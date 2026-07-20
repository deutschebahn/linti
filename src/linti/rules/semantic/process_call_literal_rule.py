from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    String,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ProcessCallLiteralRule(BaseStatementRule):
    """
    Enforces literal process name in RunProcess()/ExecuteProcess().

    The first argument must be a string literal to keep process lineage explicit.
    """

    CONFIG_KEY = "process_call_literal"
    DEPRECATED_IDS = ["S310"]
    METADATA = RuleMetadata(
        name="Literal Process Calls",
        description="Enforces that RunProcess()/ExecuteProcess() use a string literal as first argument",
        auto_fix=False,
        explanation=(
            "Enforces that RunProcess() and ExecuteProcess() calls use a string literal "
            "as their first argument (the target process name).\n\n"
            "This keeps process lineage explicit and avoids dynamic indirection "
            "through variables/parameters."
        ),
        config_example=("rules:\n  process_call_literal:\n    enabled: true"),
        examples=[
            RuleExample(
                code="RunProcess('pLoad_Customer', 'pYear', '2026');", valid=True
            ),
            RuleExample(code="ExecuteProcess('pBuild_Dimensions');", valid=True),
            RuleExample(
                code="RunProcess(pProcessName);",
                description="Variable as process name",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C310"

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context: LintContext):
        expr = statement.expression
        if not isinstance(expr, FunctionCall):
            return []

        if expr.name.lower() not in {"runprocess", "executeprocess"}:
            return []

        first_arg = expr.args[0] if expr.args else None
        if isinstance(first_arg, String):
            return []

        token = get_node_token(expr)
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )

        return [
            LintIssue(
                message=(
                    f"{expr.name}() first argument must be a string literal process name "
                    "(for clear lineage)"
                ),
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]
