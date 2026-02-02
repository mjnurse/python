"""
Using readline Library With Custom Tab-To-Complete Command Tree

Usage: python3 tab_to_complete

An example script which shows how to use the readline library to build a press tab to complete 
command line in put with a custom command tree.

mjnurse.uk - 2019
"""

import readline
readline.parse_and_bind("tab: complete")

g_cmd_tree = {
   'connect': {
      'machine': None,
   },
   'create': {
      'machine': None,
      'network': None
   },
   'delete': {
      'machine': None,
   },
}
g_machine_list = {}

def get_machine_list():
   global g_machine_list
   if g_machine_list == {}:
      g_machine_list = {'one':None, 'two':None}
   return g_machine_list

def traverse_cmd_tree(curr_cmds, tree):
   """
   Recursive function to traverse the command tree to the nodes which are children of the command line
   command path / list.
   """
   global g_cmd_tree, g_machine_list

   # EXAMPLE
   # If we get to a machine node populate the children.  This is done on demand as it is a costly
   # process and can change.
   if len(curr_cmds) > 1:
      if (    curr_cmds[:-1] == ['connect', 'machine']
          and g_cmd_tree['connect']['machine'] == None):
         g_cmd_tree['connect']['machine'] = get_machine_list()
      if (    curr_cmds[:-1] == ['delete', 'machine']
          and g_cmd_tree['delete']['machine'] == None):
         g_cmd_tree['delete']['machine'] = get_machine_list()

   if tree is None:
      return []
   elif len(curr_cmds) == 0:
      return []
   if len(curr_cmds) == 1:
      return [x +' ' for x in tree if x.startswith(curr_cmds[0])]
   else:
      if curr_cmds[0] in tree.keys():
         return traverse_cmd_tree(curr_cmds[1:], tree[curr_cmds[0]])
      else:
         return []
   return []

def complete(text, state):
   """
   Readline command completion method.
   """
   global g_cmd_tree

   curr_cmds = readline.get_line_buffer().split()
   if not curr_cmds or readline.get_line_buffer()[-1] == ' ':
      curr_cmds.append('')
   results = traverse_cmd_tree(curr_cmds, g_cmd_tree) + [None]
   return results[state]

if __name__ == "__main__": 
 
   readline.set_completer(complete)

   line = input('> ')
   print('you chose:', line)
