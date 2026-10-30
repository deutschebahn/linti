"""Starting-point ``linti.yaml`` configurations for common use cases.

The website's configurator offers these as one-click presets. Each preset
lists only the settings that differ from LinTi's defaults, so a project picks
up future default changes for everything it did not decide on explicitly.
``tests/test_config_presets.py`` checks that every preset loads cleanly and
keeps to that rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfigPreset:
    """One use case and the ``linti.yaml`` settings that fit it."""

    key: str
    title: str
    description: str
    settings: dict[str, Any] = field(default_factory=dict)


PRESETS: list[ConfigPreset] = [
    ConfigPreset(
        key="recommended",
        title="Recommended",
        description=(
            "LinTi's defaults: every rule that is on by default, errors fail the "
            "run, warnings are reported. A good start for most projects."
        ),
    ),
    ConfigPreset(
        key="strict-ci",
        title="Strict CI gate",
        description=(
            "Every finding blocks the build, processes need a docstring, and "
            "secret detection matches more names. For teams that want a clean "
            "codebase enforced on every merge."
        ),
        settings={
            "fail_on": "warning",
            "rules": {
                "docstring_region": {"enabled": True},
                "hardcoded_secret": {"mode": "strict"},
                "unknown_statement": {"severity": "error"},
                "nesting_depth": {"severity": "error"},
            },
        },
    ),
    ConfigPreset(
        key="pa-v12",
        title="Planning Analytics v12 migration",
        description=(
            "Targets Planning Analytics v12: reports functions that v12 no longer "
            "supports and requires hierarchy-aware functions everywhere."
        ),
        settings={
            "target_version": "v12",
            "rules": {
                "function_version_compatibility": {"enabled": True},
                "use_hierarchy_aware_functions": {"mode": "enforce"},
            },
        },
    ),
]
