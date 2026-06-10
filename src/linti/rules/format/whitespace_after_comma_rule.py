"""F230 – Whitespace after comma."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class WhitespaceAfterCommaRule(BaseRule):
    """Enforces exactly one space after each comma."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="Whitespace After Comma",
        description="Enforces exactly one space after commas",
        auto_fix=True,
        explanation=(
            "Every comma must be followed by exactly one space.  Commas at "
            "the end of a physical line (multi-line argument lists) are exempt."
        ),
        config_example=("rules:\n" "  whitespace:\n" "    after_comma: true"),
        examples=[
            RuleExample(code="func(a, b, c);", valid=True),
            RuleExample(
                code="func(a,b,c);",
                description="Missing spaces after commas",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F230"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("after_comma", True):
            return []
        return [cls()]

    def interested_in(self):
        return [TokenType.COMMA]

    def visit(self, token, window, context: LintContext):
        issues: list[LintIssue] = []

        nxt = window.next()

        # Exempt: end-of-line or end-of-stream, and trailing commas before `)`
        if nxt is None:
            return issues
        if nxt.type in (TokenType.NEWLINE, TokenType.RPAREN):
            return issues

        after_pos = token.position + 1  # length of "," is always 1

        if nxt.type != TokenType.WHITESPACE:
            fix = Fix(position=after_pos, old_value="", new_value=" ")
            issues.append(
                LintIssue(
                    "Expected one space after ','",
                    token.line,
                    token.column + 1,
                    after_pos,
                    rule_id=self.RULE_ID,
                    fix=fix,
                )
            )
        elif nxt.value != " ":
            fix = Fix(position=nxt.position, old_value=nxt.value, new_value=" ")
            issues.append(
                LintIssue(
                    "Expected exactly one space after ','",
                    nxt.line,
                    nxt.column,
                    nxt.position,
                    rule_id=self.RULE_ID,
                    fix=fix,
                )
            )

        return issues
