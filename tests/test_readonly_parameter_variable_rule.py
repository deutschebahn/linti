"""Tests for S210: ReadOnlyParameterVariableRule."""


from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.semantic.readonly_parameter_variable_rule import (
    ReadOnlyParameterVariableRule,
)


def test_readonly_assignment_to_local_variable():
    """Test that assignments to local variables (not parameters/variables) are allowed."""
    code = """
    nValue = 5;
    sMessage = 'Hello';
    cRate = 1.5;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    parameters = ["pLogOutput"]
    variables = ["vDimension"]
    errors = linter.lint(
        tokens, LintContext(parameters=parameters, variables=variables)
    )

    # Should have no issues (not assigning to parameters or variables)
    assert len(errors) == 0


def test_readonly_assignment_to_parameter():
    """Test that assignments to parameters are flagged."""
    code = """
    pLogOutput = 0;
    sMessage = 'test';
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    parameters = ["pLogOutput", "pFactor"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have 1 issue (pLogOutput assignment)
    assert len(errors) == 1
    assert "pLogOutput" in str(errors[0])
    assert "must not be modified" in str(errors[0])


def test_readonly_assignment_to_variable():
    """Test that assignments to data source variables are flagged."""
    code = """
    vDimension = 'NewDim';
    nValue = 5;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    variables = ["vDimension", "vHierarchy"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have 1 issue (vDimension assignment)
    assert len(errors) == 1
    assert "vDimension" in str(errors[0])
    assert "must not be modified" in str(errors[0])


def test_readonly_multiple_violations():
    """Test multiple assignments to parameters and variables."""
    code = """
    pLogOutput = 0;
    vDimension = 'NewDim';
    pFactor = 25;
    vHierarchy = 'NewHier';
    nValue = 5;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    parameters = ["pLogOutput", "pFactor"]
    variables = ["vDimension", "vHierarchy"]
    errors = linter.lint(
        tokens, LintContext(parameters=parameters, variables=variables)
    )

    # Should have 4 issues
    assert len(errors) == 4
    assert any("pLogOutput" in str(e) for e in errors)
    assert any("pFactor" in str(e) for e in errors)
    assert any("vDimension" in str(e) for e in errors)
    assert any("vHierarchy" in str(e) for e in errors)


def test_readonly_reading_parameter_is_allowed():
    """Test that reading from parameters (not assigning to them) is allowed."""
    code = """
    cLogOutput = pLogOutput;
    nValue = pFactor * 2;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    parameters = ["pLogOutput", "pFactor"]
    errors = linter.lint(tokens, LintContext(parameters=parameters))

    # Should have no issues (reading from parameters, not writing to them)
    assert len(errors) == 0


def test_readonly_reading_variable_is_allowed():
    """Test that reading from variables (not assigning to them) is allowed."""
    code = """
    sDim = vDimension;
    sHier = vHierarchy;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    variables = ["vDimension", "vHierarchy"]
    errors = linter.lint(tokens, LintContext(variables=variables))

    # Should have no issues (reading from variables, not writing to them)
    assert len(errors) == 0


def test_readonly_no_parameters_or_variables():
    """Test that when no parameters/variables are provided, no errors are raised."""
    code = """
    pLogOutput = 0;
    vDimension = 'NewDim';
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    errors = linter.lint(tokens, LintContext(parameters=None, variables=None))

    # Should have no issues (no parameters/variables defined)
    assert len(errors) == 0


def test_readonly_empty_parameters_and_variables():
    """Test that empty lists cause no errors."""
    code = """
    pLogOutput = 0;
    vDimension = 'NewDim';
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    errors = linter.lint(tokens, LintContext(parameters=[], variables=[]))

    # Should have no issues (empty lists)
    assert len(errors) == 0


def test_readonly_parameter_only():
    """Test with only parameters defined (no variables)."""
    code = """
    pLogOutput = 0;
    nValue = 5;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    parameters = ["pLogOutput"]
    errors = linter.lint(tokens, LintContext(parameters=parameters, variables=None))

    # Should have 1 issue (pLogOutput)
    assert len(errors) == 1
    assert "pLogOutput" in str(errors[0])


def test_readonly_variable_only():
    """Test with only variables defined (no parameters)."""
    code = """
    vDimension = 'NewDim';
    nValue = 5;
    """
    tokens = Lexer(code).tokenize()

    rule = ReadOnlyParameterVariableRule()
    linter = Linter(statement_rules=[rule])

    variables = ["vDimension"]
    errors = linter.lint(tokens, LintContext(parameters=None, variables=variables))

    # Should have 1 issue (vDimension)
    assert len(errors) == 1
    assert "vDimension" in str(errors[0])
