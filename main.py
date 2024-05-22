#!/usr/bin/env python3

# ICON OpenACC code beautifier
#
# ---------------------------------------------------------------
# Copyright (C) 2004-2024, DWD, MPI-M, DKRZ, KIT, ETH, MeteoSwiss
# Contact information: icon-model.org
#
# See AUTHORS.md for a list of authors
# See LICENSES/ for license information
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------

import logging
import os
import re
import sys

log = logging.getLogger(__name__)

acc_stencil = "!$ACC"

acc_label = "[a-zA-Z][a-zA-Z_]*"

# (at least one space) or (comma with some or no spaces)
re_acc_clause_delimiter = re.compile(" +| *, *")
re_acc_item_delimiter = re.compile(" *, *")

reduction_operator = r"\+|\*|\.and\.|\.or\.|\.eqv\.|\.neqv\."
re_acc_collon_plus_etc = re.compile(
    f"^([a-z]+|{reduction_operator}) *: *(.*)$", re.IGNORECASE
)  # any ACC keyword or reduction operator and some list item


# The following pattern matches a sequence consisting of:
#    1. Any characters that does not open/close a bracket or is end of string.
#    2. A open/close bracket or end of string.
#    3. The remainder of the string.
re_brackets = re.compile(
    r"""
    ( .*? )
    ( \( | \) | $ )
    ( .* )
    """,
    re.VERBOSE,
)  # VERBOSE: ignore spaces in expression


class NestingError(ValueError):
    """Imbalance of nested brackets."""


def match_nested_brackets(s, in_nest=False):
    """Match a string s and return a recursive list matching nests of open/close
    brackets in s.

    This function is inspired by Gene Olson's code (CC BY-SA 3.0)
    https://stackoverflow.com/a/39263467
    """
    _list = []
    while True:
        m = re_brackets.match(s)

        if m.group(1) != "":
            # There is anything before an open/close bracket or end
            _list.append(m.group(1))

        if m.group(2) == "(":
            # Recursively parse the nested code
            item, s = match_nested_brackets(m.group(3), in_nest=True)
            _list.append("(")
            _list.append(item)
            _list.append(")")
        elif m.group(2) == ")" and in_nest:
            # matches the closing bracket (recursive mode)
            return _list, m.group(3)
        elif m.group(2) == "" and not in_nest:
            # reached end of the string, return list
            return _list
        else:
            raise NestingError(
                "After %r expected %r not %r in string %r"
                % (_list, "(" if in_nest else "", m.group(2), s)
            )


class Acc_code(object):
    """The class represents a line of ACC code
    (Everything between stencil and comment-or-continuation-symbol)

    A line of ACC code may represent a full ACC directive or only parts of it if
    the directive is continued over multiple lines.

    In Fortran, OpenACC directives are specified in free-form source files as
        !$acc directive-name [clause-list]
    However, this class does not differentiate between directive names and
    clause names as both follow the same syntax. Directives and clauses are
    collected within one joined `clause_list`.
    """

    def __init__(self):
        """Initialize an ACC line"""

        self.clause_list = []

    def append_clause(self, clause_name):
        """Add a new clause (or directive) to clause_list

        Parameters
        ----------
        clause_name : str or Acc_directive_or_clause
            Name of clause (or second part of compound directive name)
        """
        if isinstance(clause_name, Acc_directive_or_clause):
            self.clause_list.append(clause_name)
        else:
            clause_name = clause_name.upper()
            if clause_name == "DEFAULT":
                self.clause_list.append(Acc_clause_default())
            else:
                self.clause_list.append(Acc_directive_or_clause(clause_name))

    def __str__(self):
        """Return the styled string according to the ICON OpenACC style guide"""
        return " ".join(str(c) for c in self.clause_list if str(c))

    def __len__(self):
        """Return the current number of elements in the clause list"""
        return len(self.clause_list)

    def append_item(self, item_name):
        """Append an item to the last clause in the list"""
        self.clause_list[-1].append(item_name.strip())

    def append_items(self, items):
        """Append items to the last clause in the list

        Parameters
        ----------
        items : list of strings and lists
            Items to append. As result of match_nested_brackets
        """

        def recursive_merge(items):
            if isinstance(items, list):
                return "".join(recursive_merge(item) for item in items)
            else:
                # should be a string
                return items

        # Item list with first item given. New items are appended when there is
        # a comma in `items`.
        item_list = [""]
        for item in items:
            if item in ("(", ")"):
                item_list[-1] += item
                continue

            if isinstance(item, list):
                # this is something that was within brackets
                item_list[-1] += recursive_merge(item)
                continue

            # split by comma, and strip spaces
            new_items = iter(re_acc_item_delimiter.split(item))
            # append first element until a comma separator is found
            item_list[-1] += next(new_items)
            # remaining items were separated by comma
            item_list.extend(new_items)

        for item_name in item_list:
            self.append_item(item_name)

    def get_last_item_list_name(self):
        return self.clause_list[-1].name

    def pop_last_clause(self):
        return self.clause_list.pop()


