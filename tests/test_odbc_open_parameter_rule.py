"""Tests for ODBCOpenParameterRule."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.semantic.odbc_open_parameter_rule import ODBCOpenParameterRule


def _lint(code: str, parameters=None):
    tokens = Lexer(code).tokenize()
    return Linter(statement_rules=[ODBCOpenParameterRule()]).lint(
        tokens, LintContext(parameters=parameters)
    )


def test_odbcopen_defined_parameter_allowed():
    code = "ODBCOpen('DATASOURCE', 'root', pPassword);"
    errors = _lint(code, parameters=["pPassword"])
    assert errors == []


def test_odbcopen_undefined_parameter_flagged():
    code = "ODBCOpen('DATASOURCE', 'root', pPassword);"
    errors = _lint(code, parameters=["pOtherParam"])
    assert len(errors) == 1
    assert errors[0].rule_id == "S330"
    assert "not defined" in errors[0].message.lower()


def test_odbcopen_literal_password_flagged():
    # Synthetic test data — not real credentials
    code = "ODBCOpen('DATASOURCE', 'root', 'password123');"
    errors = _lint(code, parameters=[])
    assert len(errors) == 1
    assert errors[0].rule_id == "S330"
    assert "must be a ti parameter" in errors[0].message.lower()


def test_odbcopen_too_few_arguments():
    code = "ODBCOpen('DATASOURCE', 'root');"
    errors = _lint(code, parameters=[])
    assert len(errors) == 1
    assert errors[0].rule_id == "S330"
    assert "requires at least 3 arguments" in errors[0].message


def test_odbcopen_case_insensitive():
    code = "odbcopen('DATASOURCE', 'root', pPassword);"
    errors = _lint(code, parameters=["pPassword"])
    assert errors == []


def test_other_functions_not_checked():
    code = "LogOutput('INFO', pMessage);"
    errors = _lint(code, parameters=[])
    assert errors == []
