"""Factory for creating rule instances based on configuration."""

from linti.config import Config
from linti.rules import _RULE_REGISTRY  # triggers all rule imports
from linti.rules.Rule import BaseRule, BaseStatementRule
from linti.rules.rule_ids import resolve_and_warn


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

    token_rules: list[BaseRule] = []
    statement_rules: list[BaseStatementRule] = []

    for rule_cls in _RULE_REGISTRY:
        config_key = rule_cls.CONFIG_KEY

        # Look up per-rule config from RulesConfig.
        rule_cfg = getattr(cfg.rules, config_key, None)

        # Create a temporary instance to check the rule ID
        temp_inst = rule_cls()
        rule_id = temp_inst.RULE_ID

        # Check if rule matches select pattern (if provided)
        # If select is provided, --select overrides the enabled setting
        matches_select = False
        if select_patterns:
            matches_select = _matches_select_pattern(rule_id, select_patterns)

        # Determine whether the rule is enabled.
        if rule_cfg is not None:
            enabled = (
                rule_cfg.get("enabled", rule_cls.DEFAULT_ENABLED)
                if isinstance(rule_cfg, dict)
                else getattr(rule_cfg, "enabled", rule_cls.DEFAULT_ENABLED)
            )
        else:
            enabled = rule_cls.DEFAULT_ENABLED

        # Use select patterns to override enabled setting if provided
        if select_patterns:
            # If select patterns are provided, only use rules that match
            if not matches_select:
                continue
            # Matched rule should be included regardless of enabled setting
            enabled = True
        elif not enabled:
            # Only skip if no select patterns and rule is disabled
            continue

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

        # Share the top-level generic_prefixes with rules that opt into it.
        # A non-empty per-rule value still wins (deprecated override path).
        if not cfg_dict.get("generic_prefixes") and cfg.generic_prefixes:
            cfg_dict = {**cfg_dict, "generic_prefixes": cfg.generic_prefixes}

        instances = rule_cls.from_config(cfg_dict)

        for inst in instances:
            if isinstance(inst, BaseRule):
                token_rules.append(inst)
            else:
                statement_rules.append(inst)

    return token_rules, statement_rules
