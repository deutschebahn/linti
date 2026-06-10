"""Backward-compatible import for `DocstringRegionRule`.

The canonical module lives in ``linti.rules.documentation``.
"""

from linti.rules.documentation.docstring_region_rule import (  # noqa: F401
    DocstringRegionRule,
)

__all__ = ["DocstringRegionRule"]
