"""Tests for ExecuteCommandRule."""

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.execute_command_rule import ExecuteCommandRule


def _lint(code: str):
    tokens = Lexer(code).tokenize()
    return Linter(statement_rules=[ExecuteCommandRule()]).lint(tokens)


def test_executecommand_call_is_flagged():
    code = "ExecuteCommand('ls -la');"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "X110"
    assert "not allowed" in errors[0].message.lower()


def test_executecommand_case_insensitive():
    code = "executecommand('dir');"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "X110"


def test_executecommand_with_multiple_args():
    code = "ExecuteCommand('cmd', 'arg1', 'arg2');"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "X110"


def test_other_functions_allowed():
    code = "LogOutput('INFO', 'Message');"
    errors = _lint(code)
    assert errors == []


def test_executecommand_with_variable_arg():
    code = "ExecuteCommand(sCmd);"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "X110"
