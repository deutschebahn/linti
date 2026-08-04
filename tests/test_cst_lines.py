"""Tests for the physical-line model (`linti.cst.lines`).

The model exists to separate *this line starts a statement* from *this line
continues one*, and to say what the hanging-indent house style expects of each.
Everything F310 and the reflow fixer do rests on those two answers.
"""

import pytest

from linti.cst.lines import LineIndex
from linti.cst.node import CstKind
from linti.lexer.lexer import Lexer
from linti.parser.parser import Parser


def _index(source: str) -> LineIndex:
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    return LineIndex(tokens, program.cst)


def _expected(source: str, indent_size: int = 4) -> dict[int, int]:
    """Canonical indent per line, skipping lines the model has no opinion on."""
    index = _index(source)
    return {
        line: indent
        for line in range(1, source.count("\n") + 2)
        if (indent := index.expected_indent(line, indent_size)) is not None
    }


def _actual(source: str) -> dict[int, int]:
    index = _index(source)
    return {info.line: info.indent_width for info in index if info.is_code}


CANONICAL = """\
IF( nA = 1 );
    sValue = CellGetS(
        'Cube',
        'Elem'
    );
ENDIF;
"""


# ---------------------------------------------------------------------------
# Continuation detection
# ---------------------------------------------------------------------------


def test_statement_lines_are_not_continuations():
    index = _index("nA = 1;\nnB = 2;\n")

    assert index.get(1).is_continuation is False
    assert index.get(2).is_continuation is False


def test_wrapped_argument_lines_are_continuations():
    index = _index(CANONICAL)

    assert index.get(2).is_continuation is False  # sValue = CellGetS(
    assert index.get(3).is_continuation is True  # 'Cube',
    assert index.get(4).is_continuation is True  # 'Elem'
    assert index.get(5).is_continuation is True  # );


def test_operator_continuation_without_parentheses_is_a_continuation():
    index = _index("sX = 'aaa'\n    | 'bbb';\n")

    assert index.get(1).is_continuation is False
    assert index.get(2).is_continuation is True
    assert index.get(2).delim_depth == 0


@pytest.mark.parametrize("keyword", ["ELSE;", "ELSEIF( nA = 2 );", "ENDIF;"])
def test_construct_keywords_start_their_line(keyword):
    """ELSE/ELSEIF/ENDIF continue the IF, but they are not continuation lines."""
    source = f"IF( nA = 1 );\n  nB = 1;\n{keyword}\n  nB = 2;\nENDIF;\n"
    index = _index(source)

    assert index.get(3).is_continuation is False


def test_while_end_starts_its_line():
    index = _index("WHILE( nA < 10 );\n    nA = nA + 1;\nEND;\n")

    assert index.get(3).is_continuation is False


def test_continuation_lines_carry_their_statement():
    index = _index(CANONICAL)

    statement = index.get(2).statement
    assert statement.kind is CstKind.ASSIGNMENT
    assert index.get(3).statement is statement
    assert index.get(5).statement is statement


# ---------------------------------------------------------------------------
# Delimiter depth
# ---------------------------------------------------------------------------


def test_delimiter_depth_counts_open_parentheses():
    index = _index(CANONICAL)

    assert index.get(2).delim_depth == 0
    assert index.get(3).delim_depth == 1
    assert index.get(5).delim_depth == 1
    assert index.get(5).starts_with_closer is True


def test_nested_calls_nest_the_depth():
    source = "sX = Outer(\n    Inner(\n        'a'\n    ),\n    'b'\n);\n"
    index = _index(source)

    assert index.get(2).delim_depth == 1  # Inner(
    assert index.get(3).delim_depth == 2  # 'a'
    assert index.get(4).delim_depth == 2  # ),
    assert index.get(6).delim_depth == 1  # );


# ---------------------------------------------------------------------------
# Block level
# ---------------------------------------------------------------------------


def test_block_level_follows_control_flow_nesting():
    source = "IF( a );\n    IF( b );\n        nX = 1;\n    ENDIF;\nENDIF;\n"
    index = _index(source)

    assert [index.get(line).block_level for line in range(1, 6)] == [0, 1, 2, 1, 0]


