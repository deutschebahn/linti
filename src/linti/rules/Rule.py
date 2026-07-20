from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from linti.linter.lint_context import LintContext

# Global registry of all rule classes with a CONFIG_KEY
_RULE_REGISTRY: list[type] = []


@dataclass(frozen=True)
class RuleExample:
    """A code example for rule documentation."""

    code: str
    description: str = ""
    valid: bool = True


@dataclass(frozen=True)
class RuleMetadata:
    """Complete documentation metadata for a linting rule.

    Used by ``--explain`` CLI and to auto-generate ALL_RULES.md.
    """

    name: str
    description: str
    auto_fix: bool = False
    explanation: str = ""
    config_example: str = ""
    examples: list[RuleExample] = field(default_factory=list)


class BaseRule(ABC):
    """Base class for token-based linting rules."""

    CONFIG_KEY: ClassVar[str] = ""
    DEFAULT_ENABLED: ClassVar[bool] = True
    METADATA: ClassVar[RuleMetadata | None] = None
    # Rule IDs this rule used to carry, kept working for one deprecation cycle.
    # The current ``RULE_ID`` is the canonical (new) ID; anything listed here is
    # resolved to it (with a deprecation warning) wherever a rule is referenced
    # by ID — ``--select``, ``# noqa`` comments, and ``linti explain``.
    DEPRECATED_IDS: ClassVar[list[str]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.CONFIG_KEY:
            _RULE_REGISTRY.append(cls)

    @property
    @abstractmethod
    def RULE_ID(self) -> str:
        """Unique identifier for this rule (e.g., 'F110')."""
        pass

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        """
        Create rule instance(s) from a config dict.

        Override this for rules with custom config parameters.

        Args:
            rule_cfg: Dict with rule-specific config (e.g., {"enabled": true, "style": "uppercase"})

        Returns:
            List of rule instances.
        """
        return [cls()]

    def reset(self) -> None:
        """Reset mutable state before a new lint pass. Override in stateful rules."""

    @abstractmethod
    def interested_in(self):
        """
        Returns list of TokenTypes this rule wants to see.
        Must be overridden — returning [] silently disables the rule.
        """
        ...

    def visit(self, token, window, context: LintContext):
        """
        Called when matching token appears.

        Args:
            token: The token being visited.
            window: TokenWindow for accessing surrounding tokens.
            context: LintContext with block, parameters, variables.

        Returns:
            List of LintIssue objects.
        """
        return []


class BaseStatementRule(ABC):
    """Base class for AST statement-based linting rules."""

    CONFIG_KEY: ClassVar[str] = ""
    DEFAULT_ENABLED: ClassVar[bool] = True
    METADATA: ClassVar[RuleMetadata | None] = None
    # See ``BaseRule.DEPRECATED_IDS``.
    DEPRECATED_IDS: ClassVar[list[str]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.CONFIG_KEY:
            _RULE_REGISTRY.append(cls)

    @property
    @abstractmethod
    def RULE_ID(self) -> str:
        """Unique identifier for this rule (e.g., 'N110')."""
        pass

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        """
        Create rule instance(s) from a config dict.

        Override this for rules with custom config parameters.

        Args:
            rule_cfg: Dict with rule-specific config

        Returns:
            List of rule instances.
        """
        return [cls()]

    def reset(self) -> None:
        """Reset mutable state before a new lint pass. Override in stateful rules."""

    def prepare(self, ast) -> None:
        """Pre-scan the full AST before visiting starts.

        Called once per lint pass after the AST has been built and before any
        ``visit()`` calls.  Override to collect cross-statement information
        (e.g. lookahead to detect loop counters).
        """

    @abstractmethod
    def interested_in(self):
        """
        Returns list of AST statement types this rule wants to visit.
        Must be overridden — returning [] silently disables the rule.
        """
        ...

    def visit(self, statement, context: LintContext):
        """
        Called when matching statement type is encountered.

        Args:
            statement: The AST statement node being visited.
            context: LintContext with block, parameters, variables.

        Returns:
            List of LintIssue objects (or error strings for backward compatibility).
        """
        return []
