"""Rule package - auto-discovers all rule modules via pkgutil."""

import importlib
import pkgutil

from linti.rules.Rule import _RULE_REGISTRY  # noqa: F401 – public re-export

# Automatically import every module in this package so that
# __init_subclass__ populates _RULE_REGISTRY.  No manual imports needed.
_pkg_path = __path__
_pkg_name = __name__
for _finder, _module_name, _is_pkg in pkgutil.walk_packages(
    _pkg_path, prefix=_pkg_name + "."
):
    importlib.import_module(_module_name)