def test_else_and_elseif_sit_at_the_level_of_their_if():
    source = "IF( a );\n  nB=1;\nELSEIF( b );\n  nB=2;\nELSE;\n  nB=3;\nENDIF;\n"
    index = _index(source)

    assert [index.get(line).block_level for line in range(1, 8)] == [
        0,
        1,
        0,
        1,
        0,
        1,
        0,
    ]


def test_nested_else_is_dedented_to_its_own_if():
    source = (
        "IF( a );\n"
        "    IF( b );\n"
        "        nX = 1;\n"
        "    ELSE;\n"
        "        nX = 2;\n"
        "    ENDIF;\n"
        "ENDIF;\n"
    )
    assert _expected(source) == _actual(source)


# ---------------------------------------------------------------------------
# Expected indentation
# ---------------------------------------------------------------------------


def test_canonical_source_already_matches_its_expected_indentation():
    assert _expected(CANONICAL) == _actual(CANONICAL)


def test_hand_aligned_continuation_is_pulled_back_to_a_hanging_indent():
    source = (
        "IF( nA = 1 );\n    sValue = CellGetS( 'Cube',\n"
        "                       'Elem' );\nENDIF;\n"
    )

    assert _expected(source)[3] == 8
    assert _actual(source)[3] == 23


def test_closing_line_returns_to_the_level_that_opened_it():
    assert _expected(CANONICAL)[5] == 4  # `);` under `sValue`
    assert _expected(CANONICAL)[3] == 8  # arguments one level deeper


def test_operator_continuation_hangs_one_level():
    assert _expected("sX = 'aaa'\n    | 'bbb';\n")[2] == 4


def test_indent_size_scales_every_level():
    source = "IF( a );\n  sX = Call(\n    'v'\n  );\nENDIF;\n"

    assert _expected(source, indent_size=2) == _actual(source)


def test_expected_indent_is_none_for_lines_without_code():
    index = _index("nA = 1;\n\n# comment\n   \nnB = 2;\n")

    assert index.expected_indent(2, 4) is None  # blank
    assert index.expected_indent(3, 4) is None  # comment only
    assert index.expected_indent(4, 4) is None  # whitespace only
    assert index.expected_indent(99, 4) is None  # past the end


# ---------------------------------------------------------------------------
# Line classification
# ---------------------------------------------------------------------------


def test_blank_and_comment_lines_are_classified():
    index = _index("nA = 1;\n\n# comment\nnB = 2;\n")

    assert index.get(2).is_blank is True
    assert index.get(3).is_comment_only is True
    assert index.get(3).is_code is False
    assert index.get(4).is_code is True


def test_trailing_comment_does_not_make_the_line_comment_only():
    index = _index("nA = 1;  # why\n")

    assert index.get(1).is_comment_only is False
    assert index.get(1).is_code is True


def test_lines_inside_a_multiline_string_are_left_alone():
    """Reindenting inside a string literal would change its value."""
    index = _index("sM = 'line1\nline2\nline3';\nnA = 1;\n")

    assert index.get(1).is_code is True
    assert index.get(2).inside_multiline_token is True
    assert index.get(2).is_code is False
    assert index.expected_indent(2, 4) is None
    assert index.get(3).inside_multiline_token is True
    assert index.get(4).is_code is True


def test_indent_token_is_the_leading_whitespace():
    index = _index("IF( a );\n    nB = 1;\nENDIF;\n")

    info = index.get(2)
    assert info.indent_token.value == "    "
    assert info.indent_width == 4
    assert index.get(1).indent_token is None
    assert index.get(1).indent_width == 0


def test_iteration_yields_lines_in_order():
    index = _index("nA = 1;\nnB = 2;\nnC = 3;\n")

    assert [info.line for info in index] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------


def test_unparseable_statement_still_produces_a_line_model():
    index = _index("IF( a );\n    garbage %% ;\n    nB = 2;\nENDIF;\n")

    assert index.get(2).is_continuation is False
    assert index.get(2).statement.kind is CstKind.UNKNOWN_STATEMENT
    assert index.get(3).block_level == 1


def test_empty_source_has_no_lines():
    assert list(_index("")) == []