class Acc_directive_or_clause(object):
    """Represents an ACC directive or clause

    An ACC clause may have a list of items that are given in parenthesis
    after the clause. These arguments are stored in the `item_list`.
    """

    # Name of the directive or clause
    name = ""

    def __init__(self, name):
        self.name = name
        self.item_list = []

    def append(self, item_name):
        """Append an item to the item list

        Parameters
        ----------
        item_name : str
            Name of the item
        """
        self.item_list.append(item_name)

    def __str__(self):
        """Styled string according to the ICON OpenACC style guide"""
        self.capitalize_items_before_collon()
        if not self.item_list:
            return self.name.upper()
        elif self.item_list == [""] and self.is_ok_to_remove_if_no_items():
            # empty list, original clause was something like `clause()`. Remove.
            return ""
        else:
            return f"{self.name.upper()}({', '. join(self.item_list)})"

    def capitalize_items_before_collon(self):
        def format(i):
            """Capitalize all keywords before a ":" """
            match = re_acc_collon_plus_etc.search(i)
            if match is None:
                return i
            ii = match.groups()
            return f"{ii[0].upper()}: {ii[1]}"

        self.item_list = [format(i) for i in self.item_list]

    def is_ok_to_remove_if_no_items(self):
        """Test if this clause save to remove if the item list is empty."""
        # All clauses in the following list have no effect if used without items.
        return self.name.upper() in {"SELF", "DEVICE", "HOST", "REDUCTION",
            "PRESENT", "PRIVATE", "FIRSTPRIVATE", "COPY", "COPYIN", "COPYOUT",
            "CREATE", "NO_CREATE", "DELETE", "ATTACH", "DETACH", "BIND",
            "DEVICEPTR", "DEVICE_RESIDENT", "LINK", }


class Acc_clause_default(Acc_directive_or_clause):
    """DEFAULT clause"""

    def __init__(self):
        super().__init__("DEFAULT")

    def __str__(self):
        assert len(self.item_list) == 1
        assert self.item_list[0].upper() in ("NONE", "PRESENT")
        return f"{self.name.upper()}({self.item_list[0].upper()})"


