#!/usr/bin/env python3
"""
A template python script which reads from the console and executes commands

Usage: python choice.py

A template python script which reads from the console and execute commands.  Also builds a help text and
includes a toggled command timer.

mjnurse.uk - 2019
"""

import os
import time
#import pysnooper


G_TIMER_DEFAULT_ON = False

# ===========================================================================================================

#@pysnooper.snoop()
def choice():
   """
   An interactive option selection interface.
   """

   timer_on = G_TIMER_DEFAULT_ON

   def help_msg(cmd_str, cmd_desc):
      return cmd_str + (' ' * (5 - len(cmd_str))) + ' - ' + cmd_desc + '\n'

   while 1==1:
      help_str = ''
      cmd = ''
      cmd_line = input('> ')  # raw_input
      cmd_list = cmd_line.split()
      num_cmds = len(cmd_list) - 1
      if num_cmds > -1:
         cmd = cmd_list[0]

      before = time.time()

      help_str += help_msg('cls', 'clear the screen')
      # ---------------------------------------------
      if cmd == 'cls':
         _ = os.system('clear')
         print('\033[3J')
         _ = os.system('clear')
         print('\033[3J')

      help_str += help_msg('q', 'quit')
      # -------------------------------
      if cmd == 'q':
         return

      help_str += help_msg('time', 'timer on/off')
      # ------------------------------------------
      if cmd == 'time':
         timer_on = not timer_on
         print('Timer ' + ('on' if timer_on else 'off'))

      help_str += help_msg('h / ?', 'this help')
      # ----------------------------------------
      if cmd == 'h' or cmd == '?':
         print('\n' + help_str)

      if cmd == '':
         print('\nh - help, q - quit')

      if timer_on:
         print('\nDuration:', round(time.time() - before, 3))

# ===========================================================================================================

choice()
