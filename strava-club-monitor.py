#!/usr/bin/env python3
"""
NAME
    strava-club-monitor.py - Monitor Strava clubs for newly posted group rides
    and send push notifications via ntfy.sh.

USAGE
    strava-club-monitor.py --setup               # First-time OAuth & club setup
    strava-club-monitor.py                       # One-shot check (for cron/launchd)
    strava-club-monitor.py --list-rides          # List upcoming rides from Strava
    strava-club-monitor.py --list-rides -F G3,G4 # List upcoming rides matching G3 or G4
    strava-club-monitor.py --set-filter G3,G4    # Save persistent title filter(s)
    strava-club-monitor.py --set-filter ""       # Clear saved title filter(s)
    strava-club-monitor.py --dry-run             # Preview without notifying or saving
    strava-club-monitor.py --list-clubs          # Show your Strava clubs and IDs
    strava-club-monitor.py --test-notify         # Send a test ntfy.sh alert

DESCRIPTION
    Queries Strava API v3 (/clubs/{id}/group_events) for one or more clubs,
    tracks seen events in ~/.local/state/strava-club-monitor/seen.json, and
    sends a push notification via ntfy.sh whenever a new ride is posted.
    Automatically refreshes expired Strava OAuth tokens.

    Uses only the Python standard library (works on macOS and Ubuntu WSL).

AUTHOR
    mjnurse.github.io - 2026
"""

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
OAUTH_REDIRECT_PORT = 8765
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_REDIRECT_PORT}/callback"

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "strava-club-monitor" / "config.json"
DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "strava-club-monitor" / "seen.json"
DEFAULT_NTFY_SERVER = "https://ntfy.sh"
DEFAULT_TIMEOUT = 60

RIDE_ACTIVITY_TYPES = {
    "ride",
    "ebikeride",
    "gravelride",
    "mountainbikeride",
    "virtualride",
    "handcycle",
    "velomobile",
}


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: dict, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp_path, mode)
    tmp_path.replace(path)


# ---------------------------------------------------------------------------
# HTTP / Strava API helpers
# ---------------------------------------------------------------------------

def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    form_data: dict | None = None,
    json_data: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = 2,
) -> tuple[int, str]:
    req_headers = {
        "User-Agent": "strava-club-monitor/1.0",
        "Accept-Encoding": "gzip",
    }
    if headers:
        req_headers.update(headers)

    body = None
    if form_data is not None:
        body = urllib.parse.urlencode(form_data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return resp.status, raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read()
            if exc.headers and exc.headers.get("Content-Encoding", "").lower() == "gzip":
                try:
                    err_body = gzip.decompress(err_body)
                except OSError:
                    pass
            err_text = err_body.decode("utf-8", errors="replace")
            if exc.code >= 500 and attempt < retries:
                last_err = RuntimeError(f"HTTP {exc.code} for {url}: {err_text}")
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"HTTP {exc.code} for {url}: {err_text}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            last_err = RuntimeError(f"Network/timeout error for {url}: {reason}")
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise last_err from exc

    raise last_err or RuntimeError(f"Request failed for {url}")


def strava_token_exchange(config: dict, code: str) -> dict:
    _, body = http_request(
        STRAVA_TOKEN_URL,
        method="POST",
        form_data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    data = json.loads(body)
    config["access_token"] = data["access_token"]
    config["refresh_token"] = data["refresh_token"]
    config["expires_at"] = int(data["expires_at"])
    return config


def ensure_valid_token(config: dict, config_path: Path, verbose: bool = False) -> str:
    now = int(time.time())
    expires_at = int(config.get("expires_at", 0))
    if config.get("access_token") and expires_at > now + 300:
        return config["access_token"]

    if not config.get("refresh_token"):
        raise RuntimeError("Missing Strava refresh_token. Run with --setup first.")

    if verbose:
        print("Refreshing Strava access token...")

    _, body = http_request(
        STRAVA_TOKEN_URL,
        method="POST",
        form_data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
        },
    )
    data = json.loads(body)
    config["access_token"] = data["access_token"]
    config["refresh_token"] = data.get("refresh_token", config["refresh_token"])
    config["expires_at"] = int(data["expires_at"])
    save_json(config_path, config, mode=0o600)
    return config["access_token"]


def strava_get(path: str, access_token: str, timeout: int = DEFAULT_TIMEOUT) -> list | dict:
    url = f"{STRAVA_API_BASE}{path}"
    _, body = http_request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
    )
    return json.loads(body)


