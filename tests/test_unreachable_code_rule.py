"""Tests for UnreachableCodeRule (C140)."""

import pytest

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.unreachable_code_rule import UnreachableCodeRule

TERMINATORS = [
    "ProcessQuit",
    "ItemReject",
    "ProcessBreak",
    "ProcessError",
    "ProcessRollback",
    "Break",
]


def _lint(code):
    tokens = Lexer(code).tokenize()
    return Linter(statement_rules=[UnreachableCodeRule()]).lint(tokens)


@pytest.mark.parametrize("func", TERMINATORS)
def test_terminator_at_end_of_if_is_valid(func):
    """A terminator as the last statement in an IF block is fine."""
    code = f"IF (nValue = 1);\n    nResult = 10;\n    {func}();\nENDIF;\n"
    assert _lint(code) == []


@pytest.mark.parametrize("func", TERMINATORS)
def test_unreachable_after_terminator_in_if(func):
    """Code after a terminator in an IF block is flagged."""
    code = f"IF (nValue = 1);\n    {func}();\n    nResult = 10;\nENDIF;\n"
    errors = _lint(code)
    assert len(errors) == 1
    assert "C140" in errors[0].rule_id
    assert "unreachable" in errors[0].message.lower()


def test_unreachable_after_terminator_in_else():
    """Code after a terminator in an ELSE block is flagged, with a count."""
    code = (
        "IF (nValue = 1);\n    nResult = 10;\n"
        "ELSE;\n    ProcessQuit();\n    nResult = 20;\n    sMsg = 'x';\nENDIF;\n"
    )
    errors = _lint(code)
    assert len(errors) == 1
    assert "C140" in errors[0].rule_id
    assert "2 unreachable statement" in errors[0].message


def test_unreachable_in_while_body():
    """Code after Break in a WHILE body is flagged."""
    code = "WHILE (nValue = 1);\n    Break();\n    nResult = 10;\nEND;\n"
    errors = _lint(code)
    assert len(errors) == 1
    assert "C140" in errors[0].rule_id


def test_terminator_in_main_body_is_not_flagged():
    """The unreachable-code rule only inspects block bodies, not the main body."""
    code = "ProcessQuit();\nnResult = 10;\n"
    assert _lint(code) == []


def test_case_insensitive():
    """Terminator matching is case-insensitive."""
    code = "IF (nValue = 1);\n    processquit();\n    nResult = 10;\nENDIF;\n"
    errors = _lint(code)
    assert len(errors) == 1
    assert "C140" in errors[0].rule_id


def test_without_parens():
    """A terminator without parentheses is recognised."""
    code = "IF (nValue = 1);\n    ProcessQuit;\n    nResult = 10;\nENDIF;\n"
    errors = _lint(code)
    assert len(errors) == 1
    assert "C140" in errors[0].rule_id


def test_multiple_blocks():
    """Unreachable code in both IF and ELSE branches is flagged separately."""
    code = (
        "IF (nValue = 1);\n    ProcessQuit();\n    nResult = 10;\n"
        "ELSE;\n    ProcessQuit();\n    nResult = 20;\nENDIF;\n"
    )
    errors = _lint(code)
    assert len(errors) == 2
    assert all("C140" in err.rule_id for err in errors)
