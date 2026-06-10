"""Rule S210: Read-Only Parameters and Variables - parameters and variables must not be modified."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Assignment
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ReadOnlyParameterVariableRule(BaseStatementRule):
    """
    Enforces that TM1 parameters and data source variables are read-only.

    Parameters (from the Parameters section) and data source variables (from the Variables
    section) should not be modified in the process code. If you need to change their values,
    assign them to a new variable first.
    """

    CONFIG_KEY = "readonly_parameter_variable"
    METADATA = RuleMetadata(
        name="Read-only Parameters and Variables",
        description="Enforces that parameters and data source variables are read-only",
        auto_fix=False,
        explanation=(
            "Enforces that TM1 parameters and data source variables are read-only.\n\n"
            "Parameters (from the Parameters section) and data source variables (from "
            "the Variables section) should not be modified in the process code. These "
            "values are inputs to your process and should be treated as immutable. "
            "If you need to change their values, assign them to a new local variable first.\n\n"
            "Why this matters:\n"
            "- Parameters represent user input or configuration values\n"
            "- Variables represent data from the source that should be preserved\n"
            "- Modifying these can make debugging difficult\n"
            "- Following this convention makes code more readable and maintainable"
        ),
        config_example=(
            "rules:\n" "  readonly_parameter_variable:\n" "    enabled: true"
        ),
        examples=[
            RuleExample(
                code="cLogOutput = pLogOutput;\ncLogOutput = 0;",
                description="Read parameter, modify local copy",
                valid=True,
            ),
            RuleExample(
                code="pLogOutput = 0;",
                description="Modifying a parameter",
                valid=False,
            ),
            RuleExample(
                code="vDimension = 'NewValue';",
                description="Modifying a data source variable",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "S210"

    def interested_in(self):
        """This rule is interested in Assignment statements."""
        return [Assignment]

    def visit(self, statement, context: LintContext):
        """
        Check if parameters or variables are being assigned to.

        Args:
            statement: The Assignment AST node
            context: LintContext with block, parameters, variables

        Returns:
            List of LintIssue objects
        """
        issues = []

        # Get the variable being assigned to
        var_name = statement.left.name

        # Get line/column/position from the token
        token = statement.left.token
        if not token:
            line, column, position = 0, 0, 0
        else:
            line, column, position = token.line, token.column, token.position

        # Check if it's a parameter
        if context.parameters and var_name in context.parameters:
            issue = LintIssue(
                rule_id=self.RULE_ID,
                message=f"Parameter '{var_name}' must not be modified. Assign to a new variable instead.",
                line=line,
                column=column,
                position=position,
            )
            issues.append(issue)

        # Check if it's a data source variable
        if context.variables and var_name in context.variables:
            issue = LintIssue(
                rule_id=self.RULE_ID,
                message=f"Data source variable '{var_name}' must not be modified. Assign to a new variable instead.",
                line=line,
                column=column,
                position=position,
            )
            issues.append(issue)

        return issues
