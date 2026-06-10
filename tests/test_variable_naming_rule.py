"""Tests for N220: VariableNamingRule."""


from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.naming.variable_naming_rule import VariableNamingRule


def test_variable_naming_valid():
    """Test that variables starting with 'v' pass validation."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # Valid variable names
    variables = ["vDimension", "vHierarchy", "vParent", "vChild"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have no issues
    assert len(errors) == 0


def test_variable_naming_invalid_no_v_prefix():
    """Test that variables not starting with 'v' are flagged."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # Invalid variable names (missing 'v' prefix)
    variables = ["Dimension", "Hierarchy", "Parent"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have 3 issues (one for each variable)
    assert len(errors) == 3
    assert all("must start with lowercase 'v'" in str(e) for e in errors)


def test_variable_naming_mixed():
    """Test with a mix of valid and invalid variable names."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # Mixed variable names
    variables = ["vDimension", "Hierarchy", "vParent", "Element"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have 2 issues (for "Hierarchy" and "Element")
    assert len(errors) == 2
    assert "Hierarchy" in str(errors[0]) or "Hierarchy" in str(errors[1])
    assert "Element" in str(errors[0]) or "Element" in str(errors[1])


def test_variable_naming_single_letter():
    """Test that single letter 'v' is flagged as too short."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # Single letter variable
    variables = ["v"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have 1 issue
    assert len(errors) == 1
    assert "too short" in str(errors[0])


def test_variable_naming_no_variables():
    """Test that when no variables are provided, no errors are raised."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # No variables
    errors = linter.lint(tokens, LintContext(variables=None))

    # Should have no issues
    assert len(errors) == 0


def test_variable_naming_empty_variables():
    """Test that empty variables list causes no errors."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = VariableNamingRule()
    linter = Linter(statement_rules=[rule])

    # Empty variables list
    errors = linter.lint(tokens, LintContext(variables=[]))

    # Should have no issues
    assert len(errors) == 0
