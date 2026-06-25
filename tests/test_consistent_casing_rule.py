"""Tests for N230: VariablesConsistentCasingRule."""

from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.naming.consistent_casing_rule import VariablesConsistentCasingRule


def _lint(code: str, parameters=None, variables=None):
    """Helper to tokenize and lint code with the consistent casing rule."""
    tokens = Lexer(code).tokenize()
    rule = VariablesConsistentCasingRule()
    linter = Linter(rules=[rule])
    context = LintContext(parameters=parameters, variables=variables)
    return linter.lint(tokens, context)


# --- No issues ---


def test_consistent_casing_no_issues():
    """All references use the same casing."""
    code = "sName = 'hello';\nIF(sName @= 'hello');\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 0


def test_consistent_casing_single_variable():
    """A single variable reference has no inconsistency."""
    code = "nCount = 5;"
    issues = _lint(code)
    assert len(issues) == 0


def test_consistent_casing_multiple_variables_all_consistent():
    """Multiple distinct variables, all consistent."""
    code = "sName = 'x';\nnCount = 1;\nsResult = sName;"
    issues = _lint(code)
    assert len(issues) == 0


# --- Detects inconsistencies ---


def test_inconsistent_casing_simple():
    """Same variable with different casing is flagged."""
    code = "sName = 'hello';\nsname = 'world';"
    issues = _lint(code)
    assert len(issues) == 1
    assert "sname" in issues[0].message
    assert "sName" in issues[0].message


def test_inconsistent_casing_multiple_occurrences():
    """Multiple inconsistent references are all flagged."""
    code = "sName = 'a';\nsname = 'b';\nSNAME = 'c';"
    issues = _lint(code)
    assert len(issues) == 2
    assert all("sName" in issue.message for issue in issues)


def test_inconsistent_casing_in_expression():
    """Inconsistent casing in RHS expression is detected."""
    code = "sName = 'hello';\nsResult = SNAME | 'world';"
    issues = _lint(code)
    assert len(issues) == 1
    assert "SNAME" in issues[0].message
    assert "sName" in issues[0].message


def test_inconsistent_casing_in_function_call():
    """Inconsistent casing in function arguments is detected."""
    code = "sName = 'test';\nnLen = LONG(sname);"
    issues = _lint(code)
    assert len(issues) == 1
    assert "sname" in issues[0].message


def test_inconsistent_casing_in_condition():
    """Inconsistent casing in IF condition is detected."""
    code = "nCount = 1;\nIF(NCOUNT > 0);\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 1
    assert "NCOUNT" in issues[0].message


def test_inconsistent_casing_in_while_condition():
    """Inconsistent casing in WHILE condition is detected."""
    code = "nCount = 0;\nWHILE(ncount < 10);\nnCount = nCount + 1;\nEND;"
    issues = _lint(code)
    assert len(issues) == 1
    assert "ncount" in issues[0].message


# --- Parameters: metadata declaration is canonical ---


def test_parameter_casing_from_metadata():
    """Parameter casing from metadata is canonical; code reference with different casing is flagged."""
    code = "sResult = plogoutput;"
    issues = _lint(code, parameters=["pLogOutput"])
    assert len(issues) == 1
    assert "plogoutput" in issues[0].message
    assert "pLogOutput" in issues[0].message


def test_parameter_casing_consistent_with_metadata():
    """Parameter used with same casing as metadata declaration is fine."""
    code = "sResult = pLogOutput;"
    issues = _lint(code, parameters=["pLogOutput"])
    assert len(issues) == 0


def test_multiple_parameters_mixed():
    """Multiple parameters with mixed consistency."""
    code = "sResult = plogoutput | pfactor;"
    issues = _lint(code, parameters=["pLogOutput", "pFactor"])
    assert len(issues) == 2


# --- Variables: Metadata declaration is canonical ---


def test_variable_casing_from_metadata():
    """Data source variable casing from metadata.variables is canonical."""
    code = "sResult = vdimension;"
    issues = _lint(code, variables=["vDimension"])
    assert len(issues) == 1
    assert "vdimension" in issues[0].message
    assert "vDimension" in issues[0].message


def test_variable_casing_consistent_with_metadata():
    """Variable used with same casing as metadata declaration is fine."""
    code = "sResult = vDimension;"
    issues = _lint(code, variables=["vDimension"])
    assert len(issues) == 0


# --- Script variables: first occurrence is canonical ---


def test_script_variable_first_occurrence_wins():
    """For script variables, the first occurrence defines canonical casing."""
    code = "myVar = 1;\nmyvar = 2;"
    issues = _lint(code)
    assert len(issues) == 1
    assert "myvar" in issues[0].message
    assert "myVar" in issues[0].message


# --- Autofix ---


def test_autofix_replaces_with_canonical():
    """Autofix replaces inconsistent references with canonical casing."""
    code = "sName = 'hello';\nsname = 'world';"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].fix is not None
    assert issues[0].fix.old_value == "sname"
    assert issues[0].fix.new_value == "sName"

    fixed_code, num_fixes = apply_fixes(code, issues)
    assert num_fixes == 1
    assert "sname" not in fixed_code
    assert fixed_code == "sName = 'hello';\nsName = 'world';"


def test_autofix_multiple_occurrences():
    """Autofix fixes all inconsistent references."""
    code = "sName = 'a';\nsname = 'b';\nSNAME = 'c';"
    issues = _lint(code)
    fixed_code, num_fixes = apply_fixes(code, issues)
    assert num_fixes == 2
    assert fixed_code == "sName = 'a';\nsName = 'b';\nsName = 'c';"


def test_autofix_parameter_casing():
    """Autofix uses metadata declaration casing for parameters."""
    code = "sResult = plogoutput;"
    issues = _lint(code, parameters=["pLogOutput"])
    assert len(issues) == 1
    assert issues[0].fix.new_value == "pLogOutput"

    fixed_code, _ = apply_fixes(code, issues)
    assert "pLogOutput" in fixed_code


# --- Edge cases ---


def test_predefined_variables_excluded():
    """Predefined TM1 variables are not flagged."""
    code = "NValue = 5;\nnvalue = 3;"
    issues = _lint(code)
    # NValue is a predefined variable, should be excluded
    assert len(issues) == 0


def test_empty_code():
    """Empty code produces no issues."""
    issues = _lint("")
    assert len(issues) == 0


def test_no_variables():
    """Code with no variable references produces no issues."""
    code = "1 + 2;"
    issues = _lint(code)
    assert len(issues) == 0
