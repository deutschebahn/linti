"""F270 – No trailing whitespace."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseTokenRule, RuleExample, RuleMetadata


class NoTrailingWhitespaceRule(BaseTokenRule):
    """Enforces no trailing whitespace at the end of a line."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="No Trailing Whitespace",
        description="Enforces no trailing whitespace at the end of lines",
        auto_fix=True,
        explanation=(
            "Lines must not end with whitespace characters.  Trailing spaces "
            "or tabs before a newline (or at end of file) will be removed."
        ),
        config_example=("rules:\n  whitespace:\n    no_trailing_whitespace: true"),
        examples=[
            RuleExample(code="nVar = 1;", valid=True),
            RuleExample(
                code="nVar = 1;   ",
                description="Trailing spaces at end of line",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F270"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("no_trailing_whitespace", True):
            return []
        return [cls()]

    def interested_in(self):
        return [TokenType.WHITESPACE]

    def visit(self, token, window, context: LintContext):
        nxt = window.next()

        # Only report when the whitespace directly precedes a newline or EOF
        if nxt is None or nxt.type in (TokenType.NEWLINE, TokenType.EOF):
            fix = Fix(position=token.position, old_value=token.value, new_value="")
            return [
                LintIssue(
                    "Trailing whitespace at end of line",
                    token.line,
                    token.column,
                    token.position,
                    rule_id=self.RULE_ID,
                    fix=fix,
                )
            ]

        return []
