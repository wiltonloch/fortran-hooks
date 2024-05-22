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

import unittest
import unittest.mock as mock
from io import StringIO

import main


class Test(unittest.TestCase):
    def apply_ICON_acc_style(self, input, output):
        m = mock.mock_open(read_data=input)
        with mock.patch("main.open", m, create=True):
            main.apply_ICON_acc_style("mock_fileA", "mock_fileB")
        # convert generator, that was passed to writelines(), to string
        written_output = "".join(m().writelines.call_args.args[0])
        self.assertEqual(written_output, output)

    def test_removal_of_empty_continued_ACC(self):
        """Remove empty ACC lines."""
        input = """
            !$ACC DIRECTIVE CLAUSE(1) &
            !$ACC &
            !$ACC CLAUSE(2)
        """
        output = """
            !$ACC DIRECTIVE CLAUSE(1) &
            !$ACC   CLAUSE(2)
        """
        self.apply_ICON_acc_style(input, output)

        input = """
            !$ACC DIRECTIVE CLAUSE(1) &
            !$ACC
        """
        output = """
            !$ACC DIRECTIVE CLAUSE(1)
        """
        self.apply_ICON_acc_style(input, output)

    def test_no_removal_of_empty_continued_ACC_with_comment(self):
        """Do not remove an empty ACC line if it has a comment."""
        input = """
            !$ACC DIRECTIVE CLAUSE(1) &
            !$ACC    & ! some smart comment
            !$ACC   CLAUSE(2)
        """
        output = input
        self.apply_ICON_acc_style(input, output)

    def test_no_removal_of_random_clause(self):
        """Don't remove a clause just because it has an empty argument list.

        TODO: verify how compilers and the standard handle this case. It is
        unclear whether empty item lists are accepted."""
        input = """
            !$ACC DIRECTIVE CLAUSE( &
            !$ACC a,b)&
            !$ACC CLAUSE(2)
        """
        output = """
            !$ACC DIRECTIVE CLAUSE() &
            !$ACC   CLAUSE(a, b) &
            !$ACC   CLAUSE(2)
        """
        self.apply_ICON_acc_style(input, output)

    def test_removal_of_known_clause(self):
        """Remove certain types of clauses if they would otherwise have an empty
        item list."""
        input = """
            !$ACC DIRECTIVE PRESENT( &
            !$ACC a,b)
        """
        output = """
            !$ACC DIRECTIVE &
            !$ACC   PRESENT(a, b)
        """
        self.apply_ICON_acc_style(input, output)

    def test_continuation_of_item_list_in_next_line(self):
        """Move clause to next line, if its item list starts just in that next line."""
        input = """
      !$ACC UPDATE DEVICE & ! This is the clause that is acutally to check
      !$ACC   (dsl4jsb_var_ptr       (HYDRO_,w_soil_sat_sl), &
      !$ACC    dsl4jsb_var_ptr       (HYDRO_,w_soil_pwp_sl) )

      !$ACC UPDATE DEVICE( &
      !$ACC    dsl4jsb_var_ptr       (HYDRO_,w_soil_sat_sl), &
      !$ACC    dsl4jsb_var_ptr       (HYDRO_,w_soil_pwp_sl) )
        """
        output = """
      !$ACC UPDATE & ! This is the clause that is acutally to check
      !$ACC   DEVICE(dsl4jsb_var_ptr       (HYDRO_,w_soil_sat_sl)) &
      !$ACC   DEVICE(dsl4jsb_var_ptr       (HYDRO_,w_soil_pwp_sl))

      !$ACC UPDATE &
      !$ACC   DEVICE(dsl4jsb_var_ptr       (HYDRO_,w_soil_sat_sl)) &
      !$ACC   DEVICE(dsl4jsb_var_ptr       (HYDRO_,w_soil_pwp_sl))
        """
        self.apply_ICON_acc_style(input, output)

    def test_complex_clause(self):
        """Test the correct parsing of a complex clause that contains
        parenthesis"""
        input = """
            !$ACC DIRECTIVE IF((B .and. B) .or. .not. BB,   test_argument(123))
        """
        output = """
            !$ACC DIRECTIVE IF((B .and. B) .or. .not. BB, test_argument(123))
        """
        self.apply_ICON_acc_style(input, output)

    def test_removing_of_commas(self):
        """Remove commas between clauses"""
        input = """
            !$ACC DIRECTIVE, IF(B), ASYNC(1),&
            !$ACC DEFAULT(PRESENT)
        """
        output = """
            !$ACC DIRECTIVE IF(B) ASYNC(1) &
            !$ACC   DEFAULT(PRESENT)
        """
        self.apply_ICON_acc_style(input, output)

    def test_capitalize(self):
        """Capitalize ACC stencil, directives and clauses"""
        input = """
            !$acc directive if(b,A) async(1)&
            !$acc default(present)
        """
        output = """
            !$ACC DIRECTIVE IF(b, A) ASYNC(1) &
            !$ACC   DEFAULT(PRESENT)
        """
        self.apply_ICON_acc_style(input, output)

    def test_indentation_warning(self):
        """A warning is printed to stdout if the indentation changes within a
        directive."""
        input = """
            !$ACC DIRECTIVE &
              !$ACC CLAUSE
        """
        output = """
            !$ACC DIRECTIVE &
              !$ACC   CLAUSE
        """
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.apply_ICON_acc_style(input, output)
        self.assertEqual(
            mock_stdout.getvalue(), "Continued line has another indentation level.\n"
        )

    def test_do_not_touch_unchanged_file(self):
        """As input and output filenames are the same and the code is already,
        beauty the mock_file should only be opened once for reading."""
        input = """
            !$ACC DIRECTIVE IF(b, A) ASYNC(1) &
            !$ACC   DEFAULT(PRESENT)
            CALL something()
        """
        m = mock.mock_open(read_data=input)
        with mock.patch("main.open", m, create=True):
            main.apply_ICON_acc_style("mock_file", "mock_file")
        # test that there was no second call with "w"rite mode
        m.assert_called_once_with("mock_file")

    def test_do_open_second_file(self):
        """As input and output filenames are the different, `open` should be
        called once for reading and once for writing."""
        input = """
            !$ACC DIRECTIVE IF(b, A) ASYNC(1) &
            !$ACC   DEFAULT(PRESENT)
            CALL something()
        """
        m = mock.mock_open(read_data=input)
        with mock.patch("main.open", m, create=True):
            main.apply_ICON_acc_style("mock_fileA", "mock_fileB")
        m.assert_any_call("mock_fileA")
        m.assert_called_with("mock_fileB", "w")  # test last call

    def test_update_file(self):
        """Test that file is opened for reading and writing"""
        input = """
            !$acc directive if(b, a) async(1) &
            !$acc DEFAULT(present)
        """  # this input is not beautiful -> beautifier has to work.
        m = mock.mock_open(read_data=input)
        with mock.patch("main.open", m, create=True):
            main.apply_ICON_acc_style("mock_file", "mock_file")
        m.assert_any_call("mock_file")
        m.assert_called_with("mock_file", "w")  # test last call


if __name__ == "__main__":
    unittest.main()
