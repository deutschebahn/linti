from dataclasses import dataclass
from typing import Optional


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
