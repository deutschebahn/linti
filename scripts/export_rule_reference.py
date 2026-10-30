#!/usr/bin/env python3
"""Export the rule registry for the interactive, static documentation site.

Writes the site's ``rules.json`` (the rule reference) and
``config-schema.json`` (the configurator's form schema, defaults and presets).
Also run by ``scripts/generate_all_rules.py``, so regenerating the rule docs
keeps ``ALL_RULES.md`` and both files in step.

Usage:
    python scripts/export_rule_reference.py
    python scripts/export_rule_reference.py --check
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from linti.config import _MOVED_TO_TOPLEVEL, _REMOVED_RULE_CONFIGS, Config  # noqa: E402
from linti.config_presets import PRESETS  # noqa: E402
from linti.rules.rule_ids import GROUP_NAMES, RuleDoc, deprecated_ids_for, rule_docs  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "site" / "app" / "data"
OUTPUT = DATA_DIR / "rules.json"
CONFIG_OUTPUT = DATA_DIR / "config-schema.json"


def collect_rules() -> list[dict]:
    """Return one serializable record per canonical (including synthetic) rule."""
    return [_record(doc) for doc in rule_docs()]


def _record(doc: RuleDoc) -> dict:
    metadata = doc.metadata
    return {
        "id": doc.rule_id,
        "name": metadata.name,
        "description": metadata.description,
        "group": doc.rule_id[0],
        "group_name": GROUP_NAMES.get(doc.rule_id[0], "Other"),
        "severity": metadata.severity.value,
        "auto_fix": metadata.auto_fix,
        "enabled_by_default": doc.enabled_by_default,
        "config_key": doc.config_key,
        "explanation": metadata.explanation,
        "config_example": metadata.config_example,
        "default_config": _default_config(doc.config_key, metadata, doc.enabled_by_default),
        "deprecated_by": metadata.deprecated_by,
        "previous_ids": deprecated_ids_for(doc.rule_id),
        "examples": [_example(example) for example in metadata.examples],
    }


def _default_config(config_key, metadata, enabled_by_default) -> str:
    """The rule's effective defaults as linti.yaml text, read from ``Config()``.

    Unlike the hand-written ``config_example``, this is what LinTi uses when a
    project sets nothing. Rules without a typed config only know ``enabled``
    and ``severity``.
    """
    if not config_key:
        return ""
    declared = Config().rules.model_dump(mode="json", by_alias=True).get(config_key) or {}
    options = {key: value for key, value in declared.items() if key not in {"enabled", "severity"}}
    settings = {
        "enabled": declared.get("enabled", enabled_by_default),
        "severity": declared.get("severity") or metadata.severity.value,
        **options,
    }
    return yaml.safe_dump({"rules": {config_key: settings}}, sort_keys=False)


def _example(example) -> dict:
    """Serialize an example with the process context it has to run in."""
    return {
        "code": example.code,
        "description": example.description,
        "valid": example.valid,
        "procedure": example.procedure,
        # linti.yaml text, so the playground can show and edit it as-is.
        "config": yaml.safe_dump(_plain(example.config), sort_keys=False) if example.config else "",
        "parameters": list(example.parameters),
        "variables": list(example.variables),
        "datasource_type": example.datasource_type,
        "datasource_query": example.datasource_query,
    }


def _plain(value):
    """Turn Mapping/tuple config values into types ``yaml.safe_dump`` accepts."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def collect_config_schema() -> dict:
    """Everything the configurator needs to render and validate ``linti.yaml``."""
    return {
        "schema": Config.model_json_schema(by_alias=True),
        "defaults": Config().model_dump(mode="json", by_alias=True),
        "presets": [
            {
                "key": preset.key,
                "title": preset.title,
                "description": preset.description,
                "yaml": yaml.safe_dump(preset.settings, sort_keys=False)
                if preset.settings
                else "",
            }
            for preset in PRESETS
        ],
        "removed_rule_configs": _REMOVED_RULE_CONFIGS,
        "moved_to_toplevel": {
            rule_key: {"setting": old_key, "top_level": new_key}
            for rule_key, (old_key, new_key) in _MOVED_TO_TOPLEVEL.items()
        },
    }


def _dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_json() -> str:
    return _dump(collect_rules())


def render_config_schema() -> str:
    return _dump(collect_config_schema())


def _outputs() -> dict[Path, str]:
    return {OUTPUT: render_json(), CONFIG_OUTPUT: render_config_schema()}


def is_up_to_date() -> bool:
    return all(
        path.exists() and path.read_text(encoding="utf-8") == content
        for path, content in _outputs().items()
    )


def write() -> None:
    for path, content in _outputs().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Generated {path}")


def main() -> None:
    if "--check" in sys.argv:
        if not is_up_to_date():
            raise SystemExit(
                "Rule reference is out of date. Run scripts/export_rule_reference.py"
            )
        print("Rule reference is up to date.")
    else:
        write()


if __name__ == "__main__":
    main()
