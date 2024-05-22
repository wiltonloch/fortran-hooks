"""
Here is a simple python program showing how to use regular
expressions to write a paren-matching recursive parser.

This parser recognizes items enclosed by parens, brackets,
braces and <> symbols, but is adaptable to any set of
open/close patterns.  This is where the re package greatly
assists in parsing. 

Source: 
Author: Gene Olson
SPDX-License-Identifier: CC-BY-SA-3.0
See LICENSES/ for license information
https://stackoverflow.com/a/39263467
"""

import re


# The pattern below recognises a sequence consisting of:
#    1. Any characters not in the set of open/close strings.
#    2. One of the open/close strings.
#    3. The remainder of the string.
# 
# There is no reason the opening pattern can't be the
# same as the closing pattern, so quoted strings can
# be included.  However quotes are not ignored inside
# quotes.  More logic is needed for that....


pat = re.compile(r"""
    ( .*? )
    ( \( | \) | \[ | \] | \{ | \} | \< | \> |
                           \' | \" | BEGIN | END | $ )
    ( .* )
    """, re.X)

# The keys to the dictionary below are the opening strings,
# and the values are the corresponding closing strings.
# For example "(" is an opening string and ")" is its
# closing string.

matching = { "(" : ")",
             "[" : "]",
             "{" : "}",
             "<" : ">",
             '"' : '"',
             "'" : "'",
             "BEGIN" : "END" }

# The procedure below matches string s and returns a
# recursive list matching the nesting of the open/close
# patterns in s.

def matchnested(s, term=""):
    lst = []
    while True:
        m = pat.match(s)

        if m.group(1) != "":
            lst.append(m.group(1))

        if m.group(2) == term:
            return lst, m.group(3)

        if m.group(2) in matching:
            item, s = matchnested(m.group(3), matching[m.group(2)])
            lst.append(m.group(2))
            lst.append(item)
            lst.append(matching[m.group(2)])
        else:
            raise ValueError("After <<%s %s>> expected %s not %s" %
                             (lst, s, term, m.group(2)))

# Unit test.

if __name__ == "__main__":
    for s in ("simple string",
              """ "double quote" """,
              """ 'single quote' """,
              "one'two'three'four'five'six'seven",
              "one(two(three(four)five)six)seven",
              "one(two(three)four)five(six(seven)eight)nine",
              "one(two)three[four]five{six}seven<eight>nine",
              "one(two[three{four<five>six}seven]eight)nine",
              "oneBEGINtwo(threeBEGINfourENDfive)sixENDseven",
              "ERROR testing ((( mismatched ))] parens"):
        print "\ninput", s
        try:
            lst, s = matchnested(s)
            print "output", lst
        except ValueError as e:
            print str(e)
    print "done"