def get_athlete_clubs(access_token: str, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    result = strava_get("/athlete/clubs?per_page=200", access_token, timeout=timeout)
    return result if isinstance(result, list) else []


def get_club_details(club_id: int, access_token: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    result = strava_get(f"/clubs/{club_id}", access_token, timeout=timeout)
    return result if isinstance(result, dict) else {}


def get_club_group_events(club_id: int, access_token: str, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    result = strava_get(f"/clubs/{club_id}/group_events?upcoming=true", access_token, timeout=timeout)
    return result if isinstance(result, list) else []


# ---------------------------------------------------------------------------
# Notifications (ntfy.sh)
# ---------------------------------------------------------------------------

def send_ntfy(
    config: dict,
    title: str,
    message: str,
    click_url: str | None = None,
    tags: list[str] | None = None,
    priority: int = 3,
) -> None:
    server = config.get("ntfy_server", DEFAULT_NTFY_SERVER).rstrip("/")
    topic = config.get("ntfy_topic", "").strip()
    if not topic:
        raise RuntimeError("Missing ntfy_topic in config. Run with --setup first.")

    payload: dict = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": priority,
    }
    if tags:
        payload["tags"] = tags
    if click_url:
        payload["click"] = click_url

    headers = {}
    token = config.get("ntfy_token", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    http_request(server, method="POST", headers=headers, json_data=payload)


# ---------------------------------------------------------------------------
# Event formatting & filtering
# ---------------------------------------------------------------------------

def parse_iso_utc(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_occurrence(ts: str) -> str:
    dt = parse_iso_utc(ts)
    if dt is None:
        return ts
    local_dt = dt.astimezone()
    return local_dt.strftime("%a %d %b %Y %H:%M %Z")


def is_ride_event(event: dict, all_activities: bool) -> bool:
    if all_activities:
        return True
    act_type = str(event.get("activity_type", "")).strip().lower()
    if not act_type:
        return True
    return act_type in RIDE_ACTIVITY_TYPES


def parse_filter_patterns(values: list[str] | str | None) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    patterns: list[str] = []
    for item in values:
        for part in item.split(","):
            cleaned = part.strip()
            if cleaned:
                patterns.append(cleaned)
    return patterns


def matches_title_filter(event: dict, title_filters: list[str]) -> bool:
    if not title_filters:
        return True
    title = str(event.get("title") or "")
    for pattern in title_filters:
        try:
            if re.search(pattern, title, re.IGNORECASE):
                return True
        except re.error:
            if pattern.lower() in title.lower():
                return True
    return False


def event_sort_key(event: dict) -> tuple[int, str, str]:
    occurrences = event.get("upcoming_occurrences") or []
    first = occurrences[0] if occurrences else ""
    dt = parse_iso_utc(first)
    if dt is not None:
        return (0, dt.isoformat(), str(event.get("title") or ""))
    return (1, first, str(event.get("title") or ""))


def has_upcoming_occurrence(event: dict, now_utc: datetime) -> bool:
    occurrences = event.get("upcoming_occurrences") or []
    if not occurrences:
        return True
    for occ in occurrences:
        dt = parse_iso_utc(occ)
        if dt is None or dt >= now_utc:
            return True
    return False


def format_event_notification(club_id: int, club_name: str, event: dict) -> tuple[str, str, str]:
    event_id = event["id"]
    title_text = event.get("title") or "Untitled Ride"
    notif_title = f"New Strava Ride: {club_name}"
    click_url = f"https://www.strava.com/clubs/{club_id}/group_events/{event_id}"

    lines = [title_text]

    occurrences = event.get("upcoming_occurrences") or []
    if occurrences:
        lines.append(f"When: {format_occurrence(occurrences[0])}")

    address = (event.get("address") or "").strip()
    if address:
        lines.append(f"Start: {address}")

    route_id = event.get("route_id")
    if route_id:
        lines.append(f"Route: https://www.strava.com/routes/{route_id}")

    description = (event.get("description") or "").strip()
    if description:
        snippet = description if len(description) <= 240 else description[:237].rstrip() + "..."
        lines.append("")
        lines.append(snippet)

    return notif_title, "\n".join(lines), click_url


# ---------------------------------------------------------------------------
# Interactive OAuth & setup
# ---------------------------------------------------------------------------

def capture_oauth_code(auth_url: str) -> str:
    captured: dict[str, str | None] = {"code": None, "error": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                captured["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Strava authorization complete!</h2>"
                    b"<p>You can close this tab and return to your terminal.</p></body></html>"
                )
            else:
                captured["error"] = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Authorization failed.</h2></body></html>")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = HTTPServer(("127.0.0.1", OAUTH_REDIRECT_PORT), CallbackHandler)
    server.timeout = 180

    print("\nOpening Strava authorization URL in your browser...")
    print(f"If it does not open automatically, visit:\n  {auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print(f"Waiting for Strava callback on {OAUTH_REDIRECT_URI} (up to 3 minutes)...")
    try:
        server.handle_request()
    finally:
        server.server_close()

    if captured["error"]:
        raise RuntimeError(f"Strava authorization error: {captured['error']}")
    if captured["code"]:
        return captured["code"]

    pasted = input(
        "\nDid not receive local callback. Paste the full redirect URL (or just the 'code' value): "
    ).strip()
    if "code=" in pasted:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
        if "code" in params:
            return params["code"][0]
    if not pasted:
        raise RuntimeError("No authorization code provided.")
    return pasted


def run_setup(config_path: Path, state_path: Path) -> int:
    print("=== Strava Club Ride Monitor Setup ===\n")
    print("1. Create a Strava API application at: https://www.strava.com/settings/api")
    print("   Set 'Authorization Callback Domain' to: localhost\n")

    existing = load_json(config_path)

    client_id = input(
        f"Strava Client ID [{existing.get('client_id', '')}]: "
    ).strip() or str(existing.get("client_id", ""))
    client_secret = input(
        f"Strava Client Secret [{'****' if existing.get('client_secret') else ''}]: "
    ).strip() or str(existing.get("client_secret", ""))

    if not client_id or not client_secret:
        print("Error: Client ID and Client Secret are required.", file=sys.stderr)
        return 1

    print("\n2. Configure ntfy.sh push notifications")
    print("   Install the ntfy app on your phone (or open https://ntfy.sh) and")
    print("   subscribe to a unique, hard-to-guess topic name (e.g. mjn-strava-rides-9482).\n")

    ntfy_server = (
        input(f"ntfy server [{existing.get('ntfy_server', DEFAULT_NTFY_SERVER)}]: ").strip()
        or existing.get("ntfy_server", DEFAULT_NTFY_SERVER)
    )
    ntfy_topic = (
        input(f"ntfy topic [{existing.get('ntfy_topic', '')}]: ").strip()
        or existing.get("ntfy_topic", "")
    )
    ntfy_token = (
        input(
            f"ntfy access token (optional, leave blank for public ntfy.sh) "
            f"[{'****' if existing.get('ntfy_token') else ''}]: "
        ).strip()
        or existing.get("ntfy_token", "")
    )

    if not ntfy_topic:
        print("Error: ntfy topic is required.", file=sys.stderr)
        return 1

    config: dict = {
        "client_id": client_id,
        "client_secret": client_secret,
        "ntfy_server": ntfy_server,
        "ntfy_topic": ntfy_topic,
        "ntfy_token": ntfy_token,
        "clubs": existing.get("clubs", {}),
        "all_activities": existing.get("all_activities", False),
    }

    auth_params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": OAUTH_REDIRECT_URI,
            "approval_prompt": "auto",
            "scope": "read",
        }
    )
    code = capture_oauth_code(f"{STRAVA_AUTH_URL}?{auth_params}")
    strava_token_exchange(config, code)
    save_json(config_path, config, mode=0o600)
    print("\nStrava OAuth tokens saved.")

    clubs = get_athlete_clubs(config["access_token"])
    club_lookup: dict[str, str] = {}
    if clubs:
        print("\nYour Strava clubs:")
        for c in clubs:
            cid = str(c["id"])
            cname = c.get("name", f"Club {cid}")
            club_lookup[cid] = cname
            print(f"  {cid:>10}  {cname}")
    else:
        print("\nNo clubs returned from /athlete/clubs (you can still enter club IDs manually).")

    default_ids = ",".join(config["clubs"].keys()) if isinstance(config.get("clubs"), dict) else ""
    raw_ids = input(f"\nEnter comma-separated club ID(s) to monitor [{default_ids}]: ").strip()
    if not raw_ids:
        raw_ids = default_ids

    selected_clubs: dict[str, str] = {}
    for part in raw_ids.split(","):
        cid = part.strip()
        if not cid:
            continue
        if cid in club_lookup:
            selected_clubs[cid] = club_lookup[cid]
        else:
            try:
                details = get_club_details(int(cid), config["access_token"])
                selected_clubs[cid] = details.get("name", f"Club {cid}")
            except Exception:
                selected_clubs[cid] = f"Club {cid}"

    if not selected_clubs:
        print("Error: At least one club ID is required.", file=sys.stderr)
        return 1

    config["clubs"] = selected_clubs

    existing_filters = ",".join(parse_filter_patterns(existing.get("title_filters")))
    raw_filters = input(
        f"Optional ride title filter(s), comma-separated (e.g. G3,G4; blank = all rides) [{existing_filters}]: "
    ).strip()
    if raw_filters == "":
        config["title_filters"] = parse_filter_patterns(existing_filters)
    else:
        config["title_filters"] = parse_filter_patterns(raw_filters)

    save_json(config_path, config, mode=0o600)
    print(f"\nConfiguration saved to {config_path} (permissions 0600).")

    send_test = input("Send a test ntfy.sh notification now? [Y/n]: ").strip().lower()
    if send_test in ("", "y", "yes"):
        send_ntfy(
            config,
            title="Strava Club Monitor Configured",
            message=f"Monitoring: {', '.join(selected_clubs.values())}",
            tags=["bike", "white_check_mark"],
        )
        print("Test notification sent!")

    print("\nSeeding existing club rides so you only get alerted on newly posted rides...")
    run_check(
        config_path=config_path,
        state_path=state_path,
        seed_only=True,
        dry_run=False,
        all_activities_override=None,
        verbose=True,
    )

    print("\nSetup complete! Add a cron job (e.g. every 15 minutes) with 'crontab -e':")
    print(f"  */15 * * * * /usr/bin/env python3 {Path(__file__).resolve()}")
    return 0


# ---------------------------------------------------------------------------
# Main monitoring check
# ---------------------------------------------------------------------------

def resolve_clubs(config: dict) -> dict[str, str]:
    clubs = config.get("clubs") or {}
    if isinstance(clubs, list):
        clubs = {str(cid): f"Club {cid}" for cid in clubs}
    return clubs


def run_set_filter(config_path: Path, raw_filters: str) -> int:
    config = load_json(config_path)
    if not config:
        print(f"Config not found at {config_path}. Run with --setup first.", file=sys.stderr)
        return 1
    patterns = parse_filter_patterns(raw_filters)
    config["title_filters"] = patterns
    save_json(config_path, config, mode=0o600)
    if patterns:
        print(f"Saved title filter(s): {', '.join(patterns)}")
    else:
        print("Cleared title filters (all rides will match).")
    return 0


def run_list_rides(
    config_path: Path,
    all_activities_override: bool | None = None,
    title_filters_override: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> int:
    config = load_json(config_path)
    if not config:
        print(f"Config not found at {config_path}. Run with --setup first.", file=sys.stderr)
        return 1

    clubs = resolve_clubs(config)
    if not clubs:
        print("No clubs configured. Run with --setup first.", file=sys.stderr)
        return 1

    all_activities = (
        all_activities_override
        if all_activities_override is not None
        else bool(config.get("all_activities", False))
    )
    title_filters = (
        title_filters_override
        if title_filters_override is not None
        else parse_filter_patterns(config.get("title_filters"))
    )

    access_token = ensure_valid_token(config, config_path, verbose=verbose)
    had_errors = False

    if title_filters:
        print(f"Active title filter(s): {', '.join(title_filters)}\n")

    for club_id_str, club_name in clubs.items():
        club_id = int(club_id_str)
        try:
            events = get_club_group_events(club_id, access_token, timeout=timeout)
        except RuntimeError as exc:
            print(f"Error fetching events for club {club_id} ({club_name}): {exc}", file=sys.stderr)
            had_errors = True
            continue

        matching = [
            e
            for e in events
            if is_ride_event(e, all_activities) and matches_title_filter(e, title_filters)
        ]
        matching.sort(key=event_sort_key)

        print(f"=== {club_name} ({len(matching)} upcoming ride(s)) ===")
        if not matching:
            print("  (none matching)")
            continue

        for event in matching:
            occurrences = event.get("upcoming_occurrences") or []
            when = format_occurrence(occurrences[0]) if occurrences else "Date TBC"
            title = event.get("title") or "Untitled Ride"
            url = f"https://www.strava.com/clubs/{club_id}/group_events/{event['id']}"
            print(f"  {when:<26}  {title}")
            print(f"  {'':<26}  {url}")
        print()

    return 1 if had_errors else 0


def run_check(
    config_path: Path,
    state_path: Path,
    seed_only: bool = False,
    dry_run: bool = False,
    all_activities_override: bool | None = None,
    title_filters_override: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> int:
    config = load_json(config_path)
    if not config:
        print(f"Config not found at {config_path}. Run with --setup first.", file=sys.stderr)
        return 1

    clubs = resolve_clubs(config)
    if not clubs:
        print("No clubs configured. Run with --setup first.", file=sys.stderr)
        return 1

    all_activities = (
        all_activities_override
        if all_activities_override is not None
        else bool(config.get("all_activities", False))
    )
    title_filters = (
        title_filters_override
        if title_filters_override is not None
        else parse_filter_patterns(config.get("title_filters"))
    )

    access_token = ensure_valid_token(config, config_path, verbose=verbose)

    first_run = not state_path.is_file()
    state = load_json(state_path)
    seen_by_club: dict[str, dict] = state.setdefault("seen_events", {})
    now_utc = datetime.now(timezone.utc)

    effective_seed = seed_only or first_run
    if first_run and not seed_only and verbose:
        print("First run detected: seeding existing events without sending alerts.")

    new_alerts = 0
    had_errors = False
    succeeded_clubs = 0

    for club_id_str, club_name in clubs.items():
        club_id = int(club_id_str)
        if verbose:
            filter_note = f" [filter: {', '.join(title_filters)}]" if title_filters else ""
            print(f"Checking club {club_id} ({club_name}){filter_note}...")

        try:
            events = get_club_group_events(club_id, access_token, timeout=timeout)
        except RuntimeError as exc:
            print(f"Error fetching events for club {club_id} ({club_name}): {exc}", file=sys.stderr)
            had_errors = True
            continue

        succeeded_clubs += 1

        club_seen: dict[str, dict] = seen_by_club.setdefault(club_id_str, {})
        matching_events = [
            e
            for e in events
            if is_ride_event(e, all_activities) and matches_title_filter(e, title_filters)
        ]

        if verbose:
            print(f"  Found {len(matching_events)} matching event(s).")

        for event in matching_events:
            event_id = str(event["id"])
            if event_id in club_seen:
                continue

            if not effective_seed and has_upcoming_occurrence(event, now_utc):
                notif_title, notif_body, click_url = format_event_notification(
                    club_id, club_name, event
                )
                if dry_run:
                    print(f"[DRY RUN] Would alert:\n  Title: {notif_title}\n  URL:   {click_url}")
                    for line in notif_body.splitlines():
                        print(f"  {line}")
                else:
                    send_ntfy(
                        config,
                        title=notif_title,
                        message=notif_body,
                        click_url=click_url,
                        tags=["bike"],
                    )
                    if verbose:
                        print(f"  Alert sent: {event.get('title')} ({event_id})")
                new_alerts += 1

            club_seen[event_id] = {
                "title": event.get("title", ""),
                "first_seen": now_utc.isoformat(),
                "upcoming_occurrences": event.get("upcoming_occurrences") or [],
            }

    state["last_checked"] = now_utc.isoformat()
    if not dry_run and succeeded_clubs > 0:
        save_json(state_path, state, mode=0o600)

    if verbose or dry_run:
        if effective_seed and succeeded_clubs > 0:
            print(f"Seeded existing events into {state_path}.")
        elif succeeded_clubs > 0:
            print(f"Done. {new_alerts} new ride alert(s).")

    return 1 if had_errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor Strava clubs for newly posted rides and alert via ntfy.sh."
    )
    parser.add_argument("--setup", action="store_true", help="Interactive OAuth, club, and ntfy setup")
    parser.add_argument("--list-clubs", action="store_true", help="List Strava clubs you belong to")
    parser.add_argument("--list-rides", action="store_true", help="List upcoming rides for monitored clubs")
    parser.add_argument(
        "-F",
        "--filter",
        action="append",
        dest="filters",
        metavar="PATTERN",
        help="Only include rides whose title matches pattern(s), comma-separated or repeatable (e.g. -F G3,G4)",
    )
    parser.add_argument(
        "--set-filter",
        metavar="PATTERN",
        help="Save persistent title filter(s) to config (e.g. --set-filter G3,G4; use \"\" to clear)",
    )
    parser.add_argument("--test-notify", action="store_true", help="Send a test ntfy.sh notification")
    parser.add_argument("--seed", action="store_true", help="Mark current events as seen without alerting")
    parser.add_argument("--dry-run", action="store_true", help="Show new rides without sending alerts or saving state")
    parser.add_argument("--all-activities", action="store_true", help="Alert on all activity types, not just rides")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help=f"Config file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help=f"State file (default: {DEFAULT_STATE_PATH})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print status output")
    args = parser.parse_args()

    title_filters_override = (
        parse_filter_patterns(args.filters) if args.filters is not None else None
    )

    try:
        if args.setup:
            return run_setup(args.config, args.state)

        if args.set_filter is not None:
            return run_set_filter(args.config, args.set_filter)

        if args.list_clubs:
            config = load_json(args.config)
            if not config:
                print(f"Config not found at {args.config}. Run with --setup first.", file=sys.stderr)
                return 1
            token = ensure_valid_token(config, args.config, verbose=args.verbose)
            clubs = get_athlete_clubs(token, timeout=args.timeout)
            for c in clubs:
                print(f"{c['id']:>10}  {c.get('name', '')}")
            return 0

        if args.list_rides:
            return run_list_rides(
                config_path=args.config,
                all_activities_override=True if args.all_activities else None,
                title_filters_override=title_filters_override,
                timeout=args.timeout,
                verbose=args.verbose,
            )

        if args.test_notify:
            config = load_json(args.config)
            if not config:
                print(f"Config not found at {args.config}. Run with --setup first.", file=sys.stderr)
                return 1
            send_ntfy(
                config,
                title="Strava Club Monitor Test",
                message="Push notifications from strava-club-monitor.py are working!",
                tags=["bike", "tada"],
            )
            print("Test notification sent!")
            return 0

        return run_check(
            config_path=args.config,
            state_path=args.state,
            seed_only=args.seed,
            dry_run=args.dry_run,
            all_activities_override=True if args.all_activities else None,
            title_filters_override=title_filters_override,
            timeout=args.timeout,
            verbose=args.verbose,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