class LineParser(object):
    directive = ""
    open_itemlist_continues_in_next_line = False

    def __init__(self, line, previous_lp=None):
        """Parse a line of OpenACC code

        The code is expected to be valid ACC code. It's style is assumed to be
        close to the ICON ACC style guide. Complex Fortran expressions in ACC
        item-lists can not be parsed and may result in errors. Also, Fortran
        expressions continued over multiple lines can not be interpreted. Such
        code requires manual adjustment as it violates the ICON OpenACc Style
        guide.
        """
        self._original_line = line
        exit = False
        try:
            self.parse(line, previous_lp)
        except NotImplementedError as e:
            print()
            print()
            print(e)
            if previous_lp:
                print("Previous line: %r" % previous_lp._original_line)
            print("This line: %r" % self._original_line)
            print("Please adjust the corresponding ACC code manually or implement an automatic correction.")
            exit = True
        except Exception as e:
            print()
            print("Error while parsing a line. Please try to beautify the following line manually.")
            if previous_lp:
                print("Previous line: %r" % previous_lp._original_line)
            print("This line: %r" % self._original_line)
            raise
        if exit: sys.exit(1)

    def parse(self, line, previous_lp=None):
        line_upper = line.upper()
        self.indentation = line_upper.index(acc_stencil)
        start = self.indentation + len(acc_stencil) + 1 #  Add one for subsequent space

        acc_line = line[start:].strip()
        if acc_line.startswith("&"):
            # remove the line continuation symbol at the beginning of the line
            acc_line = acc_line[1:].lstrip()
            # Handle the case of an empty ACC directive that consists of only one & (and maybe a comment)
            # TODO: review whether this is necessary at all
            if acc_line == "":
                # We just removed the only meaning full of this line
                acc_line = "&"  # restore line continuation
            elif acc_line.startswith("!"):
                acc_line = f"& {acc_line}"

        if "!" in acc_line and "&" in acc_line:
            pos_comment = acc_line.index("!")
            pos_continuation = acc_line.index("&")
            end = min(pos_comment, pos_continuation)
            self.line_end = " " + acc_line[end:]
        elif "!" in acc_line:
            # ignore everything starting with the comment symbol
            end = acc_line.index("!")
            self.line_end = " " + acc_line[end:]
        elif "&" in acc_line:
            # ignore everything starting with the line continuation
            end = acc_line.index("&")
            log.debug("Position of &: %i", end)
            self.line_end = " " + acc_line[end:]
            log.debug("line_end: %s", self.line_end)
        else:
            end = len(acc_line) + 1
            self.line_end = ""

        acc_line = acc_line[:end].strip()

        self.is_continuation = (
            previous_lp is not None and previous_lp.continues_in_next_line()
        )

        self.is_continuing_item_list = self.is_continuation and previous_lp.open_itemlist_continues_in_next_line

        if self.is_continuation:
            if self.indentation != previous_lp.indentation:
                # raise ValueError("Continued line has another indentation level.")
                print("Continued line has another indentation level.")
                # TODO: automatically detect correct indentation level

        """parsing strategy:

        as long as something is inside brackets, it must by delimited by commas
        that are not within deeper brackets. Otherwise parts (directives/clauses)
        may be separated by comma and/or white space.
        An open bracket at the beginning is missing, if previous_lp.open_itemlist_continues_in_next_line
        A close bracket at the end might be missing, if self.continues_in_next_line()
            Then set self.open_itemlist_continues_in_next_line to True

        match_nested_brackets is used to parse the line after adding knowingly
        missing brackets (see above).
        """

        if self.is_continuing_item_list:
            if acc_line.startswith(
                ")"
            ):  # special case of just a single closing bracket closing a continued line:
                if previous_lp.open_itemlist_ended_with_comma:
                    raise ValueError('ACC Syntax error. Previous item list ended with "," but is not continued in this line.')
                acc_line = acc_line[1:].lstrip()
                if acc_line.startswith(","): # this comma separates clauses
                    acc_line = acc_line[1:].lstrip()
            else:
                item_list_starts_with_comma = acc_line.startswith(",")
                if item_list_starts_with_comma and previous_lp.open_itemlist_ended_with_comma:
                    raise ValueError('ACC Syntax error. Previous item list ended with "," but this line starts with ",".')
                if item_list_starts_with_comma and previous_lp.open_itemlist_ended_with_opening_bracket:
                    raise ValueError('ACC Syntax error. Previous item list ended with "(" but this line starts with ",".')
                if not (previous_lp.open_itemlist_ended_with_comma or previous_lp.open_itemlist_ended_with_opening_bracket):
                    if not item_list_starts_with_comma:
                        raise NotImplementedError('Parsing error: Can not handle continued item lists that have the line break within an item.')
                    else:
                        # Continued line starts with a comma, which we can strip away.
                        # The previous line is well-formed due to the added closing parenthesis.
                        acc_line = acc_line[1:].lstrip()
                acc_line = previous_lp.get_open_item_list_name() + "(" + acc_line

        ends_with_comma = False
        ends_with_opening_bracket = False
        if self.continues_in_next_line():
            if acc_line.endswith(","):
                # remove final comma in a continued line
                acc_line = acc_line[:-1].strip()
                ends_with_comma = True
            elif acc_line.endswith("("):
                # The line ends with a new clause whose contents are on the next line.
                ends_with_opening_bracket = True

        try:
            match = match_nested_brackets(acc_line)
        except NestingError:
            if self.continues_in_next_line():
                # allow for closed bracket in next line
                acc_line += ")"
                match = match_nested_brackets(acc_line)
                # if match_nested_brackets successes with a additional bracket,
                # that we know, that it continues in next line
                self.open_itemlist_continues_in_next_line = True
                self.open_itemlist_ended_with_comma = ends_with_comma
                self.open_itemlist_ended_with_opening_bracket = ends_with_opening_bracket
            else:
                raise
        log.debug("parsed acc_line: %r", acc_line)
        log.debug("Matches: %r", match)

        self.acc_code = Acc_code()

        for item in match:
            log.debug("item in match: %r", item)
            if item in ("(", ")"):
                # start or end of an item list. We will recognize an item list as it is a Python list.
                continue
            if isinstance(item, list):
                if len(self.acc_code) == 0:
                    self.acc_code.append_clause(previous_lp.pop_last_clause())
                self.acc_code.append_items(item)
                continue

            # split by spaces and/or a comma
            for clause in re_acc_clause_delimiter.split(item):
                log.debug("clause in m %r", clause)
                if clause != "":
                    self.acc_code.append_clause(clause)

    def continues_in_next_line(self):
        return self.line_end.startswith(" &")

    def get_open_item_list_name(self):
        return self.acc_code.get_last_item_list_name()

    def pop_last_clause(self):
        return self.acc_code.pop_last_clause()

    def has_no_acc_code_or_comment(self):
        return str(self.acc_code) == "" and self.line_end in (" &", "")

    def remove_continuation(self):
        self.line_end = self.line_end.lstrip(" &")

    def __str__(self):
        indentation = " " * self.indentation
        if self.is_continuation:
            return f"{indentation}!$ACC   {str(self.acc_code)}{self.line_end}".rstrip() + "\n"
        else:
            return f"{indentation}!$ACC {str(self.acc_code)}{self.line_end}".rstrip() + "\n"

    def __repr__(self):
        class_name = type(self).__name__
        prompt = f"{class_name}({self._original_line!r})"
        return f"{prompt}\n{'-' * (len(class_name) - 2) }>> {str(self)!r}"


