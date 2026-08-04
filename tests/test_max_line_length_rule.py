"""Tests for F330 – Maximum Line Length.

The interesting half of this rule is the fix: it rewrites code rather than
whitespace, so the tests care about three things — that the output says the
same thing, that it is laid out the way F310 wants, and that a second pass
changes nothing.
"""

import pytest

from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.format.max_line_length_rule import MaxLineLengthRule
from linti.rules.rule_factory import create_rules


def _linter(limit: int = 40) -> Linter:
    return Linter(statement_rules=[MaxLineLengthRule(limit=limit)])


def _lint(code: str, limit: int = 40):
    return _linter(limit).lint(Lexer(code).tokenize(), source=code)


def _fix(code: str, limit: int = 40) -> str:
    fixed, _ = apply_fixes_iteratively(code, _linter(limit))
    return fixed


def _all_format_rules(limit: int = 40) -> Linter:
    cfg = Config()
    cfg.rules.max_line_length.limit = limit
    return Linter(*create_rules(cfg, select="F"))


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_short_lines_are_accepted():
    assert _lint("nA = 1;\nnB = 2;\n") == []


def test_line_at_exactly_the_limit_is_accepted():
    padding = 40 - len("s = '';")
    code = "s = '" + "x" * padding + "';\n"
    assert len(code.rstrip("\n")) == 40

    assert _lint(code) == []


def test_line_one_over_the_limit_is_reported():
    padding = 41 - len("s = '';")
    code = "s = '" + "x" * padding + "';\n"

    assert len(_lint(code)) == 1


def test_line_over_the_limit_is_reported():
    code = "sValue = CellGetS( 'Cube', 'AAAA', 'BBBB', 'CCCC' );\n"
    issues = _lint(code)

    assert len(issues) == 1
    assert issues[0].rule_id == "F330"
    assert issues[0].line == 1
    assert "Line exceeds 40 characters (52)" in issues[0].message


def test_each_long_line_is_reported():
    code = "nA = 1;\n" + "sX = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';\n" * 2
    issues = _lint(code)

    assert [i.line for i in issues] == [2, 3]


def test_long_comment_line_is_reported_without_a_fix():
    code = "# " + "x" * 60 + "\nnA = 1;\n"
    issues = _lint(code)

    assert len(issues) == 1
    assert issues[0].fix is None


def test_issue_position_points_at_the_start_of_its_line():
    code = "nA = 1;\nsX = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';\n"
    issues = _lint(code)

    assert code[issues[0].position :].startswith("sX = ")


# ---------------------------------------------------------------------------
# Rewrapping calls
# ---------------------------------------------------------------------------


def test_long_call_is_broken_at_its_arguments():
    code = "sValue = CellGetS( 'Cube', 'AAAA', 'BBBB', 'CCCC' );\n"

    assert _fix(code) == (
        "sValue = CellGetS(\n    'Cube',\n    'AAAA',\n    'BBBB',\n    'CCCC'\n);\n"
    )


def test_rewrapping_respects_the_enclosing_block_indent():
    code = "IF( a );\n    sValue = CellGetS( 'Cube', 'AAAA', 'BBBB' );\nENDIF;\n"

    assert _fix(code) == (
        "IF( a );\n"
        "    sValue = CellGetS(\n"
        "        'Cube',\n"
        "        'AAAA',\n"
        "        'BBBB'\n"
        "    );\n"
        "ENDIF;\n"
    )


def test_nested_calls_only_break_as_far_as_needed():
    """The inner call fits once the outer one is wrapped, so it stays flat."""
    code = (
        "IF( a );\n    sX = Outer( Inner( 'aaaa', 'bbbb' ), 'cccc', 'dddd' );\nENDIF;\n"
    )

    assert _fix(code) == (
        "IF( a );\n"
        "    sX = Outer(\n"
        "        Inner( 'aaaa', 'bbbb' ),\n"
        "        'cccc',\n"
        "        'dddd'\n"
        "    );\n"
        "ENDIF;\n"
    )


