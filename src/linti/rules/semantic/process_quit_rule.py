from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    IfStatement,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ProcessQuitRule(BaseStatementRule):
    """
    Enforces that ProcessQuit() is only allowed in IF/ELSE blocks, not in the main program body.

    ProcessQuit() terminates the process immediately, so:
    1. It must not be used in the main program body at all
    2. It must be at the end of IF/ELSE blocks (no unreachable code after it)
    """

    CONFIG_KEY = "process_quit"
    METADATA = RuleMetadata(
        name="ProcessQuit Placement",
        description="Enforces that ProcessQuit() is only at the end of blocks to prevent unreachable code",
        auto_fix=False,
        explanation=(
            "Enforces that ProcessQuit() is only allowed in IF/ELSE blocks, not "
            "in the main program body.\n\n"
            "Since ProcessQuit() terminates the TI process immediately:\n"
            "1. It must not be used in the main program body at all\n"
            "2. When used in IF/ELSE blocks, it must be at the end to prevent unreachable code"
        ),
        config_example=("rules:\n" "  process_quit:\n" "    enabled: true"),
        examples=[
            RuleExample(
                code="IF (nValue = 1);\n    nResult = 10;\n    ProcessQuit();\nENDIF;",
                description="ProcessQuit at end of IF block",
                valid=True,
            ),
            RuleExample(
                code="nValue = 5;\nProcessQuit();",
                description="ProcessQuit in main program body",
                valid=False,
            ),
            RuleExample(
                code="IF (nValue = 1);\n    ProcessQuit();\n    nResult = 10;\nENDIF;",
                description="Unreachable code after ProcessQuit",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "S110"

    def interested_in(self):
        return [ExpressionStatement, IfStatement]

    def visit(self, statement, context: LintContext):
        """Visit ExpressionStatement or IfStatement and check for ProcessQuit() usage."""
        issues = []

        if isinstance(statement, ExpressionStatement):
            if self._is_process_quit(statement):
                if not context.in_control_block():
                    token = self._get_token(statement)
                    line, column, position = (
                        (token.line, token.column, token.position)
                        if token
                        else (0, 0, 0)
                    )
                    issues.append(
                        LintIssue(
                            message="ProcessQuit() is not allowed in the main program body. Use it only in IF/ELSE blocks",
                            line=line,
                            column=column,
                            position=position,
                            rule_id=self.RULE_ID,
                        )
                    )

        elif isinstance(statement, IfStatement):
            issues.extend(self._check_unreachable(statement.then_body))
            if statement.else_body:
                issues.extend(self._check_unreachable(statement.else_body))

        return issues

    def _check_unreachable(self, statements):
        """Check for unreachable statements after ProcessQuit() in a block."""
        issues = []

        for i, stmt in enumerate(statements):
            if isinstance(stmt, ExpressionStatement) and self._is_process_quit(stmt):
                remaining = [
                    s for s in statements[i + 1 :] if not isinstance(s, IfStatement)
                ]
                if remaining:
                    token = self._get_token(stmt)
                    line, column, position = (
                        (token.line, token.column, token.position)
                        if token
                        else (0, 0, 0)
                    )
                    issues.append(
                        LintIssue(
                            message=(
                                f"ProcessQuit() must be the last statement in the block. "
                                f"Found {len(remaining)} unreachable statement(s) after it"
                            ),
                            line=line,
                            column=column,
                            position=position,
                            rule_id=self.RULE_ID,
                        )
                    )

        return issues

    def _is_process_quit(self, stmt):
        """Check if a statement is a ProcessQuit() function call."""
        expr = stmt.expression
        return isinstance(expr, FunctionCall) and expr.name.lower() == "processquit"

    def _get_token(self, stmt):
        """Extract token from statement for position info."""
        expr = stmt.expression
        if isinstance(expr, FunctionCall):
            return get_node_token(expr)
        return None
