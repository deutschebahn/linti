"""Process-wide structural facts that per-section rules cannot see on their own.

A rule runs on one section at a time. Some questions span sections, e.g.
whether Metadata and Data will run at all given the data source that is in
effect when Prolog ends. :class:`ProcessFacts` answers them from the shared
per-run :class:`~linti.linter.parse_cache.SectionParseCache` and the
:class:`~linti.semantic.constant_evaluation.ConstantEvaluationIndex`, so
nothing is parsed twice. Like the index it is built once per process and
computes each answer lazily.
"""

from __future__ import annotations

from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Iterator, Optional

from linti.parser.ast import (
    Assignment,
    FunctionCall,
    Identifier,
    IfStatement,
    Statement,
    UnknownStatement,
    WhileStatement,
    iter_expression_nodes,
    statement_expression,
)

if TYPE_CHECKING:
    from linti.linter.parse_cache import SectionParseCache
    from linti.model.process_ir import ProcessIR
    from linti.parser.ast import Program
    from linti.semantic.constant_evaluation import ConstantEvaluationIndex

SECTIONS = ("prolog", "metadata", "data", "epilog")

#: Data source types that mean "no data source": Metadata and Data are skipped.
#: ``None`` is how the process properties store it; Prolog code assigns
#: ``'NULL'``.
_NO_SOURCE_TYPES = {"none", "null", ""}

#: Functions that hand the process's data source to a drill-through, so a data
#: source with empty Metadata/Data is still in use.
DRILLTHROUGH_FUNCTIONS = {
    "returnsqltablehandle",
    "returnviewhandle",
    "returncsvtablehandle",
}

#: A line past the end of any section, to ask for the value when Prolog ends.
_END_OF_SECTION = 10**9


class DataSourceState(Enum):
    NONE = "none"
    PRESENT = "present"
    UNKNOWN = "unknown"


def iter_statements(statements) -> Iterator[Statement]:
    """Every statement in *statements*, nested IF/WHILE bodies included."""
    for stmt in statements:
        yield stmt
        if isinstance(stmt, IfStatement):
            yield from iter_statements(stmt.then_body)
            yield from iter_statements(stmt.else_body or [])
        elif isinstance(stmt, WhileStatement):
            yield from iter_statements(stmt.body)


def classify_data_source(value: object) -> DataSourceState:
    """Map a stored or assigned ``DatasourceType`` value to its state."""
    if not isinstance(value, str):
        return DataSourceState.UNKNOWN
    if value.strip().lower() in _NO_SOURCE_TYPES:
        return DataSourceState.NONE
    return DataSourceState.PRESENT


class ProcessFacts:
    """Lazily computed cross-section facts about one process."""

    def __init__(
        self,
        process: "ProcessIR",
        cache: "SectionParseCache",
        constants: Optional["ConstantEvaluationIndex"] = None,
    ) -> None:
        self._process = process
        self._cache = cache
        self._constants = constants

    def present_sections(self) -> list[str]:
        """Sections the process has at all, in execution order."""
        return [s for s in SECTIONS if getattr(self._process, s, None) is not None]

    def first_statement(self, section: str) -> Optional[Statement]:
        """The section's first executable statement, or ``None`` if it has none.

        Comments, blank lines and generated-section markers produce no
        statement. An unparseable statement counts as code, and so does a
        section that failed to parse at all (returned as a bare
        :class:`UnknownStatement`).
        """
        if getattr(self._process, section, None) is None:
            return None
        parsed = self._cache.get(section)
        if parsed.ast is None:
            return UnknownStatement([], "unparseable section")
        statements = parsed.ast.statements
        return statements[0] if statements else None

    def section_ast(self, section: str) -> Optional["Program"]:
        """The parsed section, or ``None`` when it is absent or unparseable."""
        if getattr(self._process, section, None) is None:
            return None
        return self._cache.get(section).ast

    @property
    def declares_variables(self) -> bool:
        """Whether the process declares any data source variables."""
        return bool(self._process.variables)

    def has_code(self, section: str) -> bool:
        return self.first_statement(section) is not None

    def is_linted(self, section: str) -> bool:
        """Whether rules run on *section* at all.

        A section that failed to parse (nesting too deep) is reported as P900
        and never handed to a rule, so a process-level finding must be placed
        in a section that is linted.
        """
        if getattr(self._process, section, None) is None:
            return False
        return self._cache.get(section).ast is not None

    @cached_property
    def stored_data_source(self) -> DataSourceState:
        """The data source as the process properties define it."""
        if self._process.datasource_type is None:
            # The format carries no data source metadata (plain .ti).
            return DataSourceState.UNKNOWN
        return classify_data_source(self._process.datasource_type)

    @cached_property
    def effective_data_source(self) -> DataSourceState:
        """The data source in effect when Prolog ends and Metadata would start.

        Starts from the stored definition and follows statically provable
        Prolog assignments to ``DatasourceType``. Anything dynamic or
        branch-dependent is UNKNOWN.
        """
        if self._prolog_may_hide_data_source_change:
            return DataSourceState.UNKNOWN
        if self.data_source_assignment is None:
            return self.stored_data_source
        # A provable Prolog assignment settles the question even when the
        # format stores no data source (plain .ti): the index starts from the
        # stored value when there is one and joins branches against it.
        if self._constants is None:
            return DataSourceState.UNKNOWN
        value = self._constants.possible_values_at(
            "DatasourceType", "prolog", _END_OF_SECTION
        ).exact
        return classify_data_source(value)

    @cached_property
    def _prolog_may_hide_data_source_change(self) -> bool:
        """Whether Prolog code the parser could not read may set the source.

        An unparseable Prolog, or an unparseable statement mentioning
        ``DatasourceType``, could change the data source invisibly, so the
        effective data source is unknown then.
        """
        if self._process.prolog is None:
            return False
        ast = self._cache.get("prolog").ast
        if ast is None:
            return True
        return any(
            isinstance(stmt, UnknownStatement)
            and any(
                str(getattr(token, "value", "")).lower() == "datasourcetype"
                for token in stmt.tokens
            )
            for stmt in iter_statements(ast.statements)
        )

    @cached_property
    def data_source_assignment(self) -> Optional[Assignment]:
        """The last Prolog assignment to ``DatasourceType``, if any."""
        if self._process.prolog is None:
            return None
        ast = self._cache.get("prolog").ast
        if ast is None:
            return None
        last = None
        for stmt in iter_statements(ast.statements):
            if (
                isinstance(stmt, Assignment)
                and isinstance(stmt.left, Identifier)
                and stmt.left.name.lower() == "datasourcetype"
            ):
                last = stmt
        return last

    @cached_property
    def uses_drillthrough(self) -> bool:
        """Whether any section hands the data source to a drill-through."""
        for section in self.present_sections():
            ast = self._cache.get(section).ast
            if ast is None:
                continue
            for stmt in iter_statements(ast.statements):
                expr = statement_expression(stmt)
                if expr is None:
                    continue
                for node in iter_expression_nodes(expr):
                    if (
                        isinstance(node, FunctionCall)
                        and node.name.lower() in DRILLTHROUGH_FUNCTIONS
                    ):
                        return True
        return False