def test_inner_call_breaks_too_when_it_still_does_not_fit():
    code = "sX = Outer( Inner( 'aaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbb' ), 'cc' );\n"

    assert _fix(code, limit=30) == (
        "sX = Outer(\n"
        "    Inner(\n"
        "        'aaaaaaaaaaaaaaa',\n"
        "        'bbbbbbbbbbbbbbb'\n"
        "    ),\n"
        "    'cc'\n"
        ");\n"
    )


def test_expression_statement_call_is_rewrapped():
    code = "ExecuteProcess( 'SomeProcess', 'pParam1', 'pParam2', 'pP3' );\n"

    assert _fix(code) == (
        "ExecuteProcess(\n"
        "    'SomeProcess',\n"
        "    'pParam1',\n"
        "    'pParam2',\n"
        "    'pP3'\n"
        ");\n"
    )


# ---------------------------------------------------------------------------
# Rewrapping conditions and operator chains
# ---------------------------------------------------------------------------


def test_long_if_condition_breaks_before_each_operator():
    code = "IF( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\n    nX = 1;\nENDIF;\n"

    assert _fix(code, limit=30) == (
        "IF(\n"
        "    nA = 1\n"
        "    & nB = 2\n"
        "    & nC = 3\n"
        "    & nD = 4\n"
        ");\n"
        "    nX = 1;\n"
        "ENDIF;\n"
    )


def test_operator_chain_keeps_its_operands_together():
    """`nA = 1` must not be split just because the chain around it is."""
    fixed = _fix("IF( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\nENDIF;\n", limit=30)

    assert "    nA = 1\n" in fixed
    assert "\n    = 1" not in fixed


def test_while_condition_is_rewrapped():
    code = "WHILE( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\n    nX = 1;\nEND;\n"
    fixed = _fix(code, limit=30)

    assert fixed.startswith("WHILE(\n    nA = 1\n    & nB = 2\n")
    assert fixed.endswith(");\n    nX = 1;\nEND;\n")


def test_top_level_concatenation_hangs_one_level():
    code = "sX = 'aaaaaaaaaa' | 'bbbbbbbbbb' | 'cccccccccc';\n"

    assert _fix(code, limit=30) == (
        "sX = 'aaaaaaaaaa'\n    | 'bbbbbbbbbb'\n    | 'cccccccccc';\n"
    )


def test_grouping_parentheses_break_and_close_at_their_own_level():
    """A grouped sub-expression closes back where the line that opened it was."""
    code = "nX = (nAaaaaaaaaa + nBbbbbbbbbb + nCcccccccc) * nD;\n"

    assert _fix(code, limit=30) == (
        "nX = (\n    nAaaaaaaaaa\n    + nBbbbbbbbbb\n    + nCcccccccc\n)\n    * nD;\n"
    )


def test_grouped_conditions_stay_whole_when_they_fit():
    code = "IF( (nA = 1 & nB = 2) % (nC = 3 & nD = 4) );\n    nX = 1;\nENDIF;\n"
    fixed = _fix(code, limit=30)

    assert "    (nA = 1 & nB = 2)\n" in fixed
    assert "    % (nC = 3 & nD = 4)\n" in fixed


def test_elseif_condition_is_rewrapped_not_the_leading_if():
    code = (
        "IF( a );\n"
        "    nX = 1;\n"
        "ELSEIF( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\n"
        "    nX = 2;\n"
        "ENDIF;\n"
    )
    fixed = _fix(code, limit=30)

    assert fixed.startswith("IF( a );\n    nX = 1;\nELSEIF(\n")
    assert "    & nB = 2\n" in fixed


# ---------------------------------------------------------------------------
# Lines that must not be rewritten
# ---------------------------------------------------------------------------


def test_unbreakable_long_literal_is_reported_without_a_fix():
    code = "sX = '" + "a" * 60 + "';\n"
    issues = _lint(code)

    assert len(issues) == 1
    assert issues[0].fix is None
    assert _fix(code) == code