def walk(rootdir):
    """Iteratively walk through rootdir and style all .{f,F}90 files"""
    lines_changed_total = 0
    files_total = 0
    for subdir, dirs, files in os.walk(rootdir):
        for file in files:
            if file.endswith(".f90") or file.endswith(".F90"):
                file = os.path.join(subdir, file)
                log.info("Apply style to %s.", file)
                lines_changed = apply_ICON_acc_style(file, file)
                log.info("Lines changed more than their case: %d", lines_changed)
                lines_changed_total += lines_changed
                files_total += 1

    print(
        f"{lines_changed_total} lines in {files_total} files changed (excluding case changes)"
    )


def apply_ICON_acc_style(in_file, out_file):
    """Apply ICON ACC style on given file

    Reads in_file and writes to out_file. May be the same.
    """
    previous_lp = None
    processed_lines = []
    lines_changed = 0  # number of lines with more than case changed
    is_anything_changed = False  # are there any changes to a file?
    with open(in_file) as f:
        for line in f:
            line_upper = line.upper()
            if not line_upper.lstrip().startswith(acc_stencil):
                processed_lines.append(line)
                continue

            lp = LineParser(line, previous_lp)
            if line.lower() != str(lp).lower():
                lines_changed += 1
            if line != str(lp):
                is_anything_changed = True
            # Remove empty continued ACC lines
            if lp.has_no_acc_code_or_comment():
                if not lp.continues_in_next_line():
                    previous_lp.remove_continuation()
                    is_anything_changed = True
                continue  # drop this line
            processed_lines.append(lp)
            previous_lp = lp

    if in_file != out_file or is_anything_changed:
        with open(out_file, "w") as f:
            f.writelines(str(l) for l in processed_lines)

    return lines_changed


if __name__ == "__main__":

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    log.handlers = [stream_handler]

    if len(sys.argv) == 1:
        print("Missing argument.")
        print("Warning: This program modifies given files in place!")
        print(f"Syntax: {sys.argv[0]} file1 file2 directory1/ directory2/")
        sys.exit(1)
    else:
        files_or_dirs = sys.argv[1:]

    if len(files_or_dirs) == 1 and os.path.isfile(files_or_dirs[0]):
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    print("Warning: This program modifies given files in place!")

    for f in files_or_dirs:
        if os.path.isdir(f):
            walk(f)
        else:
            apply_ICON_acc_style(f, f)
