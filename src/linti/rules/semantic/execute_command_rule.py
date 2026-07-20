"""Rule X110: Prevent ExecuteCommand() calls for security reasons."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import ExpressionStatement, FunctionCall, get_node_token
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ExecuteCommandRule(BaseStatementRule):
    """
    Prohibits the use of ExecuteCommand() function calls.

    ExecuteCommand is disabled for security reasons (e.g., command injection risks).
    """

    CONFIG_KEY = "execute_command"
    DEPRECATED_IDS = ["S320"]
    METADATA = RuleMetadata(
        name="No ExecuteCommand",
        description="Prohibits the use of ExecuteCommand() (disabled for security reasons)",
        auto_fix=False,
        explanation=(
            "Prohibits the use of ExecuteCommand() function calls.\n\n"
            "Why:\n"
            "- Prevents command injection vulnerabilities\n"
            "- Restricts TI code to approved TM1 API functions only\n"
            "- Improves security audit compliance"
        ),
        config_example=("rules:\n  execute_command:\n    enabled: true"),
        examples=[
            RuleExample(
                code="ExecuteCommand('rm -rf /tmp/*');",
                description="Prohibited",
                valid=False,
            ),
            RuleExample(
                code="ExecuteCommand(sUserCommand);",
                description="Prohibited",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "X110"

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context: LintContext):
        expr = statement.expression
        if not isinstance(expr, FunctionCall):
            return []

        if expr.name.lower() != "executecommand":
            return []

        token = get_node_token(expr)
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )

        return [
            LintIssue(
                message="ExecuteCommand() is not allowed (disabled for security reasons)",
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]
