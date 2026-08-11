"""Tests for the --select rule filter functionality."""

import warnings

import pytest

from linti.config import Config, LintiConfigWarning
from linti.rules.rule_factory import (
    RuleSelection,
    _matches_select_pattern,
    create_rules,
)


def test_matches_select_pattern_exact():
    """Test exact rule ID matching."""
    assert _matches_select_pattern("F110", ["F110"])
    assert _matches_select_pattern("D110", ["D110"])
    assert _matches_select_pattern("C220", ["C220"])
    assert not _matches_select_pattern("F110", ["F111"])


def test_matches_select_pattern_first_letter():
    """Test first letter group matching."""
    assert _matches_select_pattern("F110", ["F"])
    assert _matches_select_pattern("F220", ["F"])
    assert _matches_select_pattern("F210", ["F"])
    assert _matches_select_pattern("D110", ["D"])
    assert not _matches_select_pattern("N110", ["F"])


def test_matches_select_pattern_two_letters():
    """Test two-letter group matching (e.g., F1, F2, N1)."""
    assert _matches_select_pattern("F110", ["F1"])
    assert _matches_select_pattern("F120", ["F1"])
    assert not _matches_select_pattern("F220", ["F1"])

    assert _matches_select_pattern("D110", ["D1"])
    assert not _matches_select_pattern("D110", ["D3"])

    assert _matches_select_pattern("F220", ["F2"])
    assert _matches_select_pattern("F220", ["F2"])
    assert not _matches_select_pattern("F110", ["F2"])

    assert _matches_select_pattern("N110", ["N1"])
    assert not _matches_select_pattern("N210", ["N1"])


def test_matches_select_pattern_three_letters():
    """Test three-letter group matching (e.g., F11, C22)."""
    assert _matches_select_pattern("F110", ["F11"])
    assert not _matches_select_pattern("F120", ["F11"])

    assert _matches_select_pattern("D110", ["D11"])
    assert not _matches_select_pattern("D110", ["D12"])

    assert _matches_select_pattern("C220", ["C22"])
    assert not _matches_select_pattern("C210", ["C22"])


def test_matches_select_pattern_multiple():
    """Test multiple patterns."""
    assert _matches_select_pattern("F110", ["F110", "C220"])
    assert _matches_select_pattern("C220", ["F110", "C220"])
    assert not _matches_select_pattern("N110", ["F110", "C220"])


def test_matches_select_pattern_case_insensitive():
    """Test case-insensitive matching."""
    assert _matches_select_pattern("F110", ["f110"])
    assert _matches_select_pattern("f110", ["F110"])
    assert _matches_select_pattern("F110", ["f"])
    assert _matches_select_pattern("D110", ["d110"])
    assert _matches_select_pattern("D110", ["d"])


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

    token_rules, stmt_rules = create_rules(cfg, select="F110,D110")
    all_rules = token_rules + stmt_rules

    # All rules should be either F110 or D110
    for rule in all_rules:
        assert rule.RULE_ID in ["F110", "D110"], f"Unexpected rule {rule.RULE_ID}"


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
    token_rules, stmt_rules = create_rules(cfg, select="F110 , D110")
    all_rules = token_rules + stmt_rules

    for rule in all_rules:
        assert rule.RULE_ID in ["F110", "D110"]


def test_unknown_rule_id_is_not_created_when_selected():
    """An ID owned by no rule (e.g. a removed one) instantiates nothing."""
    cfg = Config()

    with pytest.warns(LintiConfigWarning, match="matches no rule"):
        token_rules, stmt_rules = create_rules(cfg, select="F990")

    assert token_rules + stmt_rules == []


def _rule_by_id(cfg, rule_id: str):
    token_rules, stmt_rules = create_rules(cfg, select=rule_id)
    return (token_rules + stmt_rules)[0]


# --- --extend-select and --exclude-rule -------------------------------------


def _rule_ids(cfg: Config, **selectors) -> set[str]:
    """The IDs create_rules produces for *cfg* under the given selectors."""
    token_rules, stmt_rules = create_rules(cfg, **selectors)
    return {rule.RULE_ID for rule in token_rules + stmt_rules}


def test_extend_select_adds_to_the_configured_set():
    """--extend-select keeps the default set and adds the named rules."""
    cfg = Config()

    default_ids = _rule_ids(cfg)
    extended_ids = _rule_ids(cfg, extend_select="D110")

    # D110 is opt-in, so it joins a default set that is otherwise untouched.
    assert "D110" not in default_ids
    assert extended_ids == default_ids | {"D110"}


def test_extend_select_overrides_a_disabled_rule():
    """A rule the config switched off still runs when extended in."""
    cfg = Config(rules={"docstring_region": {"enabled": False}})

    assert "D110" not in _rule_ids(cfg)
    assert "D110" in _rule_ids(cfg, extend_select="D110")


def test_extend_select_adds_on_top_of_select():
    """--select replaces the set; --extend-select adds to that replacement."""
    cfg = Config()

    ids = _rule_ids(cfg, select="F", extend_select="D110")

    assert "D110" in ids
    assert {rule_id for rule_id in ids if rule_id != "D110"}, "F rules still ran"
    assert all(rule_id.startswith("F") or rule_id == "D110" for rule_id in ids)


def test_exclude_removes_a_rule_from_the_default_set():
    cfg = Config()

    ids = _rule_ids(cfg, exclude="F110")

    assert "F110" not in ids
    # Only F110 went missing; every other default rule still runs.
    assert _rule_ids(cfg) - ids == {"F110"}


