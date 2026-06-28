"""Shared helper for identifying generic (templated) TM1 processes.

Several rules treat *generic* processes — whose names start with a configured
prefix (e.g. ``}core.``) — more strictly than regular ones. Keeping the
detection in one place avoids divergent definitions across rules.
"""

from collections.abc import Iterable
from typing import Optional


def is_generic_process(
    process_name: Optional[str], generic_prefixes: Iterable[str]
) -> bool:
    """Return True when *process_name* starts with any of *generic_prefixes*.

    Matching is case-insensitive. Returns False when the name is empty or no
    prefixes are configured.
    """
    if not process_name:
        return False
    name_lower = process_name.lower()
    return any(name_lower.startswith(prefix.lower()) for prefix in generic_prefixes)
