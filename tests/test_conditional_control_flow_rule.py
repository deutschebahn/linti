"""Tests for ConditionalControlFlowRule (C120)."""

import pytest

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.conditional_control_flow_rule import (
    ConditionalControlFlowRule,
)

# The full set of flow-altering statements the rule guards.
CONTROL_FLOW = [
    "ProcessQuit",
    "ItemReject",
    "ProcessBreak",
    "ProcessError",
    "ProcessExitByChoreRollback",
    "ProcessExitByProcessRollback",
    "ProcessRollback",
    "Break",
]


def _lint(code):
    tokens = Lexer(code).tokenize()
    return Linter(statement_rules=[ConditionalControlFlowRule()]).lint(tokens)


@pytest.mark.parametrize("func", CONTROL_FLOW)
def test_flagged_in_main_body(func):
    """Each control-flow statement in the main body is flagged."""
    errors = _lint(f"nValue = 5;\n{func}();\n")
    assert len(errors) == 1
    assert "C120" in errors[0].rule_id
    assert func in errors[0].message


@pytest.mark.parametrize("func", CONTROL_FLOW)
def test_allowed_inside_if(func):
    """Each control-flow statement inside an IF block is allowed."""
    errors = _lint(f"IF (nValue = 1);\n    {func}();\nENDIF;\n")
    assert errors == []


@pytest.mark.parametrize("func", CONTROL_FLOW)
def test_allowed_inside_else(func):
    """Each control-flow statement inside an ELSE block is allowed."""
    code = f"IF (nValue = 1);\n    nResult = 10;\nELSE;\n    {func}();\nENDIF;\n"
    assert _lint(code) == []


@pytest.mark.parametrize("func", CONTROL_FLOW)
def test_flagged_in_bare_while(func):
    """A bare WHILE loop (no enclosing IF) is not a valid guard."""
    errors = _lint(f"WHILE (nValue = 1);\n    {func}();\nEND;\n")
    assert len(errors) == 1
    assert "C120" in errors[0].rule_id


def test_allowed_in_if_nested_in_while():
    """An IF inside a WHILE is a valid guard."""
    code = "WHILE (nValue = 1);\n    IF (nOther = 2);\n        Break();\n    ENDIF;\nEND;\n"
    assert _lint(code) == []


def test_case_insensitive():
    """Matching is case-insensitive."""
    errors = _lint("processbreak();\n")
    assert len(errors) == 1
    assert "C120" in errors[0].rule_id


def test_without_parens_flagged():
    """A statement without parentheses is still flagged in the main body."""
    errors = _lint("ProcessBreak;\n")
    assert len(errors) == 1
    assert "C120" in errors[0].rule_id


def test_without_parens_allowed_in_if():
    """A statement without parentheses inside an IF is allowed."""
    assert _lint("IF (nValue = 1);\n    ProcessBreak;\nENDIF;\n") == []


def test_nested_if_is_a_guard():
    """A control-flow statement in a nested IF is guarded."""
    code = "IF (nValue = 1);\n    IF (nOther = 2);\n        ProcessQuit();\n    ENDIF;\nENDIF;\n"
    assert _lint(code) == []


def test_multiple_statements_in_main_body():
    """Multiple un-guarded statements are each flagged."""
    errors = _lint("ProcessBreak();\nItemReject();\n")
    assert len(errors) == 2
    assert all("C120" in err.rule_id for err in errors)
