"""Rule N220: Variable Naming Convention - data source variables must start with 'v'."""

from linti.rules.naming.parameter_naming_rule import _MetadataNamingRule
from linti.rules.Rule import RuleExample, RuleMetadata


class VariableNamingRule(_MetadataNamingRule):
    """
    Enforces that TM1 data source variables start with lowercase 'v'.

    This rule validates variable names defined in the YAML Variables section.
    All data source variables should follow the naming convention: vVariableName

    Example:
        Valid: vDimension, vHierarchy, vParent
        Invalid: Dimension, hierarchy, VariableName
    """

    CONFIG_KEY = "variable_naming"
    PREFIX = "v"
    LABEL = "Data source variable"
    EXAMPLE = "vDimension"
    COLLECTION_ATTR = "variables"
    LINES_ATTR = "variable_lines"
    METADATA = RuleMetadata(
        name="Data Source Variable Naming",
        description="Enforces that data source variables start with lowercase 'v'",
        auto_fix=False,
        explanation=(
            "Enforces that TM1 data source variables start with lowercase 'v'.\n\n"
            "Data source variables are the columns from the data source, defined in "
            "the YAML Variables section. These variables are automatically populated "
            "by TM1 during Metadata and Data processing."
        ),
        config_example=("rules:\n" "  variable_naming:\n" "    enabled: true"),
        examples=[
            RuleExample(
                code="vDimension", description="Valid variable name", valid=True
            ),
            RuleExample(code="vHierarchy", valid=True),
            RuleExample(
                code="Dimension", description="Missing 'v' prefix", valid=False
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "N220"
