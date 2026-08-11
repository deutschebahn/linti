"""Factory for creating rule instances based on configuration."""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass

from linti.config import Config, LintiConfigWarning, rule_severity_override
from linti.rules import _RULE_REGISTRY  # triggers all rule imports
from linti.rules.Rule import BaseTokenRule, BaseStatementRule
from linti.rules.rule_ids import canonical_ids, resolve_and_warn, synthetic_rules


#: What every rule selector (``--select``, ``--extend-select``,
#: ``--exclude-rule``) accepts: one comma-separated string, a sequence of them
#: (a repeated CLI option), or nothing at all.
RuleSelector = str | Sequence[str] | None

#: Top-level ``Config`` settings forwarded into every rule's ``from_config``
#: input, so a rule can share a project-wide fact instead of redeclaring it.
#: A per-rule value of the same name always takes precedence. Rules that do not
#: care simply ignore the key — none unpacks its config as keyword arguments.
_SHARED_TOP_LEVEL_KEYS = ("generic_prefixes", "target_version")


def _matches_select_pattern(rule_id: str, patterns: Sequence[str]) -> bool:
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


def parse_rule_patterns(value: RuleSelector) -> list[str]:
    """Normalize a rule selector into a list of canonical patterns.

    Accepts a single comma-separated string ("F110,C2"), a repeated CLI option
    (``["F110", "C2"]``, each value itself comma-separated), or ``None``.

    A full deprecated rule ID (e.g. "S220") is resolved to its canonical form
    ("C220") with a deprecation warning; group prefixes ("F", "F1") and
    canonical IDs pass through unchanged.
    """
    if value is None:
        return []
    items = [value] if isinstance(value, str) else list(value)
    return [
        resolve_and_warn(part.strip())
        for item in items
        for part in item.split(",")
        if part.strip()
    ]


def _warn_about_inert_patterns(patterns: Sequence[str], flag: str) -> None:
    """Warn about every *flag* pattern that cannot affect the run.

    A pattern is inert in one of two ways. It names a synthetic rule, which no
    selector can reach: there is no rule instance to add or drop, so only that
    rule's config keys govern it. Or it matches no rule ID at all, which is
    almost always a typo — and a typo stays invisible otherwise, since
    ``--select F22O`` quietly lints nothing and ``--ignore F22O`` quietly keeps
    reporting.

    Warn only; the pattern is left in place. Dropping it from ``--select``
    would turn "run exactly these rules" into "run all configured rules",
    which is the opposite of what a user who mistyped one ID wants.
    """
    synthetic = {synth.rule_id.upper(): synth for synth in synthetic_rules()}
    selectable = canonical_ids()

    for pattern in patterns:
        synth = synthetic.get(pattern.upper())
        if synth is not None:
            warnings.warn(
                f"{flag} {synth.rule_id} has no effect: it is enforced directly "
                "in the parser rather than by a rule module, so there is no "
                f"rule to select or skip. {synth.selector_hint}",
                LintiConfigWarning,
                stacklevel=2,
            )
        elif not any(
            _matches_select_pattern(rule_id, [pattern]) for rule_id in selectable
        ):
            warnings.warn(
                f"{flag} {pattern} matches no rule and has no effect. "
                "Run `linti explain` to list the available rule IDs.",
                LintiConfigWarning,
                stacklevel=2,
            )


@dataclass(frozen=True)
class RuleSelection:
    """The rule selectors of one run, normalized and warned about once.

    Parsing is what warns — about deprecated IDs, typos, and selectors linti
    cannot honour — so it has to happen once per run rather than once per rule
    set. :func:`linti.cli.file_linter.lint_files` builds a fresh ``Linter`` per
    file; without this type, a directory run would repeat every warning for
    every file it lints.
    """

    select: tuple[str, ...] = ()
    extend: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @classmethod
    def parse(
        cls,
        select: RuleSelector = None,
        extend_select: RuleSelector = None,
        exclude: RuleSelector = None,
    ) -> "RuleSelection":
        """Normalize the three raw selectors, warning about anything inert."""
        parsed = (
            ("--select", parse_rule_patterns(select)),
            ("--extend-select", parse_rule_patterns(extend_select)),
            ("--exclude-rule", parse_rule_patterns(exclude)),
        )
        for flag, patterns in parsed:
            _warn_about_inert_patterns(patterns, flag)

        return cls(*(tuple(patterns) for _flag, patterns in parsed))


def create_rules(
    cfg: Config,
    select: RuleSelector = None,
    extend_select: RuleSelector = None,
    exclude: RuleSelector = None,
    selection: RuleSelection | None = None,
) -> tuple:
    """
    Create rule instances based on configuration.

    Iterates the auto-discovered ``_RULE_REGISTRY`` instead of maintaining a
    manual import + if-block per rule.

    Each selector takes rule IDs or group prefixes (e.g. "F110", "F", "F1"),
    either comma-separated in one string or as a sequence of such strings.
    They combine in this precedence order:

    1. ``exclude`` wins over everything — a matching rule never runs.
    2. ``select`` replaces the configured set: only matching rules run.
    3. ``extend_select`` adds to whatever is in effect, on top of ``select``
       or, without it, on top of the configured set.
    4. Otherwise the per-rule ``enabled`` setting decides.

    Both ``select`` and ``extend_select`` override an ``enabled: false`` for
    the rules they match.

    Args:
        cfg: Configuration object with rule settings
        select: Optional rule IDs or patterns to run *instead of* the
                configured set (e.g., "F110" or "F,N1" or ["F110", "C220"])
        extend_select: Optional rule IDs or patterns to run *in addition to*
                the set already in effect
        exclude: Optional rule IDs or patterns to skip for this run
        selection: The three selectors already parsed by
                :meth:`RuleSelection.parse`. Callers that build several rule
                sets in one run (a directory lint builds one per file) pass
                this so the parse warnings are emitted once, not per set; it
                supersedes the three raw selectors above.

    Returns:
        Tuple of (token_rules, statement_rules)
    """
    if selection is None:
        selection = RuleSelection.parse(select, extend_select, exclude)
    select_patterns = selection.select
    extend_patterns = selection.extend
    exclude_patterns = selection.exclude

    token_rules: list[BaseTokenRule] = []
    statement_rules: list[BaseStatementRule] = []

    for rule_cls in _RULE_REGISTRY:
        config_key = rule_cls.CONFIG_KEY

        # Look up per-rule config from RulesConfig.
        rule_cfg = getattr(cfg.rules, config_key, None)

        # Create a temporary instance to check the rule ID
        temp_inst = rule_cls()
        rule_id = temp_inst.RULE_ID

        # An exclusion wins over every other selector: a rule named by
        # --exclude-rule never runs, not even when --select asked for it.
        if _matches_select_pattern(rule_id, exclude_patterns):
            continue

        # Determine whether the rule is enabled.
        if rule_cfg is not None:
            enabled = (
                rule_cfg.get("enabled", rule_cls.DEFAULT_ENABLED)
                if isinstance(rule_cfg, dict)
                else getattr(rule_cfg, "enabled", rule_cls.DEFAULT_ENABLED)
            )
        else:
            enabled = rule_cls.DEFAULT_ENABLED

        # --select replaces the configured set, --extend-select adds to it;
        # a match by either runs the rule regardless of its enabled setting.
        matches_extend = _matches_select_pattern(rule_id, extend_patterns)
        if select_patterns:
            if not (
                _matches_select_pattern(rule_id, select_patterns) or matches_extend
            ):
                continue
        elif not (enabled or matches_extend):
            # No select patterns and the rule is disabled — nothing asked for it.
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
