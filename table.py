#!/usr/bin/env python3
"""
A class to create and draw a text table

Usage: import table OR python3 table.py

This class defines a table object which can be constructed row by row and then printed or returned as
a string.  The table column heading can be specified along with the format of each column when the
table object is created.

mjnurse.uk - 2019
"""

import re

class table:
   """
   This class defines a table object which can be constructed row by row and then printed or returned as
   a string.  The table column heading can be specified along with the format of each column when the
   table object is created.
   """

   def __init__(self, **params):
      """
      Table instantiated with a variable list of parameter pairs.  The parameter pairs are named c#n and
      c#f where # in a number from 1 to n where n in the number of table columns.
      """
      self.formats = {}
      self.last_row_is_a_border = False
      header = '|'
      for i in range(1, 21):
         col_format_field = 'c' + str(i) + 'f'
         if col_format_field in params.keys():
            try:
               self.formats[col_format_field] = '{:' + params[col_format_field] + '}'
            except:
               self.formats[col_format_field] = '{:}'
         else:
            self.formats[col_format_field] = '{:10}'
         col_name_field = 'c' + str(i) + 'n'
         if col_name_field in params.keys():
            header_field_format = self.formats[col_format_field]
            header_field_format = re.sub(r'\.[^}]*', r'', header_field_format)
            header_field_format = re.sub(r'[df,]', r'', header_field_format)
            header += header_field_format.format(params[col_name_field]) + '|'
      self.border = re.sub(r'[^|]', r'-', header)
      self.border = re.sub(r'[|]', r'+', self.border)

      self.table = self.border
      self.table += '\n' + header
      self.table += '\n' + self.border

   def add_row(self, **params):
      """
      Adds a row to the table.  This is called with a variable list of parameters.  The parameters are
      named c# where # in a number from 1 to n where n in the number of table columns.
      """
      row = '|'
      for i in range(1, 21):
         col_format_field = 'c' + str(i) + 'f'
         col_name_field = 'c' + str(i)
         if col_name_field in params.keys():
            try:
               row += self.formats[col_format_field].format(params[col_name_field]) + '|'
            except:
               field_format = self.formats[col_format_field]
               field_format = re.sub(r'\.[^}]*', r'', field_format)
               field_format = re.sub(r'[df,]', r'', field_format)
               field_length = int(re.sub(r'[{}:]', r'', field_format))
               row += field_format.format('#' * field_length) + '|'
      self.table += '\n' + row
      self.last_row_is_a_border = False

   def add_divider(self):
      """
      Adds a horizontal divider / line to the table.
      """
      self.table += '\n' + self.border
      self.last_row_is_a_border = True

   def to_string(self):
      """
      Returns the table as a string.
      """
      if not self.last_row_is_a_border:
         self.add_divider()
      return self.table

   def print(self):
      """
      Prints the table.
      """
      print(self.to_string())

"""
The following code allows the python script to be executed directly (as well as included as a package in
other python scripts).

This code tests the class and creates and prints an example table.
"""
if __name__ == "__main__":

   tab = table(c1n='format', c1f='12',
               c2n='>10', c2f='>10',
               c3n='^10', c3f='^10',
               c4n='10', c4f='10',
               c5n='10.2f', c5f='10.2f',
               c6n='10,.2f', c6f='10,.2f',
               c7n='10d', c7f='10d',
               c8n='12,d', c8f='12,d',
               c9n='8.3', c9f='8.3',
               c10n='10.0f', c10f='10.0f')

   for val in [1234.567, 'hello', 123456]:
      tab.add_row(c1=val, c2=val, c3=val, c4=val, c5=val, c6=val, c7=val, c8=val, c9=val, c10=val)
   tab.add_divider()
   val = 0
   tab.add_row(c1=val, c2=val, c3=val, c4=val, c5=val, c6=val, c7=val, c8=val, c9=val, c10=val)

   print(tab.to_string())
