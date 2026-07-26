from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    IfStatement,
    WhileStatement,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.rules.semantic.conditional_control_flow_rule import CONTROL_FLOW_STATEMENTS


class UnreachableCodeRule(BaseStatementRule):
    """
    Flags unreachable code after a flow-terminating statement within a block.

    Statements such as ``ProcessQuit``, ``ProcessBreak``, ``ProcessError``,
    ``ItemReject``, the ``ProcessRollback`` family and the ``Break`` loop
    keyword end the current flow. Any statement that follows one of them in
    the same block body can never execute and should be removed.
    """

    CONFIG_KEY = "unreachable_code"
    METADATA = RuleMetadata(
        name="Unreachable Code",
        description="Flags code after a flow-terminating statement that can never execute",
        auto_fix=False,
        explanation=(
            "Flags unreachable code that follows a flow-terminating statement "
            "within a block.\n\n"
            "Statements such as ProcessQuit, ProcessBreak, ProcessError, "
            "ItemReject, the ProcessRollback family and the Break loop keyword "
            "end the current flow. A flow-terminating statement must therefore "
            "be the last statement in its block; anything after it can never "
            "execute."
        ),
        config_example=("rules:\n  unreachable_code:\n    enabled: true"),
        examples=[
            RuleExample(
                code="IF (nValue = 1);\n    nResult = 10;\n    ProcessQuit();\nENDIF;",
                description="ProcessQuit at the end of the block",
                valid=True,
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
        return "C140"

    def interested_in(self):
        return [IfStatement, WhileStatement]

    def visit(self, statement, context: LintContext):
        """Check each block body for code after a flow-terminating statement."""
        issues = []

        if isinstance(statement, IfStatement):
            issues.extend(self._check_unreachable(statement.then_body))
            if statement.else_body:
                issues.extend(self._check_unreachable(statement.else_body))
        elif isinstance(statement, WhileStatement):
            issues.extend(self._check_unreachable(statement.body))

        return issues

    def _check_unreachable(self, statements):
        """Report statements after a flow-terminating call in a block body."""
        issues = []

        for i, stmt in enumerate(statements):
            if not self._is_flow_terminator(stmt):
                continue

            remaining = [
                s for s in statements[i + 1 :] if not isinstance(s, IfStatement)
            ]
            if not remaining:
                continue

            token = self._get_token(stmt)
            line, column, position = (
                (token.line, token.column, token.position) if token else (0, 0, 0)
            )
            issues.append(
                LintIssue(
                    message=(
                        f"{stmt.expression.name}() must be the last statement in "
                        f"the block. Found {len(remaining)} unreachable "
                        f"statement(s) after it"
                    ),
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            )

        return issues

    def _is_flow_terminator(self, stmt):
        """Check if a statement is a flow-terminating control-flow call."""
        if not isinstance(stmt, ExpressionStatement):
            return False
        expr = stmt.expression
        return (
            isinstance(expr, FunctionCall)
            and expr.name.lower() in CONTROL_FLOW_STATEMENTS
        )

    def _get_token(self, stmt):
        """Extract token from statement for position info."""
        return get_node_token(stmt.expression)
