"""F220 – Whitespace around binary operators."""

from linti.lexer.token import BINARY_OP_TYPES, TokenType, is_unary_plus_minus
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class WhitespaceAroundOperatorsRule(BaseRule):
    """Enforces exactly one space on each side of every binary operator."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="Whitespace Around Operators",
        description="Enforces exactly one space around binary operators",
        auto_fix=True,
        explanation=(
            "Every binary operator (`+`, `-`, `*`, `/`, `=`, `<`, `>`, `<=`, "
            "`>=`, `<>`, `@=`, `@<>`, `&`, `|`) must have exactly one space on "
            "each side.  Unary operators (e.g. a leading `-1`) are exempt.  "
            "Operators at the start or end of a physical line are also exempt."
        ),
        config_example=("rules:\n" "  whitespace:\n" "    around_operators: true"),
        examples=[
            RuleExample(code="nVar = nA + nB;", valid=True),
            RuleExample(
                code="nVar=nA+nB;",
                description="Missing spaces around operators",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F220"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("around_operators", True):
            return []
        return [cls()]

    def interested_in(self):
        return list(BINARY_OP_TYPES)

    def visit(self, token, window, context: LintContext):
        issues: list[LintIssue] = []

        # Skip unary plus / minus
        if token.type in (TokenType.PLUS, TokenType.MINUS):
            if is_unary_plus_minus(window):
                return issues

        op_val = token.value
        prev = window.previous()
        nxt = window.next()

        # ------------------------------------------------------------------
        # Check space BEFORE operator
        # ------------------------------------------------------------------
        if prev is not None and prev.type != TokenType.NEWLINE:
            if prev.type != TokenType.WHITESPACE:
                fix = Fix(position=token.position, old_value="", new_value=" ")
                issues.append(
                    LintIssue(
                        f"Expected one space before '{op_val}'",
                        token.line,
                        token.column,
                        token.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )
            elif prev.value != " ":
                fix = Fix(position=prev.position, old_value=prev.value, new_value=" ")
                issues.append(
                    LintIssue(
                        f"Expected exactly one space before '{op_val}'",
                        prev.line,
                        prev.column,
                        prev.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )

        # ------------------------------------------------------------------
        # Check space AFTER operator
        # ------------------------------------------------------------------
        if nxt is not None and nxt.type not in (TokenType.NEWLINE, TokenType.COMMENT):
            if nxt.type != TokenType.WHITESPACE:
                after_pos = token.position + len(token.value)
                fix = Fix(position=after_pos, old_value="", new_value=" ")
                issues.append(
                    LintIssue(
                        f"Expected one space after '{op_val}'",
                        token.line,
                        token.column + len(token.value),
                        after_pos,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )
            elif nxt.value != " ":
                fix = Fix(position=nxt.position, old_value=nxt.value, new_value=" ")
                issues.append(
                    LintIssue(
                        f"Expected exactly one space after '{op_val}'",
                        nxt.line,
                        nxt.column,
                        nxt.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )

        return issues
