"""Canonical ↔ deprecated rule ID resolution and validation.

The rule metadata is the single source of truth. Each rule declares its
canonical ``RULE_ID`` plus any ``DEPRECATED_IDS`` it has owned in the past.
This module derives the lookup tables from the registry once (lazily) and
resolves any user-supplied ID — from ``--select``, ``# noqa`` comments, or
``linti explain`` — to its canonical form, emitting a deprecation warning when
a deprecated ID was used.

A live canonical ID always wins over a deprecated alias: if a migration ever
recycles a number for a different rule, that number resolves to the rule that
now owns it, and no rule may keep it as a deprecated alias (see
:func:`validate_rule_ids`).

This module also holds the central logic for rule-group names and their
canonical ordering (``GROUP_NAMES``, ``GROUP_ORDER``), shared by ALL_RULES.md
generation and ``linti explain``.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

from linti.config import LintiConfigWarning
from linti.rules import _RULE_REGISTRY
from linti.rules.Rule import RuleMetadata

# Single source of truth for rule-ID groups: display name and canonical
# ordering. Shared by ALL_RULES.md generation (scripts/generate_all_rules.py)
# and `linti explain` (cli/rule_explainer.py) so both stay in sync.
GROUP_NAMES: dict[str, str] = {
    "F": "Formatting Rules",
    "N": "Naming Convention Rules",
    "D": "Documentation Rules",
    "C": "Code Quality Rules",
    "X": "External Interactions Rules",
    "P": "Parser Rules",
}

# Iteration order of GROUP_NAMES doubles as the canonical group ordering.
# Safe to rely on: dict insertion order is guaranteed by the language since
# Python 3.7, not just a CPython implementation detail.
GROUP_ORDER: dict[str, int] = {group: index for index, group in enumerate(GROUP_NAMES)}


def group_sort_key(rule_id: str) -> tuple[int, str]:
    """Sort key ordering rule IDs by group (see ``GROUP_ORDER``), then by ID."""
    return (GROUP_ORDER.get(rule_id[0], len(GROUP_ORDER)), rule_id)


# Lazily built lookup tables (see ``_build``).
_canonical_ids: set[str] | None = None
_deprecated_to_canonical: dict[str, str] | None = None
_deprecated_by_canonical: dict[str, list[str]] | None = None
_metadata_by_id: dict[str, RuleMetadata] | None = None


@dataclass(frozen=True)
class SyntheticRule:
    """A pseudo-rule with no class in ``_RULE_REGISTRY`` to walk.

    Currently only ``P900`` (the nesting-depth diagnostic): it's enforced
    directly in the parser rather than by a rule module, so it has nowhere to
    declare ``RULE_ID``/``METADATA``/``DEPRECATED_IDS`` the normal way.
    ``linti explain`` and ``ALL_RULES.md`` generation — both of which
    otherwise only walk the registry — merge these in via
    :func:`synthetic_rules` instead of each hardcoding the same rule-specific
    knowledge separately.
    """

    rule_id: str
    metadata: RuleMetadata
    config_key: str
    deprecated_ids: tuple[str, ...] = field(default_factory=tuple)


def synthetic_rules() -> list[SyntheticRule]:
    """Pseudo-rules to merge in alongside the registry, e.g. for ``explain``.

    Imports ``linter.api`` lazily: that module (and what it pulls in — the
    fixer, parse cache, reporter, providers...) is a much heavier dependency
    than this ID-bookkeeping module should carry at import time, and
    ``linter.api`` is the single source of truth for P900's ID/metadata —
    this function must not duplicate it in a second, driftable literal.
    """
    from linti.linter.api import NESTING_DEPTH_METADATA, NESTING_DEPTH_RULE_ID

    return [
        SyntheticRule(
            rule_id=NESTING_DEPTH_RULE_ID,
            metadata=NESTING_DEPTH_METADATA,
            config_key="nesting_depth",
            deprecated_ids=("S900",),
        )
    ]


class DuplicateRuleIdError(ValueError):
    """Raised when the rule registry has an inconsistent set of IDs.

    Guards the invariants documented on :func:`validate_rule_ids`; a violation
    is a programming error in the rules, not a user-config problem.
    """


def rule_instances(rule_cls) -> list:
    """Instantiate *rule_cls* the way the registry walkers need it.

    Rules that fan out into several instances (one per configured option) are
    built through ``from_config({})``; anything that cannot be built from an
    empty config falls back to a bare instance, since all callers here only
    want the declared IDs, not a working rule.

    Not total: a rule that cannot be default-constructed either propagates out
    of the fallback. That is the right outcome for the ID-bookkeeping callers,
    where such a rule is an unusable registry entry — callers that only need a
    display name should guard, as :func:`rule_metadata_index` does.
    """
    try:
        return rule_cls.from_config({})
    except Exception:
        return [rule_cls()]


def _canonical_id(rule_cls) -> str:
    """Return the canonical ``RULE_ID`` for a registered rule class."""
    return rule_instances(rule_cls)[0].RULE_ID


def _deprecated_ids(rule_cls) -> list[str]:
    return [rid.upper() for rid in getattr(rule_cls, "DEPRECATED_IDS", []) or []]


def _build() -> None:
    """Populate the module-level lookup tables from the registry (once)."""
    global _canonical_ids, _deprecated_to_canonical, _deprecated_by_canonical
    if _canonical_ids is not None:
        return

    canonical: set[str] = set()
    dep_to_canon: dict[str, str] = {}
    dep_by_canon: dict[str, list[str]] = {}

    for rule_cls in _RULE_REGISTRY:
        canonical.add(_canonical_id(rule_cls).upper())

    for rule_cls in _RULE_REGISTRY:
        canon = _canonical_id(rule_cls).upper()
        deprecated = _deprecated_ids(rule_cls)
        if deprecated:
            dep_by_canon.setdefault(canon, []).extend(deprecated)
        for dep in deprecated:
            dep_to_canon[dep] = canon

    for synth in synthetic_rules():
        canon = synth.rule_id.upper()
        deprecated = [dep.upper() for dep in synth.deprecated_ids]
        if deprecated:
            dep_by_canon.setdefault(canon, []).extend(deprecated)
        for dep in deprecated:
            dep_to_canon[dep] = canon

    _canonical_ids = canonical
    _deprecated_to_canonical = dep_to_canon
    _deprecated_by_canonical = dep_by_canon


def rule_metadata_index() -> dict[str, RuleMetadata]:
    """Map every rule ID — registry and synthetic alike — to its metadata.

    Built once and cached. Lets a caller holding nothing but the ``rule_id`` a
    :class:`~linti.linter.lint_issue.LintIssue` carries recover the rule's
    human-readable name.
    """
    global _metadata_by_id
    if _metadata_by_id is not None:
        return _metadata_by_id

    index: dict[str, RuleMetadata] = {}
    for rule_cls in _RULE_REGISTRY:
        meta: RuleMetadata | None = getattr(rule_cls, "METADATA", None)
        if meta is None:
            continue
        try:
            instances = rule_instances(rule_cls)
        except Exception:
            # A rule that cannot be instantiated at all is a registry bug, but
            # this index only feeds display; let the walkers that actually need
            # the rule (``_build``, ``create_rules``) be the ones to fail.
            continue
        for inst in instances:
            # Upper-cased like every other table here, so a lowercase RULE_ID
            # resolves through ``rule_name`` instead of rendering nameless.
            index.setdefault(inst.RULE_ID.upper(), meta)

    for synth in synthetic_rules():
        index.setdefault(synth.rule_id.upper(), synth.metadata)

    _metadata_by_id = index
    return index


def rule_name(rule_id: str) -> str:
    """Human-readable name for *rule_id*, or ``""`` when it is unknown.

    Deliberately total: reporting must never blow up on an ID that has no
    metadata behind it.
    """
    meta = rule_metadata_index().get(rule_id.strip().upper())
    return meta.name if meta is not None else ""


def canonical_ids() -> set[str]:
    """Return the set of all canonical (current) rule IDs."""
    _build()
    assert _canonical_ids is not None
    return set(_canonical_ids)


def deprecated_ids_for(canonical_id: str) -> list[str]:
    """Return the deprecated IDs a canonical rule ID used to carry."""
    _build()
    assert _deprecated_by_canonical is not None
    return list(_deprecated_by_canonical.get(canonical_id.upper(), []))


def resolve_rule_id(rule_id: str) -> tuple[str, bool]:
    """Resolve *rule_id* to its canonical form.

    Returns ``(canonical_id, was_deprecated)``. Matching is case-insensitive
    and the returned canonical ID is upper-cased. A live canonical ID always
    wins over a deprecated alias. Unknown IDs and group prefixes (e.g. ``F``,
    ``F1``) are returned unchanged with ``was_deprecated=False``.
    """
    rid = rule_id.strip().upper()
    _build()
    assert _canonical_ids is not None and _deprecated_to_canonical is not None
    if rid in _canonical_ids:
        return rid, False
    if rid in _deprecated_to_canonical:
        return _deprecated_to_canonical[rid], True
    return rid, False


def warn_if_deprecated(original: str, canonical: str, was_deprecated: bool) -> None:
    """Emit a deprecation warning when a deprecated ID was used."""
    if not was_deprecated:
        return
    warnings.warn(
        f"Rule ID {original.strip().upper()} is deprecated. Use {canonical} instead.",
        LintiConfigWarning,
        stacklevel=2,
    )


def resolve_and_warn(rule_id: str) -> str:
    """Resolve *rule_id* and warn if a deprecated ID was used. Return canonical."""
    canonical, was_deprecated = resolve_rule_id(rule_id)
    warn_if_deprecated(rule_id, canonical, was_deprecated)
    return canonical


def validate_rule_ids() -> None:
    """Validate the registry's rule-ID invariants, raising on any violation.

    Ensures:

    * every canonical rule ID is unique;
    * every deprecated ID is unique (maps to exactly one rule);
    * no deprecated ID is reused as a canonical ID.
    """
    canonical_list: list[str] = []
    deprecated_owner: dict[str, str] = {}

    for rule_cls in _RULE_REGISTRY:
        canon = _canonical_id(rule_cls).upper()
        canonical_list.append(canon)

    canonical_set = set(canonical_list)
    duplicate_canonical = sorted(
        {cid for cid in canonical_list if canonical_list.count(cid) > 1}
    )
    if duplicate_canonical:
        raise DuplicateRuleIdError(
            f"Duplicate canonical rule IDs: {', '.join(duplicate_canonical)}"
        )

    for rule_cls in _RULE_REGISTRY:
        canon = _canonical_id(rule_cls).upper()
        for dep in _deprecated_ids(rule_cls):
            if dep in canonical_set:
                raise DuplicateRuleIdError(
                    f"Deprecated rule ID {dep} (of {canon}) collides with a "
                    "canonical rule ID; a live canonical ID may not also be a "
                    "deprecated alias."
                )
            if dep in deprecated_owner and deprecated_owner[dep] != canon:
                raise DuplicateRuleIdError(
                    f"Deprecated rule ID {dep} is claimed by both "
                    f"{deprecated_owner[dep]} and {canon}."
                )
            deprecated_owner[dep] = canon
