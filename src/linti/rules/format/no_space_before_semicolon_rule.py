"""F240 – No space before semicolon."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseTokenRule, RuleExample, RuleMetadata


class NoSpaceBeforeSemicolonRule(BaseTokenRule):
    """Enforces that no whitespace appears immediately before a semicolon."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="No Space Before Semicolon",
        description="Enforces no whitespace immediately before ';'",
        auto_fix=True,
        explanation=(
            "A semicolon that terminates a statement must not be preceded by "
            "any whitespace.  Only a semicolon at the start of a physical line "
            "(after a newline) is exempt."
        ),
        config_example=("rules:\n  whitespace:\n    no_space_before_semicolon: true"),
        examples=[
            RuleExample(code="nVar = 1;", valid=True),
            RuleExample(
                code="nVar = 1 ;",
                description="Space before semicolon",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F240"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("no_space_before_semicolon", True):
            return []
        return [cls()]

    def interested_in(self):
        return [TokenType.SEMICOLON]

    def visit(self, token, window, context: LintContext):
        issues: list[LintIssue] = []

        prev = window.previous()

        if prev is None or prev.type != TokenType.WHITESPACE:
            return issues

        # Skip: whitespace is indentation (its predecessor is a NEWLINE)
        prev_prev = window.previous(2)
        if prev_prev is not None and prev_prev.type == TokenType.NEWLINE:
            return issues
        # Also skip at position 0 (absolute start of file)
        if prev_prev is None:
            return issues

        fix = Fix(position=prev.position, old_value=prev.value, new_value="")
        issues.append(
            LintIssue(
                "Unexpected whitespace before ';'",
                prev.line,
                prev.column,
                prev.position,
                rule_id=self.RULE_ID,
                fix=fix,
            )
        )
        return issues
