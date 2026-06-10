"""Tests for NewLinePerStatementRule."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.format.newline_per_statement_rule import NewLinePerStatementRule


def _lint(code: str):
    tokens = Lexer(code).tokenize()
    rule = NewLinePerStatementRule()
    linter = Linter(rules=[rule])
    return linter.lint(tokens)


def test_single_statement_per_line_no_issue():
    code = "x = 1;\ny = 2;\n"
    issues = _lint(code)
    assert len(issues) == 0


def test_two_statements_on_same_line():
    code = "x = 1; y = 2;\n"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].rule_id == "F320"


def test_three_statements_on_same_line():
    code = "x = 1; y = 2; z = 3;\n"
    issues = _lint(code)
    assert len(issues) == 2


def test_statement_before_eof_no_issue():
    """No newline required when statement is immediately before procedure end."""
    code = "x = 1;"
    issues = _lint(code)
    assert len(issues) == 0


def test_if_block_statements_on_separate_lines():
    code = """\
IF (x = 1);
    y = 2;
    z = 3;
ENDIF;
"""
    issues = _lint(code)
    assert len(issues) == 0


def test_if_block_statements_on_same_line():
    code = """\
IF (x = 1);
    y = 2; z = 3;
ENDIF;
"""
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].rule_id == "F320"


def test_statement_followed_by_comment_no_issue():
    code = "x = 1; # comment\ny = 2;\n"
    issues = _lint(code)
    assert len(issues) == 0


def test_while_block_correct():
    code = """\
WHILE (n < 10);
    n = n + 1;
END;
"""
    issues = _lint(code)
    assert len(issues) == 0


def test_while_block_multiple_on_one_line():
    code = """\
WHILE (n < 10);
    n = n + 1; m = m + 1;
END;
"""
    issues = _lint(code)
    assert len(issues) == 1


def test_last_statement_before_eof_no_newline_needed():
    """Exception: statement directly before procedure end needs no newline."""
    code = "IF (1 = 1);\n    x = 1;\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 0


def test_issue_reports_correct_line():
    code = "a = 1;\nb = 2; c = 3;\n"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].line == 2


def test_empty_code_no_issue():
    code = ""
    issues = _lint(code)
    assert len(issues) == 0


def test_nested_if_correct():
    code = """\
IF (x = 1);
    IF (y = 2);
        z = 3;
    ENDIF;
ENDIF;
"""
    issues = _lint(code)
    assert len(issues) == 0


def test_function_call_on_same_line():
    code = "CellPutN(1, 'cube', 'e1'); CellPutN(2, 'cube', 'e2');\n"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].rule_id == "F320"


def test_end_of_procedure_context_disables_newline_rule():
    code = "x = 1; y = 2;"
    tokens = Lexer(code).tokenize()
    rule = NewLinePerStatementRule()
    linter = Linter(rules=[rule])

    # Simulate that this one-line snippet is exactly the procedure end in YAML.
    context = LintContext(block_start_line=10, block_end_line=10)
    issues = linter.lint(tokens, context)

    assert len(issues) == 0


def test_autofix_two_statements_on_same_line():
    """Fix inserts a newline between two statements on the same line."""
    from linti.cli.auto_fixer import apply_fixes

    code = "x = 1; y = 2;\n"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].fix is not None

    fixed, count = apply_fixes(code, issues)
    assert count == 1
    assert fixed == "x = 1;\ny = 2;\n"


def test_autofix_three_statements_on_same_line():
    """Fix splits three statements into separate lines."""
    from linti.cli.auto_fixer import apply_fixes

    code = "x = 1; y = 2; z = 3;\n"
    issues = _lint(code)
    assert len(issues) == 2

    fixed, count = apply_fixes(code, issues)
    assert count == 2
    assert fixed == "x = 1;\ny = 2;\nz = 3;\n"


def test_autofix_no_whitespace_between_statements():
    """Fix inserts newline even when no space exists after semicolon."""
    from linti.cli.auto_fixer import apply_fixes

    code = "x = 1;y = 2;\n"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].fix is not None

    fixed, count = apply_fixes(code, issues)
    assert count == 1
    assert fixed == "x = 1;\ny = 2;\n"
