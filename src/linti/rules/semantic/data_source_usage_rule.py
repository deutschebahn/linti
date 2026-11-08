"""C153: the effective data source and the Metadata/Data code disagree."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue, Severity
from linti.parser.ast import (
    Program,
    UnknownStatement,
    get_node_token,
    statement_expression,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.semantic.process_facts import DataSourceState

_RECORD_SECTIONS = ("metadata", "data")


class DataSourceUsageRule(BaseStatementRule):
    """Compare the data source in effect after Prolog with Metadata/Data code."""

    CONFIG_KEY = "data_source_usage"
    METADATA = RuleMetadata(
        name="Data Source Usage",
        description="Detects Metadata/Data code that never runs without a data source, and data sources nothing uses",
        severity=Severity.WARNING,
        explanation=(
            "Metadata and Data run once per data source record. The rule "
            "compares the data source in effect when Prolog ends with the "
            "executable code in Metadata and Data. That data source is the one "
            "in the process properties, followed through statically provable "
            "Prolog assignments to DatasourceType, so a data source set up in "
            "Prolog counts like one in the properties.\n\n"
            "- Code without data source: the effective data source is None, "
            "but Metadata or Data contains executable code, which is skipped. "
            "Reported once per process, at the first affected statement, "
            "naming every affected section.\n"
            "- Unused data source: a data source is in effect, but Metadata "
            "and Data are both empty. Reported at the Prolog assignment to "
            "DatasourceType when there is one, else at the start of the "
            "process. A drill-through use (ReturnSQLTableHandle, "
            "ReturnViewHandle, ReturnCSVTableHandle) counts as use. Set "
            "check_unused_source: false to turn this finding off.\n"
            "- Data source without variables: the process is saved without a "
            "data source and declares no variables, but Prolog turns one on by "
            "assigning DatasourceType while Metadata or Data contain code. The "
            "variables belong to the saved definition, so the records arrive "
            "with nothing to read their columns into, and tools that read the "
            "saved definition do not see the data source. Reported at the "
            "Prolog assignment. Save the process with its data source and "
            "variables, and keep Prolog for choosing which file, view or query "
            "it reads. Set check_runtime_source: false to turn this finding "
            "off.\n\n"
            "Comments, blank lines and bare section markers count as empty; "
            "generated statements count as code. When the data source cannot "
            "be determined (a plain .ti file without process properties and "
            "without a provable Prolog assignment, a DatasourceType assigned "
            "from a parameter or inside a branch, or an unparseable Prolog "
            "statement mentioning DatasourceType), the rule stays silent. The fix is manual: move the code, set up the "
            "data source, or remove it."
        ),
        config_example=(
            "rules:\n"
            "  data_source_usage:\n"
            "    enabled: true\n"
            "    severity: warning\n"
            "    # Set to false to drop the unused-data-source finding.\n"
            "    check_unused_source: true\n"
            "    # Set to false to drop the data-source-without-variables finding.\n"
            "    check_runtime_source: true"
        ),
        examples=[
            RuleExample(
                code="nCount = nCount + 1;",
                description="Data runs once per record of the ASCII file",
                procedure="data",
                datasource_type="ASCII",
            ),
            RuleExample(
                code="ExecuteProcess('load.sales');",
                description="Prolog-only process without a data source",
                datasource_type="None",
            ),
            RuleExample(
                code="nCount = nCount + 1;",
                description="Data is skipped, there is no data source",
                valid=False,
                procedure="data",
                datasource_type="None",
            ),
            RuleExample(
                code="ExecuteProcess('load.sales');",
                description="An ASCII data source that Metadata and Data never read",
                valid=False,
                datasource_type="ASCII",
            ),
        ],
    )

    def __init__(
        self, check_unused_source: bool = True, check_runtime_source: bool = True
    ):
        """
        Args:
            check_unused_source: Whether a data source with empty Metadata and
                Data is reported.
            check_runtime_source: Whether a data source that only Prolog turns
                on, in a process saved without one and without variables, is
                reported.
        """
        self._check_unused_source = check_unused_source
        self._check_runtime_source = check_runtime_source

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [
            cls(
                check_unused_source=rule_cfg.get("check_unused_source", True),
                check_runtime_source=rule_cfg.get("check_runtime_source", True),
            )
        ]

    @property
    def RULE_ID(self) -> str:
        return "C153"

    def interested_in(self):
        # Visited once per section with the whole tree, so the rule can report
        # once per process from whichever section the finding belongs in.
        return [Program]

    def visit(self, statement, context: LintContext):
        facts = context.process_facts
        section = (context.block or "").lower()
        if facts is None:
            return []
        state = facts.effective_data_source
        if state is DataSourceState.NONE:
            return self._code_without_source(facts, section)
        if state is DataSourceState.PRESENT:
            issues = []
            if self._check_unused_source:
                issues += self._unused_source(facts, section)
            if self._check_runtime_source:
                issues += self._runtime_source_without_variables(facts, section)
            return issues
        return []

    def _code_without_source(self, facts, section: str) -> list[LintIssue]:
        affected = [s for s in _RECORD_SECTIONS if facts.has_code(s)]
        # Report from the first affected section rules actually run on: an
        # unparseable one is never visited, and the finding must not vanish.
        anchors = [s for s in affected if facts.is_linted(s)]
        if not anchors or section != anchors[0]:
            return []
        names = " and ".join(s.title() for s in affected)
        message = f"{names} will be skipped because the effective data source is None."
        return [self._issue(message, facts.first_statement(section))]

    def _unused_source(self, facts, section: str) -> list[LintIssue]:
        if any(facts.has_code(s) for s in _RECORD_SECTIONS):
            return []
        if facts.uses_drillthrough:
            return []
        linted = [s for s in facts.present_sections() if facts.is_linted(s)]
        anchor = "prolog" if "prolog" in linted else (linted or [None])[0]
        if section != anchor:
            return []
        message = (
            "A data source is configured, but neither Metadata nor Data "
            "contains executable statements."
        )
        node = facts.data_source_assignment if section == "prolog" else None
        return [self._issue(message, node)]

    def _runtime_source_without_variables(self, facts, section: str) -> list[LintIssue]:
        if section != "prolog":
            return []
        if facts.stored_data_source is not DataSourceState.NONE:
            return []
        if facts.data_source_assignment is None or facts.declares_variables:
            return []
        if not any(facts.has_code(s) for s in _RECORD_SECTIONS):
            return []  # the unused-data-source finding covers this case
        message = (
            "DatasourceType turns on a data source at run time, but the process "
            "is saved without one and declares no variables, so Metadata and "
            "Data cannot read the record columns. Save the process with its "
            "data source and variables."
        )
        return [self._issue(message, facts.data_source_assignment)]

    def _issue(self, message: str, node) -> LintIssue:
        """A finding at *node*'s first token, or at the section start."""
        token = None
        if isinstance(node, UnknownStatement):
            token = node.tokens[0] if node.tokens else None
        elif node is not None:
            # An assignment's own token is its "="; the target is where the
            # statement starts.
            token = (
                get_node_token(getattr(node, "left", None))
                or get_node_token(node)
                or get_node_token(statement_expression(node))
            )
        return LintIssue(
            message=message,
            line=token.line if token else 1,
            column=token.column if token else 1,
            position=token.position if token else 0,
            rule_id=self.RULE_ID,
        )
