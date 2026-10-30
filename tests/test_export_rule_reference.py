"""The website must describe the same rules as the Python registry."""

import importlib.util
import json
from pathlib import Path

from linti.rules.rule_ids import rule_metadata_index


SCRIPT = Path(__file__).parents[1] / "scripts" / "export_rule_reference.py"
SPEC = importlib.util.spec_from_file_location("export_rule_reference", SCRIPT)
assert SPEC and SPEC.loader
export_rule_reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_rule_reference)

OUTPUT = export_rule_reference.OUTPUT
collect_rules = export_rule_reference.collect_rules
render_json = export_rule_reference.render_json


def test_export_includes_each_canonical_rule_once():
    rules = collect_rules()
    ids = [rule["id"] for rule in rules]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(rule_metadata_index())
    assert "C150" in ids
    assert "P900" in ids


def test_checked_in_json_matches_export():
    assert OUTPUT.read_text(encoding="utf-8") == render_json()
    example = next(rule for rule in json.loads(render_json()) if rule["id"] == "C150")
    assert example["config_key"] == "misplaced_function"
    assert example["examples"]


def test_export_carries_example_context():
    rules = {rule["id"]: rule for rule in collect_rules()}
    lowercase = next(e for e in rules["F110"]["examples"] if e["config"])
    assert "style: lowercase" in lowercase["config"]
    assert lowercase["procedure"] == "prolog"
    placement = rules["C150"]["examples"]
    assert {example["procedure"] for example in placement} - {"prolog"}
    assert any(example["parameters"] for example in rules["C210"]["examples"])


def test_default_config_reflects_config_defaults():
    rules = {rule["id"]: rule for rule in collect_rules()}
    # The hand-written config_example turns this option on; the default is off.
    assert "allow_loop_counter_variables: false" in rules["N110"]["default_config"]
    assert "enabled: false" in rules["C130"]["default_config"]
    assert rules["X210"]["default_config"].startswith("rules:\n  sql_where_filtering:\n    enabled: true")


def test_checked_in_config_schema_matches_export():
    assert (
        export_rule_reference.CONFIG_OUTPUT.read_text(encoding="utf-8")
        == export_rule_reference.render_config_schema()
    )


def test_config_schema_carries_form_metadata():
    data = export_rule_reference.collect_config_schema()
    schema = data["schema"]
    # The configurator labels fields with their descriptions and reads the
    # user-facing alias, not the internal field name.
    assert "severity" in schema["properties"]
    assert "min_severity" not in schema["properties"]
    assert schema["properties"]["fail_on"]["description"]
    secret = schema["$defs"]["HardcodedSecretConfig"]["properties"]["mode"]
    assert secret["enum"] == ["relaxed", "standard", "strict", "custom"]
    assert secret["description"]
    assert data["defaults"]["rules"]["docstring_region"]["enabled"] is False
    assert data["defaults"]["severity"] == "warning"
    assert [preset["key"] for preset in data["presets"]][0] == "recommended"
    assert "process_quit" in data["removed_rule_configs"]
    assert data["moved_to_toplevel"]["docstring_region"] == {
        "setting": "generic_prefixes",
        "top_level": "generic_prefixes",
    }
