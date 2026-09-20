"""Factory for creating rule instances based on configuration."""

from linti.config import Config, rule_severity_override
from linti.rules import _RULE_REGISTRY  # triggers all rule imports
from linti.rules.Rule import BaseTokenRule, BaseStatementRule
from linti.rules.rule_ids import resolve_and_warn, warn_if_rule_deprecated


#: Top-level ``Config`` settings forwarded into every rule's ``from_config``
#: input, so a rule can share a project-wide fact instead of redeclaring it.
#: A per-rule value of the same name always takes precedence. Rules that do not
#: care simply ignore the key — none unpacks its config as keyword arguments.
_SHARED_TOP_LEVEL_KEYS = ("generic_prefixes", "target_version")


def _matches_select_pattern(rule_id: str, patterns: list[str]) -> bool:
    """
    Check if a rule ID matches any of the select patterns.

    Patterns can be:
    - Full rule ID: "F110", "D110", "C220"
    - First letter group: "F", "N", "D", "C", "X"
    - Two-letter group: "F1", "D1", "N2", "C3"
    - Three-letter group: "F11", "D11", "C22"

    Args:
        rule_id: The rule ID to check (e.g., "F110")
        patterns: List of patterns to match against

    Returns:
        True if rule_id matches any pattern
    """
    rule_id_upper = rule_id.upper()
    for pattern in patterns:
        pattern_upper = pattern.upper()
        # Check if pattern matches
        if rule_id_upper.startswith(pattern_upper):
            # Ensure it's a valid prefix (not partial matches)
            # e.g., "F1" should match "F110" but not match alone
            if len(pattern_upper) <= len(rule_id_upper):
                return True
    return False


def _configured_enabled(rule_cls, rule_cfg) -> bool:
    """Whether config — or, unset, the rule's own default — turns the rule on."""
    if rule_cfg is None:
        return rule_cls.DEFAULT_ENABLED
    if isinstance(rule_cfg, dict):
        return rule_cfg.get("enabled", rule_cls.DEFAULT_ENABLED)
    return getattr(rule_cfg, "enabled", rule_cls.DEFAULT_ENABLED)


def _active_rule_ids(cfg: Config, registry: list, select_patterns: list | None) -> set:
    """The rule IDs this run would report under, decided before any rule is built.

    A deprecated rule needs to know whether its successor is already covering
    the same code, and that answer has to exist before the first rule is
    instantiated. ``--select`` decides membership on its own here, mirroring how
    it overrides ``enabled`` in ``create_rules``.
    """
    if select_patterns:
        return {
            rule_id
            for _, rule_id in registry
            if _matches_select_pattern(rule_id, select_patterns)
        }
    return {
        rule_id
        for rule_cls, rule_id in registry
        if _configured_enabled(rule_cls, getattr(cfg.rules, rule_cls.CONFIG_KEY, None))
    }


def create_rules(cfg: Config, select: str | None = None) -> tuple:
    """
    Create rule instances based on configuration.

    Iterates the auto-discovered ``_RULE_REGISTRY`` instead of maintaining a
    manual import + if-block per rule.

    Args:
        cfg: Configuration object with rule settings
        select: Optional comma-separated rule IDs or patterns to select
                (e.g., "F110" or "F,N1" or "F110,C220")
                When select is provided, it overrides the enabled flag for matching rules.

    Returns:
        Tuple of (token_rules, statement_rules)
    """
    # Parse select patterns. A full deprecated rule ID (e.g. "S220") is
    # resolved to its canonical form ("C220") with a deprecation warning;
    # group prefixes ("F", "F1") and canonical IDs pass through unchanged.
    select_patterns = None
    if select:
        select_patterns = [
            resolve_and_warn(p.strip()) for p in select.split(",") if p.strip()
        ]

    token_rules: list[BaseTokenRule] = []
    statement_rules: list[BaseStatementRule] = []

    # RULE_ID is a property, so the ID costs an instance. Pay for it once.
    registry = [(rule_cls, rule_cls().RULE_ID) for rule_cls in _RULE_REGISTRY]
    active_ids = _active_rule_ids(cfg, registry, select_patterns)

    for rule_cls, rule_id in registry:
        config_key = rule_cls.CONFIG_KEY

        # Look up per-rule config from RulesConfig.
        rule_cfg = getattr(cfg.rules, config_key, None)

        # --select overrides the enabled setting for the rules it matches, and
        # excludes every rule it does not.
        if select_patterns:
            if not _matches_select_pattern(rule_id, select_patterns):
                continue
        elif not _configured_enabled(rule_cls, rule_cfg):
            continue

        # A deprecated rule that is still switched on would report the same code
        # a second time next to its successor, so the successor wins whenever it
        # is active too. Selecting the old ID explicitly is the escape hatch:
        # it leaves the successor out of `active_ids` and the legacy rule runs.
        successor = rule_cls.METADATA.deprecated_by if rule_cls.METADATA else None
        if successor and successor in active_ids:
            warn_if_rule_deprecated(rule_id, skipped=True)
            continue

        # Exact --select IDs already warn during resolution. Config activation
        # and group selection reach retained deprecated rules here instead.
        if rule_id not in (select_patterns or ()):
            warn_if_rule_deprecated(rule_id)

        # Build a dict view of the config for from_config().
        if rule_cfg is None:
            cfg_dict: dict = {}
        elif isinstance(rule_cfg, dict):
            cfg_dict = rule_cfg
        else:
            cfg_dict = (
                rule_cfg.model_dump()
                if hasattr(rule_cfg, "model_dump")
                else vars(rule_cfg)
            )

        # Share the top-level settings that rules opt into (generic_prefixes for
        # D110/C410, target_version for C510). A per-rule value always wins; the
        # key only ever supplies a value, so it can never enable a rule that the
        # checks above decided to skip.
        for key in _SHARED_TOP_LEVEL_KEYS:
            shared_value = getattr(cfg, key, None)
            if shared_value and not cfg_dict.get(key):
                cfg_dict = {**cfg_dict, key: shared_value}

        instances = rule_cls.from_config(cfg_dict)

        # A project may reweigh any rule. Applied after from_config so it also
        # reaches rules that fan out into several instances (e.g. whitespace).
        severity_override = rule_severity_override(cfg.rules, config_key)

        for inst in instances:
            if severity_override is not None:
                inst._severity_override = severity_override
            if isinstance(inst, BaseTokenRule):
                token_rules.append(inst)
            else:
                statement_rules.append(inst)

    return token_rules, statement_rules
