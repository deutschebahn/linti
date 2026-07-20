"""Tests for ProcessCallLiteralRule."""

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.process_call_literal_rule import ProcessCallLiteralRule


def _lint(code: str):
    tokens = Lexer(code).tokenize()
    return Linter(statement_rules=[ProcessCallLiteralRule()]).lint(tokens)


def test_runprocess_literal_first_arg_is_allowed():
    code = "RunProcess('pLoad_Customer');"
    errors = _lint(code)
    assert errors == []


def test_executeprocess_literal_first_arg_is_allowed():
    code = "ExecuteProcess('pLoad_Product');"
    errors = _lint(code)
    assert errors == []


def test_runprocess_variable_first_arg_is_flagged():
    code = "RunProcess(pProcessName);"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "C310"
    assert "first argument" in errors[0].message.lower()


def test_executeprocess_variable_first_arg_is_flagged():
    code = "ExecuteProcess(sProcess);"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "C310"


def test_runprocess_no_first_arg_is_flagged():
    code = "RunProcess();"
    errors = _lint(code)
    assert len(errors) == 1
    assert errors[0].rule_id == "C310"


def test_other_function_not_checked():
    code = "CellPutN(1, 'Cube', 'Dim1');"
    errors = _lint(code)
    assert errors == []
