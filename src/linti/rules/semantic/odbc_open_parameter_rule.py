"""Rule X120: Validate ODBCOpen password parameter is defined in process parameters."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    Identifier,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ODBCOpenParameterRule(BaseStatementRule):
    """
    Validates that ODBCOpen(Source, ClientName, Password) third parameter is a defined TI parameter.

    The password parameter must be declared in the process Parameters section.
    """

    CONFIG_KEY = "odbc_open_parameter"
    DEPRECATED_IDS = ["S330"]
    METADATA = RuleMetadata(
        name="ODBCOpen Password Parameter",
        description="Validates that ODBCOpen() password parameter is a defined TI parameter",
        auto_fix=False,
        explanation=(
            "Validates that ODBCOpen(Source, ClientName, Password) requires the third "
            "parameter (password) to be a defined TI process parameter.\n\n"
            "This ensures that sensitive credentials are managed through process "
            "parameters rather than hardcoded or undefined values.\n\n"
            "Requirements:\n"
            "1. Third argument must be an Identifier (not a string literal)\n"
            "2. Parameter name must start with 'p' (TI parameter naming convention)\n"
            "3. Parameter must be declared in the process Parameters section"
        ),
        config_example=("rules:\n  odbc_open_parameter:\n    enabled: true"),
        examples=[
            RuleExample(
                code="ODBCOpen('MyDatasource', 'AdminUser', pPassword);",
                description="Password as defined parameter",
                valid=True,
            ),
            RuleExample(
                code="ODBCOpen('MyDatasource', 'AdminUser', 'hardcodedPassword');",
                description="Hardcoded password",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "X120"

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context: LintContext):
        expr = statement.expression
        if not isinstance(expr, FunctionCall):
            return []

        if expr.name.lower() != "odbcopen":
            return []

        if len(expr.args) < 3:
            token = get_node_token(expr)
            line, column, position = (
                (token.line, token.column, token.position) if token else (0, 0, 0)
            )
            return [
                LintIssue(
                    message="ODBCOpen() requires at least 3 arguments (Source, ClientName, Password)",
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            ]

        third_arg = expr.args[2]
        if not isinstance(third_arg, Identifier):
            token = get_node_token(expr)
            line, column, position = (
                (token.line, token.column, token.position) if token else (0, 0, 0)
            )
            return [
                LintIssue(
                    message="ODBCOpen() password parameter must be a TI parameter",
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            ]

        param_name = third_arg.name
        declared_parameters = {
            parameter.lower() for parameter in (context.parameters or [])
        }

        if param_name.lower() not in declared_parameters:
            token = get_node_token(expr)
            line, column, position = (
                (token.line, token.column, token.position) if token else (0, 0, 0)
            )
            return [
                LintIssue(
                    message=f"ODBCOpen() password parameter '{param_name}' is not defined in process Parameters section",
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            ]

        return []
