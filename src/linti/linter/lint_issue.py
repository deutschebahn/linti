from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """How much weight a finding carries.

    Ordered from least to most severe via :attr:`rank`.  ``str`` is the base so
    a value round-trips through YAML config and CLI options unchanged.

    ``WARNING`` marks findings the *user* may not own — most importantly the
    parse diagnostics (E110, S900), which can equally mean "your TI has a
    syntax error" or "linti's parser does not cover this construct".  Such a
    finding is worth reporting but is a poor reason to fail a build, so by
    default it does not affect the exit code.

    Comparison is deliberately explicit through :attr:`rank` rather than by
    overriding ``<``/``>``: ``str`` already defines those lexicographically,
    and "error" sorts *below* "warning" there, which is the wrong way round.
    """

    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        """Position on the severity scale; higher means more severe."""
        return _SEVERITY_RANK[self]

    def at_least(self, floor: "Severity") -> bool:
        """True when this severity is *floor* or more severe."""
        return self.rank >= floor.rank


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.WARNING: 0,
    Severity.ERROR: 1,
}

#: Default for any rule that does not declare one, and for every issue built
#: without an explicit severity. Keeps pre-severity behaviour intact.
DEFAULT_SEVERITY = Severity.ERROR


@dataclass
class Fix:
    """A concrete fix suggestion for an auto-fixable lint issue.

    Attributes:
        position: Character offset in the source code where the fix applies
        old_value: The original text to replace
        new_value: The corrected text
    """

    position: int
    old_value: str
    new_value: str


@dataclass
class LintIssue:
    message: str
    line: int
    column: int
    position: int
    rule_id: str = ""
    fix: Optional[Fix] = None
    # Stamped by the Linter from the producing rule's (possibly config-overridden)
    # severity. Rules that build issues themselves rarely set this; the default
    # keeps every existing rule blocking exactly as before.
    severity: Severity = DEFAULT_SEVERITY
