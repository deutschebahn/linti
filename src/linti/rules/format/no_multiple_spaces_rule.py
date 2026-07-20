"""F260 – No multiple consecutive spaces."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class NoMultipleSpacesRule(BaseRule):
    """Enforces no multiple consecutive spaces outside of indentation."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="No Multiple Spaces",
        description="Enforces no multiple consecutive spaces (except indentation)",
        auto_fix=True,
        explanation=(
            "Two or more consecutive spaces are not allowed, except at the "
            "start of a line (indentation).  Use exactly one space between "
            "tokens."
        ),
        config_example=("rules:\n  whitespace:\n    no_multiple_spaces: true"),
        examples=[
            RuleExample(code="nVar = 1;", valid=True),
            RuleExample(
                code="nVar  =  1;",
                description="Multiple consecutive spaces",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F260"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("no_multiple_spaces", True):
            return []
        return [cls()]

    def interested_in(self):
        return [TokenType.WHITESPACE]

    def visit(self, token, window, context: LintContext):
        if len(token.value) <= 1:
            return []

        # Skip indentation: whitespace that follows a NEWLINE or sits at the
        # very start of the token stream (no predecessor at all).
        prev = window.previous()
        if prev is None or prev.type == TokenType.NEWLINE:
            return []

        fix = Fix(position=token.position, old_value=token.value, new_value=" ")
        return [
            LintIssue(
                "Multiple consecutive spaces found",
                token.line,
                token.column,
                token.position,
                rule_id=self.RULE_ID,
                fix=fix,
            )
        ]
