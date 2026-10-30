"""The configurator's presets must be valid, minimal linti.yaml files."""

import warnings

import pytest
import yaml

from linti.config import Config, LintiConfigWarning, RulesConfig
from linti.config_presets import PRESETS
from linti.linter.text_api import config_from_text
from linti.rules import _RULE_REGISTRY

DEFAULTS = Config().model_dump(mode="json", by_alias=True)
KNOWN_RULE_KEYS = set(RulesConfig.model_fields) | {
    rule_cls.CONFIG_KEY for rule_cls in _RULE_REGISTRY
}
PRESET_IDS = [preset.key for preset in PRESETS]


def _leaves(settings, path=()):
    for key, value in settings.items():
        if isinstance(value, dict):
            yield from _leaves(value, (*path, key))
        else:
            yield (*path, key), value


def _default(path):
    node = DEFAULTS
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def test_preset_keys_are_unique():
    assert len(PRESET_IDS) == len(set(PRESET_IDS))
    assert PRESET_IDS[0] == "recommended"


@pytest.mark.parametrize("preset", PRESETS, ids=PRESET_IDS)
def test_preset_loads_without_warnings(preset):
    text = yaml.safe_dump(preset.settings, sort_keys=False)
    with warnings.catch_warnings():
        warnings.simplefilter("error", LintiConfigWarning)
        config_from_text(text)


@pytest.mark.parametrize("preset", PRESETS, ids=PRESET_IDS)
def test_preset_uses_only_known_keys(preset):
    top_level = set(Config.model_json_schema(by_alias=True)["properties"])
    assert set(preset.settings) <= top_level
    assert set(preset.settings.get("rules", {})) <= KNOWN_RULE_KEYS


@pytest.mark.parametrize("preset", PRESETS, ids=PRESET_IDS)
def test_preset_lists_only_deviations_from_defaults(preset):
    for path, value in _leaves(preset.settings):
        assert value != _default(path), f"{'.'.join(path)} repeats the default"


def test_presets_take_effect():
    by_key = {preset.key: preset for preset in PRESETS}
    strict = Config(**by_key["strict-ci"].settings)
    assert strict.fail_on.value == "warning"
    assert strict.rules.docstring_region.enabled is True
    v12 = Config(**by_key["pa-v12"].settings)
    assert v12.target_version == "v12"
    assert v12.rules.function_version_compatibility.enabled is True
    assert v12.rules.use_hierarchy_aware_functions.mode == "enforce"
