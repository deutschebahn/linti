"""Run a rule's documentation examples through the real lint pipeline.

Rule examples double as executable specs (``tests/test_rule_examples.py``):
each one is linted with its rule alone, inside the process context it
declares, and must be reported exactly when it is marked invalid.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from linti.rules.Rule import RuleExample

if TYPE_CHECKING:
    from linti.linter.lint_issue import LintIssue

# The process-level imports are deferred: ``linti.rules`` imports every module
# in the package while the rule registry is being built, and ``linter.api``
# (via the linter) depends on that registry.


def run_example(rule_id: str, example: RuleExample) -> list[LintIssue]:
    """Lint *example* with only *rule_id* enabled and return that rule's issues."""
    from linti.config import Config, LintiConfigWarning
    from linti.linter.api import lint_process_model
    from linti.linter.linter import Linter
    from linti.model.process_ir import ProcedureInfo, ProcessIR
    from linti.rules.rule_factory import create_rules

    cfg = Config.model_validate(dict(example.config or {}))
    with warnings.catch_warnings():
        # Selecting a deprecated rule (e.g. C130) warns; that is the point of
        # running its examples, not a problem with them.
        warnings.simplefilter("ignore", LintiConfigWarning)
        token_rules, statement_rules = create_rules(cfg, select=rule_id)
    linter = Linter(token_rules, statement_rules)
    process = ProcessIR(
        name="example",
        parameters=list(example.parameters),
        variables=list(example.variables),
        datasource_type=example.datasource_type,
        datasource_query=example.datasource_query,
        **{example.procedure: ProcedureInfo(code=example.code)},
    )
    return [
        issue
        for _, issue, _ in lint_process_model(process, linter)
        if issue.rule_id == rule_id
    ]


def example_matches(rule_id: str, example: RuleExample) -> bool:
    """True when *example* is reported exactly when it is marked invalid."""
    return bool(run_example(rule_id, example)) != example.valid


def describe_context(example: RuleExample) -> str:
    """One-line summary of the context *example* declares, or ``""`` if none.

    Shown next to the example in ``ALL_RULES.md`` and ``linti explain`` so a
    reader knows what the snippet assumes.
    """
    parts: list[str] = []
    if example.procedure != "prolog":
        parts.append(f"{example.procedure.capitalize()} procedure")
    if example.parameters:
        parts.append("parameters: " + ", ".join(example.parameters))
    if example.variables:
        parts.append("variables: " + ", ".join(example.variables))
    if example.datasource_type:
        source = f"{example.datasource_type} data source"
        if example.datasource_query:
            source += f" ({example.datasource_query})"
        parts.append(source)
    if example.config:
        parts.append("config: " + ", ".join(_flatten(example.config)))
    return " · ".join(parts)


def _flatten(config: Mapping[str, Any], prefix: str = "") -> list[str]:
    """Render nested settings as ``a.b.c=value`` pairs."""
    items: list[str] = []
    for key, value in config.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            items.extend(_flatten(value, path + "."))
        else:
            items.append(f"{path}={_format_value(value)}")
    return items


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)
