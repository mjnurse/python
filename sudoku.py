"""
Sudoku Solver

Usage: python3 sudoku.py

My first sudoku solver.  Next task, make it more efficient or solve with less code.
"""

SHOW_OPERATIONS = False
BOARD = {}

# Game defined using a string so we can replace this is a text file load.
GAME = ('0 8 5 0 3 0 4 7 0'
        + '0 0 0 5 0 8 0 0 0'
        + '0 1 9 7 0 0 0 0 0'
        + '5 0 8 4 0 7 0 0 0'
        + '0 4 0 0 1 0 6 0 0'
        + '0 0 7 0 0 0 0 0 0'
        + '0 0 1 3 0 0 7 2 6'
        + '9 0 0 8 0 0 0 4 0'
        + '4 0 0 2 0 6 0 9 0')
GAME = GAME.replace(' ', '')

def print_game():
   """
   A utility function to print the sudoku board to standard out.
   """
   for row in range(0, 9):
      string = ''
      for col in range(0, 9):
         if len(BOARD[row, col].replace('0', '')) == 1:
            string += BOARD[row, col] + ' '
         else:
            string += '_ '
      print(string)
   print()

def print_operation(iteration, row, col, operation, value):
   """
   Prints a descrition about an operation which is described by the parameters passed.
   """
   if SHOW_OPERATIONS:
      print('i:' + str(iteration), 'r:' + str(row), 'c:' + str(col), 'op:', operation, 'val:' + value)

def main():
   """
   The main application process.
   """
   # Load game from string into array.
   for row in range(0, 9):
      for col in range(0, 9):
         if GAME[row * 9 + col] != '0':
            BOARD[row, col] = GAME[row * 9 + col]
         else:
            BOARD[row, col] = '123456789'
   print_game()

   # Loop through rows and columns, repeat until there are no changes (max 100 iterations).
   for iteration in range(0, 100):
      change_made = False
      for row in range(0, 9):
         for col in range(0, 9):
            if len(BOARD[row, col]) > 1:
               # Check if any cell in the row has been derived and remove this from this cells options.
               for inner_col in range(0, 9):
                  if (col != inner_col
                      and len(BOARD[row, inner_col]) == 1
                      and BOARD[row, inner_col] in BOARD[row, col]
                      and len(BOARD[row, col]) > 1):
                     BOARD[row, col] = BOARD[row, col].replace(BOARD[row, inner_col], '')
                     print_operation(iteration, row, col, 'row scan found and removed', BOARD[row, inner_col])
                     change_made = True
               # Check if any cell in the column has been derived and remove this from this cells options.
               for inner_row in range(0, 9):
                  if (row != inner_row
                      and len(BOARD[inner_row, col]) == 1
                      and BOARD[inner_row, col] in BOARD[row, col]
                      and len(BOARD[row, col]) > 1):
                     BOARD[row, col] = BOARD[row, col].replace(BOARD[inner_row, col], '')
                     print_operation(iteration, row, col, 'col scan found and removed', BOARD[inner_row, col])
                     change_made = True
               # Check if any cell in the parent 3x3 box has been derived and remove this from this cells
               # options.
               for inner_row in range(0, 3):
                  for inner_col in range(0, 3):
                     val = BOARD[int(row / 3) * 3 + inner_row, int(col / 3) * 3 + inner_col]
                     if (BOARD[row, col] != val
                         and len(val) == 1
                         and val in BOARD[row, col]
                         and len(BOARD[row, col]) > 1):
                        BOARD[row, col] = BOARD[row, col].replace(val, '')
                        print_operation(iteration, row, col, 'box scan found and removed', val)
                        change_made = True
               # For each cell in a row with more than one number, check each number and if it can't go in
               # another cell in the row set that cell to that number.
               if len(BOARD[row, col]) > 1:
                  for num in BOARD[row, col]:
                     hits = 0
                     for inner_col in range(0, 9):
                        if num in BOARD[row, inner_col]:
                           hits += 1
                     if hits == 1:
                        BOARD[row, col] = num
                        print_operation(iteration, row, col, 'row scan set', BOARD[row, col])
                        change_made = True
                        break
               # For each cell in a column with more than one number, check each number and if it can't go in
               # another cell in the column set that cell to that number.
               if len(BOARD[row, col]) > 1:
                  for num in BOARD[row, col]:
                     hits = 0
                     for inner_row in range(0, 9):
                        if num in BOARD[inner_row, col]:
                           hits += 1
                     if hits == 1:
                        BOARD[row, col] = num
                        print_operation(iteration, row, col, 'col scan set', BOARD[row, col])
                        change_made = True
                        break
      if not change_made:
         break

   print_game()

main()
