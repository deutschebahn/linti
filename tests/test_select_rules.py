"""Tests for the --select rule filter functionality."""

from linti.config import Config
from linti.rules.rule_factory import _matches_select_pattern, create_rules


def test_matches_select_pattern_exact():
    """Test exact rule ID matching."""
    assert _matches_select_pattern("F110", ["F110"])
    assert _matches_select_pattern("D410", ["D410"])
    assert _matches_select_pattern("S220", ["S220"])
    assert not _matches_select_pattern("F110", ["F111"])


def test_matches_select_pattern_first_letter():
    """Test first letter group matching."""
    assert _matches_select_pattern("F110", ["F"])
    assert _matches_select_pattern("F220", ["F"])
    assert _matches_select_pattern("F310", ["F"])
    assert _matches_select_pattern("D410", ["D"])
    assert not _matches_select_pattern("N110", ["F"])


def test_matches_select_pattern_two_letters():
    """Test two-letter group matching (e.g., F1, F2, N1)."""
    assert _matches_select_pattern("F110", ["F1"])
    assert _matches_select_pattern("F120", ["F1"])
    assert not _matches_select_pattern("F220", ["F1"])

    assert _matches_select_pattern("D410", ["D4"])
    assert not _matches_select_pattern("D410", ["D3"])

    assert _matches_select_pattern("F220", ["F2"])
    assert _matches_select_pattern("F220", ["F2"])
    assert not _matches_select_pattern("F110", ["F2"])

    assert _matches_select_pattern("N110", ["N1"])
    assert not _matches_select_pattern("N210", ["N1"])


def test_matches_select_pattern_three_letters():
    """Test three-letter group matching (e.g., F11, S22)."""
    assert _matches_select_pattern("F110", ["F11"])
    assert not _matches_select_pattern("F120", ["F11"])

    assert _matches_select_pattern("D410", ["D41"])
    assert not _matches_select_pattern("D410", ["D42"])

    assert _matches_select_pattern("S220", ["S22"])
    assert not _matches_select_pattern("S210", ["S22"])


def test_matches_select_pattern_multiple():
    """Test multiple patterns."""
    assert _matches_select_pattern("F110", ["F110", "S220"])
    assert _matches_select_pattern("S220", ["F110", "S220"])
    assert not _matches_select_pattern("N110", ["F110", "S220"])


def test_matches_select_pattern_case_insensitive():
    """Test case-insensitive matching."""
    assert _matches_select_pattern("F110", ["f110"])
    assert _matches_select_pattern("f110", ["F110"])
    assert _matches_select_pattern("F110", ["f"])
    assert _matches_select_pattern("D410", ["d410"])
    assert _matches_select_pattern("D410", ["d"])


def test_create_rules_with_select():
    """Test that create_rules respects the select parameter."""
    cfg = Config()

    # Without select, all enabled rules should be created
    token_rules, stmt_rules = create_rules(cfg)
    total_rules = len(token_rules) + len(stmt_rules)

    # With select=F, only Format rules should be created
    token_rules_f, stmt_rules_f = create_rules(cfg, select="F")
    total_f_rules = len(token_rules_f) + len(stmt_rules_f)

    assert total_f_rules < total_rules

    # Check that all F-rules are Format rules (start with F)
    all_f_rules = token_rules_f + stmt_rules_f
    for rule in all_f_rules:
        assert rule.RULE_ID.startswith("F"), f"Expected F-rule, got {rule.RULE_ID}"


def test_create_rules_with_specific_rule():
    """Test selecting a specific rule."""
    cfg = Config()

    token_rules, stmt_rules = create_rules(cfg, select="F110")
    all_rules = token_rules + stmt_rules

    # Should have exactly one rule (or possibly zero if F110 is disabled)
    assert len(all_rules) <= 1
    if all_rules:
        assert all_rules[0].RULE_ID == "F110"


def test_create_rules_with_multiple_select():
    """Test selecting multiple rules with comma-separated patterns."""
    cfg = Config()

    token_rules, stmt_rules = create_rules(cfg, select="F110,D410")
    all_rules = token_rules + stmt_rules

    # All rules should be either F110 or D410
    for rule in all_rules:
        assert rule.RULE_ID in ["F110", "D410"], f"Unexpected rule {rule.RULE_ID}"


def test_create_rules_with_groups():
    """Test selecting multiple rule groups."""
    cfg = Config()

    # Get all N and D rules
    token_rules, stmt_rules = create_rules(cfg, select="N,D")
    all_rules = token_rules + stmt_rules

    # All rules should start with N or D
    for rule in all_rules:
        assert rule.RULE_ID[0] in ["N", "D"], f"Unexpected rule {rule.RULE_ID}"


def test_select_with_whitespace():
    """Test that select patterns with whitespace are handled correctly."""
    cfg = Config()

    # Pattern with spaces around commas
    token_rules, stmt_rules = create_rules(cfg, select="F110 , D410")
    all_rules = token_rules + stmt_rules

    for rule in all_rules:
        assert rule.RULE_ID in ["F110", "D410"]


def test_removed_rule_is_not_created_when_selected():
    """Removed rules should not be instantiated even if explicitly selected."""
    cfg = Config()

    token_rules, stmt_rules = create_rules(cfg, select="F210")

    assert token_rules + stmt_rules == []
