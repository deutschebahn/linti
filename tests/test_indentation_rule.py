"""Tests for F310 – Block Indentation.

F310 judges every physical line, so the cases worth covering are the ones
where "which line is this, structurally?" is not obvious: ELSE/ELSEIF chains,
nesting, and lines that continue a statement started earlier.
"""

import pytest

from linti.cst.lines import ALIGNED, HANGING, IGNORE
from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes, apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.format.indentation_rule import IndentationRule


def _linter(indent_size: int = 4, continuation_style: str = HANGING) -> Linter:
    return Linter(
        statement_rules=[
            IndentationRule(
                indent_size=indent_size, continuation_style=continuation_style
            )
        ]
    )


def _lint(code: str, indent_size: int = 4, continuation_style: str = HANGING):
    tokens = Lexer(code).tokenize()
    return _linter(indent_size, continuation_style).lint(tokens, source=code)


def _fix(code: str, indent_size: int = 4, continuation_style: str = HANGING) -> str:
    fixed, _ = apply_fixes_iteratively(code, _linter(indent_size, continuation_style))
    return fixed


# ---------------------------------------------------------------------------
# Block indentation
# ---------------------------------------------------------------------------


def test_indentation_ok_for_if_block():
    code = """
IF (a = 1);
    nVal = 1;
ENDIF;
"""
    assert _lint(code) == []


def test_indentation_wrong_for_if_block():
    code = """
IF (a = 1);
  nVal = 1;
ENDIF;
"""
    issues = _lint(code)

    assert len(issues) == 1
    assert "Expected indentation of 4 spaces" in issues[0].message
    assert issues[0].rule_id == "F310"


def test_indentation_ok_for_while_block():
    code = """
WHILE (a = 1);
    nVal = 1;
END;
"""
    assert _lint(code) == []


def test_indentation_respects_custom_size():
    code = """
IF (a = 1);
  nVal = 1;
ENDIF;
"""
    assert _lint(code, indent_size=2) == []


def test_nested_blocks_indent_one_level_each():
    code = """
IF (a = 1);
    IF (b = 2);
        WHILE (c = 3);
            nVal = 1;
        END;
    ENDIF;
ENDIF;
"""
    assert _lint(code) == []


def test_nested_blocks_report_each_wrong_level():
    code = """
IF (a = 1);
IF (b = 2);
nVal = 1;
ENDIF;
ENDIF;
"""
    issues = _lint(code)

    # The inner ENDIF (line 5) is inside the outer IF and belongs at 4 too.
    assert [i.line for i in issues] == [3, 4, 5]
    assert "4 spaces" in issues[0].message
    assert "8 spaces" in issues[1].message
    assert "4 spaces" in issues[2].message


def test_first_line_of_a_procedure_is_checked():
    """A leading indent has no preceding newline to hang a check off."""
    issues = _lint("    nVal = 1;\n")

    assert len(issues) == 1
    assert "Expected indentation of 0 spaces" in issues[0].message


# ---------------------------------------------------------------------------
# ELSE / ELSEIF
# ---------------------------------------------------------------------------


def test_else_branch_is_indented_like_the_if():
    code = """
IF (a = 1);
    nVal = 1;
ELSE;
    nVal = 2;
ENDIF;
"""
    assert _lint(code) == []


def test_elseif_chain_is_indented_like_the_if():
    code = """
IF (a = 1);
    nVal = 1;
ELSEIF (a = 2);
    nVal = 2;
ELSEIF (a = 3);
    nVal = 3;
ELSE;
    nVal = 4;
ENDIF;
"""
    assert _lint(code) == []


def test_indented_else_keyword_is_reported():
    code = """
IF (a = 1);
    nVal = 1;
    ELSE;
    nVal = 2;
ENDIF;
"""
    issues = _lint(code)

    assert [i.line for i in issues] == [4]
    assert "Expected indentation of 0 spaces" in issues[0].message


def test_else_inside_a_nested_if_keeps_its_own_level():
    code = """
IF (a = 1);
    IF (b = 2);
        nVal = 1;
    ELSE;
        nVal = 2;
    ENDIF;
ENDIF;
"""
    assert _lint(code) == []


def test_body_after_elseif_is_indented():
    code = """
IF (a = 1);
    nVal = 1;
ELSEIF (a = 2);
nVal = 2;
ENDIF;
"""
    issues = _lint(code)

    assert [i.line for i in issues] == [5]


# ---------------------------------------------------------------------------
# Continuation lines — the hanging house style
# ---------------------------------------------------------------------------


CANONICAL_WRAPPED = """\
IF( nA = 1 );
    sValue = CellGetS(
        'Cube',
        'Elem'
    );
ENDIF;
"""


def test_canonical_wrapped_call_is_accepted():
    assert _lint(CANONICAL_WRAPPED) == []


def test_hand_aligned_continuation_is_reported_as_a_continuation():
    code = """\
IF( nA = 1 );
    sValue = CellGetS( 'Cube',
                       'Elem' );
ENDIF;
"""
    issues = _lint(code)

    assert len(issues) == 1
    assert issues[0].line == 3
    assert "Expected continuation indentation of 8 spaces" in issues[0].message


def test_hand_aligned_continuation_is_reformatted_to_hanging():
    """The reported bug: auto-fix used to flatten the alignment to 4 spaces."""
    code = """\
IF( nA = 1 );
    sValue = CellGetS( 'Cube',
                       'Elem' );
ENDIF;
"""
    assert (
        _fix(code)
        == """\
IF( nA = 1 );
    sValue = CellGetS( 'Cube',
        'Elem' );
ENDIF;
"""
    )