def test_statement_containing_a_comment_is_not_rewrapped():
    """Moving a comment could comment out the code that follows it.

    TI only starts a comment at the beginning of a statement, so one can land
    *inside* a statement's span only when that statement is already wrapped.
    """
    code = (
        "sX = CellGetS( 'AVeryLongCubeNameHere', 'ElementOne', 'ElementTwo',\n"
        "# explain the next argument\n"
        "'ElementThree' );\n"
    )
    issues = _lint(code)

    assert [i.fix is not None for i in issues] == [False]
    assert _fix(code) == code


def test_trailing_comment_after_the_semicolon_stays_put():
    """It sits outside the statement, so rewrapping around it is safe."""
    code = (
        "sX = CellGetS( 'AVeryLongCubeNameHere', 'ElementOne', 'ElemTwo' );  # note\n"
    )

    assert _fix(code) == (
        "sX = CellGetS(\n"
        "    'AVeryLongCubeNameHere',\n"
        "    'ElementOne',\n"
        "    'ElemTwo'\n"
        ");  # note\n"
    )


def test_statement_containing_a_multiline_string_is_not_rewrapped():
    """The line breaks inside the literal are part of its value."""
    code = "sX = Concat( 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'line1\nline2' );\n"

    assert _fix(code) == code


def test_unparseable_statement_is_reported_without_a_fix():
    code = "garbage %% " + "x" * 50 + " ;\n"
    issues = _lint(code)

    assert len(issues) == 1
    assert issues[0].fix is None


def test_two_long_lines_in_one_statement_yield_a_single_rewrite():
    code = (
        "sX = CellGetS( 'Cubeaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',\n"
        "               'Elemaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' );\n"
    )
    issues = _lint(code)

    assert len(issues) == 2
    assert [i.fix is not None for i in issues] == [True, False]


# ---------------------------------------------------------------------------
# Idempotence and interaction with the other formatting rules
# ---------------------------------------------------------------------------


REWRAP_CASES = [
    "sValue = CellGetS( 'Cube', 'AAAA', 'BBBB', 'CCCC' );\n",
    "IF( a );\n    sValue = CellGetS( 'Cube', 'AAAA', 'BBBB' );\nENDIF;\n",
    "IF( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\n    nX = 1;\nENDIF;\n",
    "sX = Outer( Inner( 'aaaaaaaaaaa', 'bbbbbbbbbbb' ), 'cccc' );\n",
    "sX = 'aaaaaaaaaa' | 'bbbbbbbbbb' | 'cccccccccc';\n",
    "iF(a=1);\nsX=CellGetS('Cube','AAAA','BBBB','CCCC');\nendif;\n",
    "nX = (nAaaaaaaaaa + nBbbbbbbbbb + nCcccccccc) * nD;\n",
    "IF( (nA = 1 & nB = 2) % (nC = 3 & nD = 4) );\n    nX = 1;\nENDIF;\n",
    "WHILE( nA = 1 & nB = 2 & nC = 3 & nD = 4 );\n    nX = 1;\nEND;\n",
]


@pytest.mark.parametrize("code", REWRAP_CASES)
def test_fixing_twice_changes_nothing_the_second_time(code):
    once = _fix(code, limit=30)

    assert _fix(once, limit=30) == once


@pytest.mark.parametrize("code", REWRAP_CASES)
def test_rewrapped_output_satisfies_every_formatting_rule(code):
    """F330's layout is F310's layout, so the two never fight."""
    linter = _all_format_rules(limit=30)
    fixed, _ = apply_fixes_iteratively(code, linter)

    remaining = linter.lint(Lexer(fixed).tokenize(), source=fixed)
    assert remaining == [], [(i.rule_id, i.message) for i in remaining]


