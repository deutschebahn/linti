"""C154: a data source variable is assigned after the data source was opened."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Assignment, Identifier, get_node_token
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

#: The data source local variables of the IBM TurboIntegrator reference,
#: lower-cased. Each one describes the data source.
#:
#: The DatasourceASCII* settings are left out on purpose: TM1 also reads
#: DatasourceASCIIDelimiter and DatasourceASCIIQuoteCharacter when ASCIIOutput
#: and TextOutput write a record, so a late assignment is a common way to shape
#: an export file (Bedrock sets DatasourceASCIIQuoteCharacter = '' in the
#: Epilog before TextOutput) and is not a mistake.
DATA_SOURCE_VARIABLES = frozenset(
    {
        "datasourcecubeview",
        "datasourcedimensionsubset",
        "datasourcejsonrootpointer",
        "datasourcejsonvariablemapping",
        "datasourcenameforclient",
        "datasourcenameforserver",
        "datasourcepassword",
        "datasourcequery",
        "datasourcetype",
        "datasourceusername",
    }
)

_LATE_SECTIONS = ("metadata", "data", "epilog")


class DataSourceAssignedAfterPrologRule(BaseStatementRule):
    """Report an assignment to a Datasource* variable outside the Prolog."""

    CONFIG_KEY = "data_source_assigned_after_prolog"
    METADATA = RuleMetadata(
        name="Data Source Assigned After Prolog",
        description="Detects assignments to data source variables in Metadata, Data or Epilog",
        explanation=(
            "IBM runs the Prolog before the data source is opened; Metadata "
            "and Data then process its records. Assigning a data source "
            "variable such as DatasourceQuery, DatasourceNameForServer or "
            "DatasourceType is how a process chooses its source at run time, "
            "and that only works in the Prolog. In Metadata, Data or Epilog the "
            "source has already been opened, so the assignment does not change "
            "what the process reads. A filtered query set in Data, for example, "
            "leaves the process loading the unfiltered original.\n\n"
            "Checked variables are the data source variables of the IBM "
            "reference: DatasourceType, DatasourceNameForServer, "
            "DatasourceNameForClient, DatasourceQuery, DatasourceUsername, "
            "DatasourcePassword, DatasourceCubeview, DatasourceDimensionSubset, "
            "DatasourceJsonRootPointer and DatasourceJsonVariableMapping. "
            "Matching is case-insensitive. Reading them anywhere is fine.\n\n"
            "The DatasourceASCII* settings are not checked: ASCIIOutput and "
            "TextOutput also use DatasourceASCIIDelimiter and "
            "DatasourceASCIIQuoteCharacter for the records they write, so "
            "setting them later to shape an export file is legitimate.\n\n"
            "IBM documents the order, not the effect of a late assignment; that "
            "the assignment is ignored follows from it.\n\n"
            "Fix it by moving the assignment into the Prolog."
        ),
        config_example="rules:\n  data_source_assigned_after_prolog:\n    enabled: true",
        examples=[
            RuleExample(
                code="DatasourceQuery = 'SELECT * FROM GL WHERE Period = ' | pPeriod;",
                description="Prolog: choose the query before the source opens",
                parameters=["pPeriod"],
            ),
            RuleExample(
                code="IF(DatasourceType @= 'ODBC');\n    nOdbc = 1;\nENDIF;",
                description="Data: reading a data source variable is fine",
                procedure="data",
            ),
            RuleExample(
                code="DatasourceASCIIQuoteCharacter = '';\nTextOutput('out.csv', 'a;b');",
                description="Epilog: the ASCII settings also shape TextOutput",
                procedure="epilog",
            ),
            RuleExample(
                code="DatasourceQuery = 'SELECT * FROM GL WHERE Period = ' | pPeriod;",
                description="Data: the source is already open",
                valid=False,
                procedure="data",
                parameters=["pPeriod"],
            ),
            RuleExample(
                code="DatasourceNameForServer = 'next.csv';",
                description="Epilog: the source has already been read",
                valid=False,
                procedure="epilog",
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C154"

    def interested_in(self):
        return [Assignment]

    def visit(self, statement, context: LintContext):
        section = (context.block or "").lower()
        if section not in _LATE_SECTIONS:
            return []
        target = statement.left
        if not isinstance(target, Identifier):
            return []
        if target.name.lower() not in DATA_SOURCE_VARIABLES:
            return []
        token = get_node_token(target)
        return [
            LintIssue(
                message=(
                    f"{target.name} is assigned in {section.title()}, but the "
                    "data source is opened when the Prolog ends, so this does "
                    "not change it. Assign it in the Prolog."
                ),
                line=token.line if token else 0,
                column=token.column if token else 0,
                position=token.position if token else 0,
                rule_id=self.RULE_ID,
            )
        ]
