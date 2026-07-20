"""F250 – One space inside parentheses."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class OneSpaceInsideParenthesesRule(BaseRule):
    """Enforces exactly one space immediately inside parentheses."""

    CONFIG_KEY = "whitespace"
    DEFAULT_ENABLED = True
    METADATA = RuleMetadata(
        name="One Space Inside Parentheses",
        description="Enforces exactly one space inside '(' and ')'",
        auto_fix=True,
        explanation=(
            "There must be exactly one space after an opening parenthesis and "
            "before a closing parenthesis.  Empty parentheses and multi-line "
            "parenthesised expressions (where the content starts on a new line) "
            "are exempt."
        ),
        config_example=(
            "rules:\n  whitespace:\n    one_space_inside_parentheses: true"
        ),
        examples=[
            RuleExample(code="func( a, b );", valid=True),
            RuleExample(
                code="func(a, b);",
                description="Missing spaces inside parentheses",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F250"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        if not rule_cfg.get("one_space_inside_parentheses", True):
            return []
        return [cls()]

    def interested_in(self):
        return [TokenType.LPAREN, TokenType.RPAREN]

    def visit(self, token, window, context: LintContext):
        issues: list[LintIssue] = []

        if token.type == TokenType.LPAREN:
            nxt = window.next()
            # Exempt: end-of-stream, empty parens, or multiline (content on next line)
            if nxt is None or nxt.type in (TokenType.NEWLINE, TokenType.RPAREN):
                return issues

            if nxt.type != TokenType.WHITESPACE:
                # No space at all → insert one
                after_pos = token.position + 1
                fix = Fix(position=after_pos, old_value="", new_value=" ")
                issues.append(
                    LintIssue(
                        "Expected one space after '('",
                        token.line,
                        token.column + 1,
                        after_pos,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )
            elif nxt.value != " ":
                # Wrong amount of whitespace → normalise to single space
                fix = Fix(position=nxt.position, old_value=nxt.value, new_value=" ")
                issues.append(
                    LintIssue(
                        "Expected exactly one space after '('",
                        nxt.line,
                        nxt.column,
                        nxt.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )

        else:  # RPAREN
            prev = window.previous()
            # Skip: multiline (content on previous line) or empty parens
            if prev is None or prev.type == TokenType.NEWLINE:
                return issues
            if prev.type == TokenType.LPAREN:
                return issues

            if prev.type != TokenType.WHITESPACE:
                # No space at all → insert one
                fix = Fix(position=token.position, old_value="", new_value=" ")
                issues.append(
                    LintIssue(
                        "Expected one space before ')'",
                        token.line,
                        token.column,
                        token.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )
            elif prev.value != " ":
                # Wrong amount of whitespace → normalise to single space
                fix = Fix(position=prev.position, old_value=prev.value, new_value=" ")
                issues.append(
                    LintIssue(
                        "Expected exactly one space before ')'",
                        prev.line,
                        prev.column,
                        prev.position,
                        rule_id=self.RULE_ID,
                        fix=fix,
                    )
                )

        return issues
