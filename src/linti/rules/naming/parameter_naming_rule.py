"""Rule N210: Parameter Naming Convention - parameters must start with 'p'."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Program
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class _MetadataNamingRule(BaseStatementRule):
    """
    Generic base for rules that validate naming conventions of
    YAML-declared metadata collections (parameters, variables, …).

    Subclasses set the five class-level knobs and get the full logic for free.
    """

    # -- override in subclasses ------------------------------------------------
    PREFIX: str = ""  # required first character, e.g. "p"
    LABEL: str = ""  # human label, e.g. "Parameter"
    EXAMPLE: str = ""  # example name, e.g. "pLogOutput"
    COLLECTION_ATTR: str = ""  # LintContext attribute, e.g. "parameters"
    LINES_ATTR: str = ""  # LintContext line-map, e.g. "parameter_lines"

    def interested_in(self):
        return [Program]

    def visit(self, statement, context: LintContext):
        collection = getattr(context, self.COLLECTION_ATTR, None)
        if not collection:
            return []

        line_map = getattr(context, self.LINES_ATTR, None) or {}
        issues: list[LintIssue] = []

        for name in collection:
            line = line_map.get(name, 1)

            if not name.startswith(self.PREFIX):
                issues.append(
                    LintIssue(
                        rule_id=self.RULE_ID,
                        message=f"{self.LABEL} '{name}' must start with lowercase '{self.PREFIX}'",
                        line=line,
                        column=1,
                        position=0,
                    )
                )
            elif len(name) == 1:
                issues.append(
                    LintIssue(
                        rule_id=self.RULE_ID,
                        message=f"{self.LABEL} '{self.PREFIX}' is too short, use descriptive names like '{self.EXAMPLE}'",
                        line=line,
                        column=1,
                        position=0,
                    )
                )

        return issues


class ParameterNamingRule(_MetadataNamingRule):
    """
    Enforces that TM1 process parameters start with lowercase 'p'.

    This rule validates parameter names defined in the YAML Parameters section.
    All parameters should follow the naming convention: pParameterName

    Example:
        Valid: pLogOutput, pFactor, pStrictErrorHandling
        Invalid: LogOutput, factor, ParameterName
    """

    CONFIG_KEY = "parameter_naming"
    PREFIX = "p"
    LABEL = "Parameter"
    EXAMPLE = "pLogOutput"
    COLLECTION_ATTR = "parameters"
    LINES_ATTR = "parameter_lines"
    METADATA = RuleMetadata(
        name="Parameter Naming",
        description="Enforces that parameters start with lowercase 'p'",
        auto_fix=False,
        explanation=(
            "Enforces that TM1 process parameters start with lowercase 'p'.\n\n"
            "Parameters are the input values defined in the YAML Parameters section "
            "of a TM1 TI process. Following a consistent naming convention makes it "
            "easy to identify parameters throughout the code."
        ),
        config_example=("rules:\n" "  parameter_naming:\n" "    enabled: true"),
        examples=[
            RuleExample(
                code="pLogOutput", description="Valid parameter name", valid=True
            ),
            RuleExample(code="pFactor", valid=True),
            RuleExample(
                code="LogOutput", description="Missing 'p' prefix", valid=False
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "N210"
