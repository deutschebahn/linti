from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Assignment
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ConstantAssignmentRule(BaseStatementRule):
    """
    Enforces that constants (variables starting with 'c') are assigned only once.
    """

    CONFIG_KEY = "constant_assignment"
    DEPRECATED_IDS = ["S220"]

    METADATA = RuleMetadata(
        name="Single-assignment Constants",
        description="Enforces that constants (c-prefixed variables) are assigned only once",
        auto_fix=False,
        explanation=(
            "Enforces that constants (variables starting with 'c') are assigned only "
            "once throughout the process.\n\n"
            "This rule is automatically enabled when `allow_constant_prefix: true` is "
            "set in the variable_prefix rule."
        ),
        config_example=(
            "rules:\n"
            "  variable_prefix:\n"
            "    enabled: true\n"
            "    allow_constant_prefix: true  # Enables C220"
        ),
        examples=[
            RuleExample(
                code="cRate = 1.5;", description="First assignment", valid=True
            ),
            RuleExample(
                code="cRate = 1.5;\ncRate = 2.0;",
                description="Reassignment",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C220"

    def __init__(self):
        self._assigned = {}

    def reset(self) -> None:
        self._assigned = {}

    def interested_in(self):
        return [Assignment]

    def visit(self, statement, context: LintContext):
        var_name = statement.left.name
        if not var_name.startswith("c"):
            return []

        token = statement.left.token
        if not token:
            line, column, position = 0, 0, 0
        else:
            line, column, position = token.line, token.column, token.position

        if var_name in self._assigned:
            first_line, first_column, _ = self._assigned[var_name]
            return [
                LintIssue(
                    message=(
                        "Constant variables must be assigned only once "
                        f"(found '{var_name}', first assignment at line {first_line}, "
                        f"column {first_column})"
                    ),
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            ]

        self._assigned[var_name] = (line, column, position)
        return []
