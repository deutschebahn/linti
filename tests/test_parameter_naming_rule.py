"""Tests for N210: ParameterNamingRule."""


from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.naming.parameter_naming_rule import ParameterNamingRule


def test_parameter_naming_valid():
    """Test that parameters starting with 'p' pass validation."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # Valid parameter names
    parameters = ["pLogOutput", "pFactor", "pEnableDebugging"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have no issues
    assert len(errors) == 0


def test_parameter_naming_invalid_no_p_prefix():
    """Test that parameters not starting with 'p' are flagged."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # Invalid parameter names (missing 'p' prefix)
    parameters = ["LogOutput", "Factor", "EnableDebugging"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have 3 issues (one for each parameter)
    assert len(errors) == 3
    assert all("must start with lowercase 'p'" in str(e) for e in errors)


def test_parameter_naming_mixed():
    """Test with a mix of valid and invalid parameter names."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # Mixed parameter names
    parameters = ["pLogOutput", "Factor", "pEnableDebugging", "Output"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have 2 issues (for "Factor" and "Output")
    assert len(errors) == 2
    assert "Factor" in str(errors[0]) or "Factor" in str(errors[1])
    assert "Output" in str(errors[0]) or "Output" in str(errors[1])


def test_parameter_naming_single_letter():
    """Test that single letter 'p' is flagged as too short."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # Single letter parameter
    parameters = ["p"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have 1 issue
    assert len(errors) == 1
    assert "too short" in str(errors[0])


def test_parameter_naming_no_parameters():
    """Test that when no parameters are provided, no errors are raised."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # No parameters
    errors = linter.lint(tokens, LintContext(parameters=None))

    # Should have no issues
    assert len(errors) == 0


def test_parameter_naming_empty_parameters():
    """Test that empty parameters list causes no errors."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = ParameterNamingRule()
    linter = Linter(statement_rules=[rule])

    # Empty parameters list
    errors = linter.lint(tokens, LintContext(parameters=[]))

    # Should have no issues
    assert len(errors) == 0
