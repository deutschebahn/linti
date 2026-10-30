"""Every rule example is an executable spec.

An invalid example must be reported by its rule, a valid one must not, each
within the process context (procedure, config, parameters, ...) it declares.
"""

import pytest

from linti.config import Config, RulesConfig
from linti.rules.examples import describe_context, run_example
from linti.rules.Rule import RuleExample
from linti.rules.rule_ids import rule_metadata_index

PROCEDURES = {"prolog", "metadata", "data", "epilog"}

EXAMPLES = [
    pytest.param(
        rule_id,
        example,
        id=f"{rule_id}-{index}-{'valid' if example.valid else 'invalid'}",
    )
    for rule_id, meta in sorted(rule_metadata_index().items())
    for index, example in enumerate(meta.examples)
]


def _unknown_config_keys(config) -> list[str]:
    """Keys pydantic would silently drop instead of passing on to a rule."""
    unknown = [key for key in config if key not in Config.model_fields]
    for rule_key, options in (config.get("rules") or {}).items():
        field = RulesConfig.model_fields.get(rule_key)
        if field is None:
            continue  # untyped rule block: kept verbatim via extra="allow"
        known = field.annotation.model_fields
        unknown += [f"rules.{rule_key}.{opt}" for opt in options if opt not in known]
    return unknown


@pytest.mark.parametrize(("rule_id", "example"), EXAMPLES)
def test_example_context_is_well_formed(rule_id, example):
    assert example.procedure in PROCEDURES
    config = dict(example.config or {})
    Config.model_validate(config)
    assert not _unknown_config_keys(config)


@pytest.mark.parametrize(("rule_id", "example"), EXAMPLES)
def test_example_is_reported_exactly_when_invalid(rule_id, example):
    issues = run_example(rule_id, example)
    if example.valid:
        assert not issues, (
            f"{rule_id} reports its valid example {example.description!r}: "
            + "; ".join(issue.message for issue in issues)
        )
    else:
        assert issues, f"{rule_id} misses its invalid example {example.description!r}"


def test_run_example_passes_context_to_the_rule():
    # N210 only fires on a declared parameter, so this proves the context
    # actually reaches the process being linted.
    bare = RuleExample(code="", valid=False)
    with_parameter = RuleExample(code="", valid=False, parameters=("LogOutput",))
    assert not run_example("N210", bare)
    assert run_example("N210", with_parameter)


def test_run_example_applies_example_config():
    code = "if (x = 1);\n    nResult = 10;\nendif;"
    default = RuleExample(code=code)
    lowercase = RuleExample(
        code=code, config={"rules": {"keyword_casing": {"style": "lowercase"}}}
    )
    assert run_example("F110", default)
    assert not run_example("F110", lowercase)


def test_describe_context():
    assert describe_context(RuleExample(code="x = 1;")) == ""
    example = RuleExample(
        code="",
        procedure="data",
        parameters=("pA",),
        datasource_type="ODBC",
        datasource_query="SELECT 1",
        config={"rules": {"max_line_length": {"limit": 40, "enabled": True}}},
    )
    assert describe_context(example) == (
        "Data procedure · parameters: pA · ODBC data source (SELECT 1)"
        " · config: rules.max_line_length.limit=40, rules.max_line_length.enabled=true"
    )
