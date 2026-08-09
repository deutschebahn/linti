"""Tests for canonical/deprecated rule ID resolution and its invariants.

Covers the guarantees the rule-ID migration promises: the registry's IDs stay
internally consistent, every deprecated ID keeps working for one deprecation
cycle, and every rule keeps its documentation and configuration.
"""

import pytest

from linti.config import Config, LintiConfigWarning
from linti.rules import _RULE_REGISTRY
from linti.rules.rule_factory import create_rules
from linti.rules.rule_ids import (
    DuplicateRuleIdError,
    _canonical_id,
    _deprecated_ids,
    canonical_ids,
    deprecated_ids_for,
    resolve_rule_id,
    validate_rule_ids,
)

# The full old → new mapping this migration promises to honour. The
# Formatting rules (F1xx-F3xx) keep the IDs they already had; only the
# former "Semantic (S)" rules moved.
MIGRATION = {
    "N230": "N120",
    "D410": "D110",
    "S110": "C120",
    "S120": "C130",
    "S130": "C110",
    "S210": "C210",
    "S220": "C220",
    "S310": "C310",
    "S320": "X110",
    "S330": "X120",
    "S340": "X210",
    "S410": "C410",
    "E110": "P110",
}

# Every rule that survives the migration, by canonical ID.
EXPECTED_CANONICAL_IDS = {
    "F110",
    "F220",
    "F230",
    "F240",
    "F250",
    "F260",
    "F270",
    "F310",
    "F320",
    "F330",
    "N110",
    "N120",
    "N210",
    "N220",
    "D110",
    "C110",
    "C120",
    "C130",
    "C140",
    "C210",
    "C220",
    "C310",
    "C410",
    "C430",
    "C510",
    "X110",
    "X120",
    "X130",
    "X210",
    "P110",
}


class TestRegistryInvariants:
    def test_validation_passes(self):
        """The shipped registry satisfies every rule-ID invariant."""
        validate_rule_ids()

    def test_canonical_ids_are_unique(self):
        ids = [_canonical_id(cls) for cls in _RULE_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_canonical_ids_match_the_migration_target(self):
        assert canonical_ids() == EXPECTED_CANONICAL_IDS

    def test_deprecated_ids_are_unique(self):
        deprecated = [d for cls in _RULE_REGISTRY for d in _deprecated_ids(cls)]
        assert len(deprecated) == len(set(deprecated))

    def test_no_deprecated_id_is_reused_as_a_canonical_id(self):
        deprecated = {d for cls in _RULE_REGISTRY for d in _deprecated_ids(cls)}
        assert deprecated & canonical_ids() == set()

    def test_every_deprecated_id_maps_to_exactly_one_rule(self):
        owners: dict[str, list[str]] = {}
        for cls in _RULE_REGISTRY:
            for dep in _deprecated_ids(cls):
                owners.setdefault(dep, []).append(_canonical_id(cls))
        assert all(len(o) == 1 for o in owners.values())

    def test_no_rule_loses_its_documentation(self):
        """Every registered rule still carries METADATA with a name."""
        for cls in _RULE_REGISTRY:
            meta = getattr(cls, "METADATA", None)
            assert meta is not None, f"{_canonical_id(cls)} lost its METADATA"
            assert meta.name, f"{_canonical_id(cls)} has an empty name"

    def test_no_rule_loses_its_configuration(self):
        """Every registered rule keeps a CONFIG_KEY and is constructible."""
        for cls in _RULE_REGISTRY:
            assert cls.CONFIG_KEY, f"{_canonical_id(cls)} lost its CONFIG_KEY"

    def test_validation_raises_on_a_conflicting_deprecated_id(self, monkeypatch):
        """A deprecated ID colliding with a canonical ID is rejected."""
        offender = next(cls for cls in _RULE_REGISTRY if _canonical_id(cls) == "F110")
        monkeypatch.setattr(offender, "DEPRECATED_IDS", ["C220"], raising=False)
        with pytest.raises(DuplicateRuleIdError, match="collides"):
            validate_rule_ids()


class TestResolution:
    @pytest.mark.parametrize("old,new", sorted(MIGRATION.items()))
    def test_every_deprecated_id_resolves_to_its_canonical(self, old, new):
        assert resolve_rule_id(old) == (new, True)

    @pytest.mark.parametrize("old,new", sorted(MIGRATION.items()))
    def test_deprecated_lookup_is_case_insensitive(self, old, new):
        assert resolve_rule_id(old.lower()) == (new, True)

    @pytest.mark.parametrize("rule_id", sorted(EXPECTED_CANONICAL_IDS))
    def test_canonical_ids_resolve_to_themselves(self, rule_id):
        assert resolve_rule_id(rule_id) == (rule_id, False)

    def test_unknown_id_passes_through_unchanged(self):
        assert resolve_rule_id("F990") == ("F990", False)

    def test_group_prefix_passes_through_unchanged(self):
        assert resolve_rule_id("F") == ("F", False)
        assert resolve_rule_id("F1") == ("F1", False)

    def test_deprecated_ids_for_reports_previous_ids(self):
        assert deprecated_ids_for("C220") == ["S220"]
        assert deprecated_ids_for("F110") == []


class TestManualDeprecations:
    """P900 (nesting-depth) has no rule class, so its S900->P900 migration is
    a manual entry in rule_ids.py rather than a DEPRECATED_IDS attribute — it
    still needs to resolve like every registry-backed one does."""

    def test_s900_resolves_to_p900(self):
        assert resolve_rule_id("S900") == ("P900", True)

    def test_s900_lookup_is_case_insensitive(self):
        assert resolve_rule_id("s900") == ("P900", True)

    def test_deprecated_ids_for_reports_s900(self):
        assert deprecated_ids_for("P900") == ["S900"]

    def test_p900_is_not_a_registry_canonical_id(self):
        """P900 stays out of canonical_ids() — it isn't a registry rule."""
        assert "P900" not in canonical_ids()


class TestSelectBackwardCompatibility:
    def test_deprecated_select_creates_the_canonical_rule(self):
        cfg = Config()
        with pytest.warns(LintiConfigWarning, match="S220 is deprecated"):
            token_rules, stmt_rules = create_rules(cfg, select="S220")
        assert [r.RULE_ID for r in token_rules + stmt_rules] == ["C220"]

    def test_deprecated_select_matches_canonical_select(self):
        cfg = Config()
        with pytest.warns(LintiConfigWarning):
            deprecated = create_rules(cfg, select="S320")
        canonical = create_rules(cfg, select="X110")
        assert [r.RULE_ID for r in deprecated[0] + deprecated[1]] == [
            r.RULE_ID for r in canonical[0] + canonical[1]
        ]

    def test_warning_names_both_ids(self):
        cfg = Config()
        with pytest.warns(LintiConfigWarning) as record:
            create_rules(cfg, select="S410")
        message = str(record[0].message)
        assert "S410 is deprecated" in message
        assert "Use C410 instead" in message

    def test_canonical_select_does_not_warn(self, recwarn):
        create_rules(Config(), select="C220")
        assert [w for w in recwarn if issubclass(w.category, LintiConfigWarning)] == []
