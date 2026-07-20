"""Tests for EmptyBlockRule (C110)."""

from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.semantic.empty_block_rule import EmptyBlockRule


def _linter() -> Linter:
    return Linter(statement_rules=[EmptyBlockRule()])


def _lint(code: str):
    return _linter().lint(Lexer(code).tokenize(), source=code)


def _fix(code: str):
    return apply_fixes_iteratively(code, _linter())


# --- Detection: valid (no issues) ---


def test_if_with_code_is_valid():
    code = "IF (x = 1);\n    y = 2;\nENDIF;"
    assert _lint(code) == []


def test_else_with_code_is_valid():
    code = "IF (x = 1);\n    y = 2;\nELSE;\n    z = 3;\nENDIF;"
    assert _lint(code) == []


def test_while_with_code_is_valid():
    code = "WHILE (x < 5);\n    x = x + 1;\nEND;"
    assert _lint(code) == []


def test_nested_block_with_code_is_valid():
    code = "IF (x = 1);\n    IF (y = 2);\n        z = 3;\n    ENDIF;\nENDIF;"
    assert _lint(code) == []


# --- Detection: empty blocks ---


def test_empty_if_is_flagged():
    issues = _lint("IF (x = 1);\nENDIF;")
    assert len(issues) == 1
    assert issues[0].rule_id == "C110"
    assert "IF block" in issues[0].message
    assert issues[0].fix is None  # IF blocks are never auto-fixed


def test_empty_else_is_flagged():
    issues = _lint("IF (x = 1);\n    y = 2;\nELSE;\nENDIF;")
    assert len(issues) == 1
    assert issues[0].rule_id == "C110"
    assert "ELSE block" in issues[0].message


def test_empty_elseif_is_flagged():
    issues = _lint("IF (x = 1);\n    y = 2;\nELSEIF (x = 2);\nENDIF;")
    assert len(issues) == 1
    assert "ELSEIF block" in issues[0].message


def test_empty_while_is_flagged():
    issues = _lint("WHILE (x < 5);\nEND;")
    assert len(issues) == 1
    assert "WHILE block" in issues[0].message
    assert issues[0].fix is not None  # empty WHILE is auto-fixable


def test_empty_then_with_else_flags_only_then():
    issues = _lint("IF (x = 1);\nELSE;\n    z = 3;\nENDIF;")
    assert len(issues) == 1
    assert "IF block" in issues[0].message


def test_nested_empty_inner_if_flagged_once():
    code = "IF (x = 1);\n    IF (y = 2);\n    ENDIF;\nENDIF;"
    issues = _lint(code)
    # Only the inner IF is empty; the outer one contains the inner IF.
    assert len(issues) == 1
    assert "IF block" in issues[0].message


# --- Comments-only: flagged but not auto-fixable ---


def test_else_with_only_comment_is_flagged_without_fix():
    issues = _lint("IF (x = 1);\n    y = 2;\nELSE;\n    # todo\nENDIF;")
    assert len(issues) == 1
    assert "only comments" in issues[0].message
    assert issues[0].fix is None


def test_while_with_only_comment_is_flagged_without_fix():
    issues = _lint("WHILE (x < 5);\n    # todo\nEND;")
    assert len(issues) == 1
    assert "only comments" in issues[0].message
    assert issues[0].fix is None


# --- Auto-fix ---


def test_autofix_removes_empty_else():
    code = "IF (x = 1);\n    y = 2;\nELSE;\nENDIF;"
    fixed, n = _fix(code)
    assert n == 1
    assert fixed == "IF (x = 1);\n    y = 2;\nENDIF;"


def test_autofix_removes_empty_elseif_last():
    code = "IF (x = 1);\n    y = 2;\nELSEIF (x = 2);\nENDIF;"
    fixed, n = _fix(code)
    assert n == 1
    assert fixed == "IF (x = 1);\n    y = 2;\nENDIF;"


def test_autofix_keeps_empty_elseif_followed_by_elseif():
    """An empty ELSEIF before another ELSEIF must NOT be removed.

    Removing it would let the swallowed condition fall through to the next
    ELSEIF and change behaviour, so it is reported only.
    """
    code = (
        "IF (x = 1);\n    y = 2;\nELSEIF (x = 2);\nELSEIF (x = 3);\n    z = 4;\nENDIF;"
    )
    issues = _lint(code)
    assert len(issues) == 1
    assert "ELSEIF block" in issues[0].message
    assert issues[0].fix is None
    assert _fix(code) == (code, 0)


def test_autofix_keeps_empty_elseif_followed_by_else():
    """An empty ELSEIF before an ELSE must NOT be removed (behaviour change)."""
    code = "IF (x = 1);\n    y = 2;\nELSEIF (x = 2);\nELSE;\n    z = 3;\nENDIF;"
    issues = _lint(code)
    elseif_issues = [i for i in issues if "ELSEIF block" in i.message]
    assert len(elseif_issues) == 1
    assert elseif_issues[0].fix is None
    assert _fix(code) == (code, 0)


def test_autofix_removes_empty_while():
    code = "WHILE (x < 5);\nEND;"
    fixed, n = _fix(code)
    assert n == 1
    assert fixed == ""


def test_autofix_removes_empty_while_in_context():
    """Removing a WHILE deletes its END; too, leaving surrounding code intact."""
    code = "foo();\nWHILE (x < 5);\nEND;\nbar();"
    fixed, n = _fix(code)
    assert n == 1
    assert "WHILE" not in fixed
    assert "END" not in fixed
    assert "foo();" in fixed
    assert "bar();" in fixed


def test_autofix_does_not_touch_comment_only_else():
    code = "IF (x = 1);\n    y = 2;\nELSE;\n    # keep me\nENDIF;"
    fixed, n = _fix(code)
    assert n == 0
    assert fixed == code


def test_autofix_does_not_touch_empty_if():
    code = "IF (x = 1);\nENDIF;"
    fixed, n = _fix(code)
    assert n == 0
    assert fixed == code


def test_autofix_removes_elseif_with_string_literal_condition():
    """The removed span may contain string literals.

    Token values store strings unquoted, so the fix text must come from the
    raw source — otherwise the quotes are lost and the fix fails to apply.
    """
    code = "IF (s @= 'A');\n    foo();\nELSEIF (s @= 'B');\nENDIF;"
    fixed, n = _fix(code)
    assert n == 1
    assert fixed == "IF (s @= 'A');\n    foo();\nENDIF;"
    assert _lint(fixed) == []
