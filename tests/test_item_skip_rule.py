"""Tests for ItemSkipRule."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.semantic.item_skip_rule import ItemSkipRule


def _lint(code, block=None):
    tokens = Lexer(code).tokenize()
    rule = ItemSkipRule()
    linter = Linter(statement_rules=[rule])
    return linter.lint(tokens, LintContext(block=block))


def test_item_skip_allowed_in_metadata():
    """Test that ItemSkip() in metadata block is allowed."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ENDIF;
    """
    assert len(_lint(code, block="metadata")) == 0


def test_item_skip_allowed_in_data():
    """Test that ItemSkip() in data block is allowed."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ENDIF;
    """
    assert len(_lint(code, block="data")) == 0


def test_item_skip_not_allowed_in_prolog():
    """Test that ItemSkip() in prolog block is flagged."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ENDIF;
    """
    errors = _lint(code, block="prolog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id
    assert "prolog" in errors[0].message.lower()


def test_item_skip_not_allowed_in_epilog():
    """Test that ItemSkip() in epilog block is flagged."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ENDIF;
    """
    errors = _lint(code, block="epilog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id
    assert "epilog" in errors[0].message.lower()


def test_item_skip_in_if_block_in_prolog():
    """Test that ItemSkip() in IF block within prolog is flagged."""
    code = """
    IF (nValue = 1);
        nResult = 10;
        ItemSkip();
    ELSE;
        nResult = 20;
    ENDIF;
    """
    errors = _lint(code, block="prolog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id


def test_item_skip_in_else_block_in_epilog():
    """Test that ItemSkip() in ELSE block within epilog is flagged."""
    code = """
    IF (nValue = 1);
        nResult = 10;
    ELSE;
        ItemSkip();
        nResult = 20;
    ENDIF;
    """
    errors = _lint(code, block="epilog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id


def test_item_skip_case_insensitive():
    """Test that ItemSkip check is case-insensitive."""
    code = """
    IF (nValue = 1);
        itemskip();
    ENDIF;
    """
    errors = _lint(code, block="prolog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id


def test_item_skip_nested_if_statements():
    """Test ItemSkip in nested if statements."""
    code = """
    IF (nValue = 1);
        IF (nOther = 2);
            ItemSkip();
        ENDIF;
        nResult = 10;
    ENDIF;
    """
    errors = _lint(code, block="epilog")
    assert len(errors) == 1
    assert "C130" in errors[0].rule_id


def test_multiple_item_skip_calls_in_prolog():
    """Test multiple ItemSkip calls in different blocks."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ELSE;
        ItemSkip();
    ENDIF;
    """
    errors = _lint(code, block="prolog")
    assert len(errors) == 2
    assert all("C130" in err.rule_id for err in errors)


def test_item_skip_allowed_when_no_block_context():
    """Test that ItemSkip() is allowed when block context is None (plain .ti file)."""
    code = """
    IF (nValue = 1);
        ItemSkip();
    ENDIF;
    """
    assert len(_lint(code, block=None)) == 0