@pytest.mark.parametrize("code", REWRAP_CASES)
def test_rewrapping_preserves_the_tokens(code):
    """Layout may change; what the code says may not."""
    before = [
        (t.type, t.value)
        for t in Lexer(code).tokenize()
        if t.type.name not in ("WHITESPACE", "NEWLINE")
    ]
    after = [
        (t.type, t.value)
        for t in Lexer(_fix(code, limit=30)).tokenize()
        if t.type.name not in ("WHITESPACE", "NEWLINE")
    ]

    assert before == after


def test_string_contents_survive_rewrapping():
    code = "sX = Concat( 'it''s', 'a  b', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' );\n"
    fixed = _fix(code, limit=30)

    assert "'it''s'" in fixed
    assert "'a  b'" in fixed


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_from_config_reads_the_limit():
    (rule,) = MaxLineLengthRule.from_config({"limit": 80})

    assert rule.limit == 80


def test_from_config_defaults_to_120():
    (rule,) = MaxLineLengthRule.from_config({})

    assert rule.limit == 120


def test_rule_is_enabled_by_default():
    _, statement_rules = create_rules(Config())

    assert any(r.RULE_ID == "F330" for r in statement_rules)


def test_rule_can_be_disabled():
    cfg = Config()
    cfg.rules.max_line_length.enabled = False
    _, statement_rules = create_rules(cfg)

    assert not any(r.RULE_ID == "F330" for r in statement_rules)


def test_rule_id():
    assert MaxLineLengthRule().RULE_ID == "F330"


# ---------------------------------------------------------------------------
# The reflow engine's own guards
# ---------------------------------------------------------------------------


def _statement_node(code: str):
    from linti.parser.parser import Parser

    tokens = Lexer(code).tokenize()
    program = Parser(tokens).parse()
    return program.statements[0].cst, tokens


def test_can_reflow_refuses_a_span_holding_a_comment():
    from linti.cst.layout import Reflow

    code = "sX = Concat( 'a',\n# why\n'b' );\n"
    node, tokens = _statement_node(code)

    assert Reflow(tokens, code, limit=10).can_reflow(node) is False


def test_can_reflow_ignores_a_comment_outside_the_span():
    from linti.cst.layout import Reflow

    code = "sX = Concat( 'a' );  # why\n"
    node, tokens = _statement_node(code)

    assert Reflow(tokens, code, limit=10).can_reflow(node) is True


def test_can_reflow_refuses_a_span_holding_a_multiline_string():
    from linti.cst.layout import Reflow

    code = "sX = Concat( 'a', 'line1\nline2' );\n"
    node, tokens = _statement_node(code)

    assert Reflow(tokens, code, limit=10).can_reflow(node) is False


def test_can_reflow_accepts_ordinary_code():
    from linti.cst.layout import Reflow

    code = "sX = Concat( 'a', 'b' );\n"
    node, tokens = _statement_node(code)

    assert Reflow(tokens, code, limit=10).can_reflow(node) is True


def test_render_returns_none_when_the_layout_would_not_change():
    """A fix that rewrites a span to itself would spin the auto-fix loop."""
    from linti.cst.layout import Reflow

    code = "sX = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';\n"
    node, tokens = _statement_node(code)

    assert Reflow(tokens, code, limit=10).render(node, 0) is None


def test_reflow_target_walks_up_to_the_nearest_reflowable_construct():
    from linti.cst.layout import reflow_target
    from linti.cst.node import CstKind

    code = "IF( nA = 1 );\n    nX = 1;\nENDIF;\n"
    tokens = Lexer(code).tokenize()
    from linti.parser.parser import Parser

    program = Parser(tokens).parse()
    inside_condition = program.cst.covering_node(
        next(i for i, t in enumerate(tokens) if t.value == "nA")
    )

    assert reflow_target(inside_condition).kind is CstKind.IF_HEADER


def test_reflow_target_is_none_outside_any_reflowable_construct():
    from linti.cst.layout import reflow_target
    from linti.parser.parser import Parser

    code = "garbage %% ;\n"
    tokens = Lexer(code).tokenize()
    program = Parser(tokens).parse()

    assert reflow_target(program.statements[0].cst) is None
