from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

# Control-flow functions and keywords that abruptly alter process flow
# (terminate the process, break out of a loop, or reject/skip the record).
# Using any of them unconditionally is almost always a bug: their effect
# should be guarded by an explicit IF condition. Stored lower-cased for
# case-insensitive matching. Shared with the Unreachable Code rule (C140),
# for which these same statements make any following code dead.
CONTROL_FLOW_STATEMENTS = frozenset(
    {
        "processquit",
        "itemreject",
        "processbreak",
        "processerror",
        "processexitbychorerollback",
        "processexitbyprocessrollback",
        "processrollback",
        "break",
    }
)


class ConditionalControlFlowRule(BaseStatementRule):
    """
    Enforces that flow-altering control statements are only used inside an
    IF/ELSE block.

    Statements such as ``ProcessQuit``, ``ProcessBreak``, ``ProcessError``,
    ``ItemReject``, the ``ProcessRollback`` family and the ``Break`` loop
    keyword abruptly change process flow. Using them unconditionally in the
    main program body (or a bare ``WHILE`` loop) is almost always a logic
    error — their effect should be guarded by an explicit ``IF`` condition.
    """

    CONFIG_KEY = "conditional_control_flow"
    DEPRECATED_IDS = ["S110"]
    METADATA = RuleMetadata(
        name="Conditional Control Flow",
        description="Enforces that flow-altering statements are only used inside an IF/ELSE block",
        auto_fix=False,
        explanation=(
            "Enforces that flow-altering control statements are only used "
            "inside an IF/ELSE block.\n\n"
            "The following functions and keywords abruptly change process "
            "flow and must be guarded by an explicit IF condition:\n"
            "- ProcessQuit\n"
            "- ItemReject\n"
            "- ProcessBreak\n"
            "- ProcessError\n"
            "- ProcessExitByChoreRollback\n"
            "- ProcessExitByProcessRollback\n"
            "- ProcessRollback\n"
            "- Break\n\n"
            "Using any of them in the main program body — or in a bare WHILE "
            "loop with no enclosing IF — is almost always a logic error."
        ),
        config_example=("rules:\n  conditional_control_flow:\n    enabled: true"),
        examples=[
            RuleExample(
                code="IF (nValue = 1);\n    ProcessBreak();\nENDIF;",
                description="ProcessBreak guarded by an IF condition",
                valid=True,
            ),
            RuleExample(
                code="nValue = 5;\nProcessQuit();",
                description="ProcessQuit in the main program body",
                valid=False,
            ),
            RuleExample(
                code="WHILE (nValue = 1);\n    Break;\nEND;",
                description="Break in a bare WHILE loop (no enclosing IF)",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C120"

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context: LintContext):
        """Flag a flow-altering statement used outside an IF/ELSE block."""
        expr = statement.expression
        if not (
            isinstance(expr, FunctionCall)
            and expr.name.lower() in CONTROL_FLOW_STATEMENTS
        ):
            return []

        if context.in_if_block():
            return []

        token = get_node_token(expr)
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )

        return [
            LintIssue(
                message=(
                    f"{expr.name}() is not allowed outside an IF statement. "
                    "Guard it with an explicit IF condition"
                ),
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]
