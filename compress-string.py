"""
Two functions to compress and decompress a string.

Usage: include compress_string

The functions included compress and decompress a string by roughly 1/3rd by replacing 3 character
substrings with 2 character substrings.  The uncompressed string must only contain the characters
a-z, 0-9 and SPACE, UNDERSCORE.

mjnurse.uk - 2019
"""
def compress_string(p_string):
   """
   This function compresses a string by roughly 1/3rd.  Each three characters are compressed to use only
   two characters.  The three character substring can only contain the characters a-z, 0-9, UNDERSCORE,
   SPACE.  Together this makes a max of 40 different characters.  3 characters each from a set of 40
   means there are 40 * 40 * 40 = 64,000 different combinations.  64,000 / 256 = 250, this means all
   values <= 64,000 can be encoded as two ASCII characters in the range 0-255.

   """
   if len(p_string) % 3 == 2:
      p_string += ' '
   compressed_string = ''
   for itr in range(0, int(len(p_string)/3)):
      three_chars = p_string[itr*3:itr*3+3]
      three_char_val = 0
      for char in three_chars:
         if char >= 'a' and char <= 'z':
            val = ord(char) - ord('a')
         if char >= '0' and char <= '9':
            val = ord(char) - ord('0') + 26
         if char == '_':
            val = 36
         if char == ' ':
            val = 37
         three_char_val = three_char_val * 40 + val
      two_chars = chr(int(three_char_val / 256)) + chr(three_char_val % 256)
      compressed_string += two_chars
   if len(p_string) % 3 == 1:
      compressed_string += p_string[len(p_string) - 1]
   return compressed_string

def uncompress_string(p_string):
   """
   This function decompresses a 2 character substring into a 3 character substring.  This is the reverse
   logic for the compress_string function described above.
   """
   string = ''
   for itr in range(0, int(len(p_string)/2)):
      two_chars = p_string[itr*2:itr*2+2]
      two_char_val = ord(two_chars[0:1]) * 256 + ord(two_chars[1:2])
      three_chars = chr(int(two_char_val/1600)) + chr(int(two_char_val/40) % 40) + chr(two_char_val % 40)
      for char in three_chars:
         if ord(char) < 26:
            string += chr(ord(char) + ord('a'))
         elif ord(char) < 36:
            string += chr(ord(char) + ord('0') - 26)
         elif ord(char) == 36:
            string += '_'
         elif ord(char) == 37:
            string += ' '
   if len(p_string) % 2 == 1:
      string += p_string[len(p_string) - 1]
   return string
