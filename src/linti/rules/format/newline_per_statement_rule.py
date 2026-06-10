from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class NewLinePerStatementRule(BaseRule):
    """Enforces that after a completed statement, code continues on a new line.

    Exception: no newline is required when the statement is immediately
    before the procedure end (EOF).
    """

    CONFIG_KEY = "newline_per_statement"
    METADATA = RuleMetadata(
        name="One Statement Per Line",
        description="Enforces that each statement is followed by a newline",
        auto_fix=True,
        explanation=(
            "Enforces that after a completed statement (marked by a semicolon), "
            "code continues on a new line.\n\n"
            "Exception: no newline is required when the statement is immediately "
            "before the procedure end (EOF)."
        ),
        config_example=("rules:\n" "  newline_per_statement:\n" "    enabled: true"),
        examples=[
            RuleExample(
                code="nValue = 5;\nsMessage = 'test';",
                description="Each statement on its own line",
                valid=True,
            ),
            RuleExample(
                code="nValue = 5; sMessage = 'test';",
                description="Multiple statements on same line",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "F320"

    def interested_in(self):
        return [TokenType.SEMICOLON]

    def visit(self, token, window, context: LintContext):
        issues = []

        if context.is_end_of_procedure(token.line):
            return issues

        offset = 1
        ws_token = None
        while True:
            nxt = window.next(offset)

            if nxt is None or nxt.type == TokenType.EOF:
                # End of file — exception, no newline required
                break

            if nxt.type == TokenType.NEWLINE:
                # Proper newline after statement — OK
                break

            if nxt.type in (TokenType.WHITESPACE, TokenType.COMMENT):
                if nxt.type == TokenType.WHITESPACE:
                    ws_token = nxt
                offset += 1
                continue

            # Non-whitespace/comment token on the same line after semicolon
            fix_pos = ws_token.position if ws_token else nxt.position
            fix_old = ws_token.value if ws_token else ""

            issues.append(
                LintIssue(
                    "Each statement must be followed by a newline",
                    nxt.line,
                    nxt.column,
                    nxt.position,
                    rule_id=self.RULE_ID,
                    fix=Fix(position=fix_pos, old_value=fix_old, new_value="\n"),
                )
            )
            break

        return issues
