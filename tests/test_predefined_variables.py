"""Tests for TM1 predefined variables exclusion in naming rule."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.parser.parser import Parser
from linti.rules.naming.naming_rule import VariablePrefixRule


def test_predefined_datasource_variables_excluded():
    """Test that TM1 predefined Datasource variables are excluded from naming convention checks."""
    code = """
    DatasourceASCIIDecimalSeparator = ',';
    DatasourceType = 'NULL';
    DatasourceNameForServer = 'test';
    """

    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    rule = VariablePrefixRule()
    errors = []
    for stmt in ast.statements:
        errors.extend(rule.visit(stmt, LintContext()))

    # Should have no errors even though these don't follow naming conventions
    assert len(errors) == 0


def test_predefined_system_variables_excluded():
    """Test that TM1 predefined system variables are excluded from naming convention checks."""
    code = """
    MinorErrorLogMax = 100;
    NValue = 5;
    SValue = 'test';
    Value_Is_String = 1;
    OnMinorErrorDoItemSkip = 0;
    """

    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    rule = VariablePrefixRule()
    errors = []
    for stmt in ast.statements:
        errors.extend(rule.visit(stmt, LintContext()))

    # Should have no errors even though these don't follow naming conventions
    assert len(errors) == 0


def test_user_variables_still_checked():
    """Test that user variables are still checked for naming conventions."""
    code = """
    badNumeric = 123;
    badString = 'test';
    """

    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    rule = VariablePrefixRule()
    errors = []
    for stmt in ast.statements:
        errors.extend(rule.visit(stmt, LintContext()))

    # Should have 2 errors for bad naming
    assert len(errors) == 2
    assert "badNumeric" in errors[0].message
    assert "badString" in errors[1].message


def test_predefined_and_user_variables_mixed():
    """Test that predefined variables are excluded while user variables are still checked."""
    code = """
    DatasourceASCIIDecimalSeparator = ';';
    badVar = 123;
    DatasourceType = 'ODBC';
    nGoodVar = 456;
    """

    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    rule = VariablePrefixRule()
    errors = []
    for stmt in ast.statements:
        errors.extend(rule.visit(stmt, LintContext()))

    # Should have only 1 error for badVar
    assert len(errors) == 1
    assert "badVar" in errors[0].message
    assert "Numeric variables must start with 'n'" in errors[0].message


def test_predefined_variables_case_insensitive():
    """Test that predefined variable lookup is case-insensitive (TM1 is case-insensitive)."""
    code = """
    DATASOURCETYPE = 'ODBC';
    nvalue = 5;
    SVALUE = 'hello';
    VALUE_IS_STRING = 1;
    datasourcenameforserver = 'srv';
    """

    tokens = Lexer(code).tokenize()
    parser = Parser(tokens)
    ast = parser.parse()

    rule = VariablePrefixRule()
    errors = []
    for stmt in ast.statements:
        errors.extend(rule.visit(stmt, LintContext()))

    # All are predefined variables written in different casing — no errors expected
    assert len(errors) == 0, f"Expected no errors but got: {[e.message for e in errors]}"