def test_closing_paren_returns_to_the_statement_indent():
    code = """\
IF( nA = 1 );
    sValue = CellGetS(
        'Cube'
        );
ENDIF;
"""
    issues = _lint(code)

    assert [i.line for i in issues] == [4]
    assert "Expected continuation indentation of 4 spaces" in issues[0].message


def test_nested_wrapped_calls_indent_one_level_per_paren():
    code = """\
sX = Outer(
    Inner(
        'a'
    ),
    'b'
);
"""
    assert _lint(code) == []


def test_operator_continuation_hangs_one_level():
    assert _lint("sX = 'aaa'\n    | 'bbb';\n") == []


def test_operator_continuation_at_column_zero_is_reported():
    issues = _lint("sX = 'aaa'\n| 'bbb';\n")

    assert [i.line for i in issues] == [2]
    assert "Expected continuation indentation of 4 spaces" in issues[0].message


def test_wrapped_if_condition_is_a_continuation():
    code = """\
IF(
    nA = 1
    & nB = 2
);
    nVal = 1;
ENDIF;
"""
    assert _lint(code) == []


def test_continuation_scales_with_indent_size():
    code = """\
IF( a );
  sX = Call(
    'v'
  );
ENDIF;
"""
    assert _lint(code, indent_size=2) == []


# ---------------------------------------------------------------------------
# Lines the rule must not touch
# ---------------------------------------------------------------------------


def test_blank_lines_are_ignored():
    code = "IF (a = 1);\n\n    nVal = 1;\n\nENDIF;\n"

    assert _lint(code) == []


def test_whitespace_only_lines_are_ignored():
    """F270 owns trailing whitespace; F310 must not fight it for the same line."""
    code = "IF (a = 1);\n      \n    nVal = 1;\nENDIF;\n"

    assert _lint(code) == []


def test_comment_only_lines_are_ignored():
    code = "IF (a = 1);\n# a comment at column 1\n    nVal = 1;\nENDIF;\n"

    assert _lint(code) == []


def test_lines_inside_a_multiline_string_are_never_reindented():
    """Reindenting inside a string literal would change its value."""
    code = "IF (a = 1);\n    sM = 'line1\nline2';\nENDIF;\n"

    assert _lint(code) == []
    assert _fix(code) == code


def test_unparseable_statement_still_gets_its_line_checked():
    code = "IF (a = 1);\ngarbage %% ;\nENDIF;\n"
    issues = _lint(code)

    assert [i.line for i in issues] == [2]


# ---------------------------------------------------------------------------
# Fixes
# ---------------------------------------------------------------------------


def test_fix_inserts_missing_indentation():
    assert _fix("IF (a = 1);\nnVal = 1;\nENDIF;\n") == (
        "IF (a = 1);\n    nVal = 1;\nENDIF;\n"
    )


def test_fix_replaces_wrong_indentation():
    assert _fix("IF (a = 1);\n      nVal = 1;\nENDIF;\n") == (
        "IF (a = 1);\n    nVal = 1;\nENDIF;\n"
    )


def test_fix_of_a_wrapped_call_is_idempotent():
    code = """\
sValue = CellGetS(
              'Cube',
                    'Elem'
                );
"""
    once = _fix(code)
    assert (
        once
        == """\
sValue = CellGetS(
    'Cube',
    'Elem'
);
"""
    )
    assert _fix(once) == once


def test_single_pass_fix_reports_the_canonical_target():
    """Even a misplaced statement line names the indent it should end up at."""
    code = "IF (a = 1);\n  nVal = 1;\nENDIF;\n"
    tokens = Lexer(code).tokenize()
    issues = _linter().lint(tokens, source=code)

    fixed, count = apply_fixes(code, issues)
    assert fixed == "IF (a = 1);\n    nVal = 1;\nENDIF;\n"
    assert count == 1


# ---------------------------------------------------------------------------
# continuation_style
# ---------------------------------------------------------------------------


def test_aligned_style_accepts_alignment_under_the_opening_paren():
    code = """\
IF( nA = 1 );
    sValue = CellGetS( 'Cube',
                       'Elem' );
ENDIF;
"""
    assert _lint(code, continuation_style=ALIGNED) == []
    assert _lint(code, continuation_style=HANGING) != []


def test_aligned_style_falls_back_to_hanging_when_nothing_lines_up():
    """With `(` at end of line there is no column to align with."""
    assert _lint(CANONICAL_WRAPPED, continuation_style=ALIGNED) == []


def test_ignore_style_leaves_every_continuation_line_alone():
    code = """\
IF( nA = 1 );
    sValue = CellGetS( 'Cube',
              'Elem' );
ENDIF;
"""
    assert _lint(code, continuation_style=IGNORE) == []
    assert _fix(code, continuation_style=IGNORE) == code


def test_ignore_style_still_checks_statement_lines():
    code = "IF( nA = 1 );\n  nVal = 1;\nENDIF;\n"
    issues = _lint(code, continuation_style=IGNORE)

    assert [i.line for i in issues] == [2]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_from_config_reads_size_and_style():
    (rule,) = IndentationRule.from_config({"size": 2, "continuation_style": "aligned"})

    assert rule.indent_size == 2
    assert rule.continuation_style == ALIGNED


def test_from_config_defaults():
    (rule,) = IndentationRule.from_config({})

    assert rule.indent_size == 4
    assert rule.continuation_style == HANGING


@pytest.mark.parametrize("style", ["nonsense", None, ""])
def test_unknown_continuation_style_falls_back_to_hanging(style):
    assert IndentationRule(continuation_style=style).continuation_style == HANGING


def test_rule_id():
    assert IndentationRule().RULE_ID == "F310"