def test_exclude_accepts_a_group_prefix():
    cfg = Config()

    ids = _rule_ids(cfg, exclude="F2")

    assert not any(rule_id.startswith("F2") for rule_id in ids)
    assert any(rule_id.startswith("F1") for rule_id in ids)


def test_exclude_wins_over_select_and_extend_select():
    """An excluded rule stays out even when another selector asked for it."""
    cfg = Config()

    assert "F110" not in _rule_ids(cfg, select="F110", exclude="F110")
    assert "D110" not in _rule_ids(
        cfg, select="F", extend_select="D110", exclude="D110"
    )


def test_selectors_accept_repeated_values():
    """A repeated CLI option is equivalent to one comma-separated string."""
    cfg = Config()

    assert _rule_ids(cfg, select=["F110", "D110"]) == _rule_ids(cfg, select="F110,D110")
    assert _rule_ids(cfg, exclude=["F110", "D110"]) == _rule_ids(
        cfg, exclude="F110,D110"
    )


def test_excluding_the_nesting_depth_pseudo_rule_warns_and_changes_nothing():
    """P900 has no rule instance to drop — say so instead of doing nothing."""
    cfg = Config()

    with pytest.warns(LintiConfigWarning, match="P900 has no effect") as recorded:
        ids = _rule_ids(cfg, exclude="P900")

    assert ids == _rule_ids(cfg)
    # The hint has to name the settings that do govern the diagnostic.
    assert "max_nesting_depth" in str(recorded[0].message)
    assert "rules.nesting_depth.enabled" in str(recorded[0].message)


def test_selecting_the_nesting_depth_pseudo_rule_warns_too():
    """No selector can reach P900, not just --exclude-rule."""
    cfg = Config()

    with pytest.warns(LintiConfigWarning, match=r"--select P900 has no effect"):
        create_rules(cfg, select="P900")

    with pytest.warns(LintiConfigWarning, match=r"--extend-select P900 has no effect"):
        create_rules(cfg, extend_select="P900")


def test_excluding_the_deprecated_nesting_depth_id_warns_twice():
    """S900 resolves to P900 first, then hits the same refusal."""
    cfg = Config()

    with pytest.warns(LintiConfigWarning) as recorded:
        _rule_ids(cfg, exclude="S900")

    messages = [str(warning.message) for warning in recorded]
    assert any("S900 is deprecated" in message for message in messages)
    assert any("P900 has no effect" in message for message in messages)


# --- unknown patterns -------------------------------------------------------


@pytest.mark.parametrize(
    "selector, flag",
    [
        ({"select": "F22O"}, "--select"),
        ({"extend_select": "F22O"}, "--extend-select"),
        ({"exclude": "F22O"}, "--exclude-rule"),
    ],
)
def test_a_pattern_matching_no_rule_warns(selector, flag):
    """A typo is inert in every selector, so every selector has to say so."""
    with pytest.warns(LintiConfigWarning, match=f"{flag} F22O matches no rule"):
        create_rules(Config(), **selector)


def test_unknown_pattern_warning_points_at_explain():
    with pytest.warns(LintiConfigWarning, match="linti explain"):
        create_rules(Config(), select="NOPE")


def test_a_valid_group_prefix_does_not_warn():
    """Only patterns that match nothing warn — prefixes are normal input."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", LintiConfigWarning)
        create_rules(Config(), select="F", extend_select="D1", exclude="C")


def test_an_unknown_select_pattern_still_selects_nothing():
    """Warning about a typo must not silently widen the run to every rule."""
    with pytest.warns(LintiConfigWarning):
        ids = _rule_ids(Config(), select="F990")

    assert ids == set()
    assert _rule_ids(Config()), "the default set is not empty"


def test_a_selection_is_parsed_and_warned_about_once():
    """Reusing a RuleSelection is what keeps a directory run from repeating."""
    with pytest.warns(LintiConfigWarning) as recorded:
        selection = RuleSelection.parse(select="F22O")
    assert len(recorded) == 1

    with warnings.catch_warnings():
        warnings.simplefilter("error", LintiConfigWarning)
        for _ in range(3):
            create_rules(Config(), selection=selection)


def test_excluding_a_group_prefix_never_refuses():
    """`--ignore P` is a normal exclusion: it just doesn't reach P900."""
    cfg = Config()

    with warnings.catch_warnings():
        warnings.simplefilter("error", LintiConfigWarning)
        ids = _rule_ids(cfg, exclude="P")

    assert not any(rule_id.startswith("P") for rule_id in ids)


def test_top_level_generic_prefixes_shared_with_rules():
    """The top-level generic_prefixes reaches rules that opt into it."""
    cfg = Config(generic_prefixes=["}core."])

    c410 = _rule_by_id(cfg, "C410")
    d110 = _rule_by_id(cfg, "D110")

    assert c410._generic_prefixes == ["}core."]
    assert d110._generic_prefixes == ["}core."]


def test_per_rule_and_top_level_generic_prefixes_conflict_raises():
    """Setting both the top-level and the deprecated per-rule value is a hard error."""
    with pytest.raises(ValueError, match="generic_prefixes"):
        Config(
            generic_prefixes=["}core."],
            rules={"docstring_region": {"generic_prefixes": ["}custom."]}},
        )
