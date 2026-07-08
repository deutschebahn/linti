"""Rule S340 – Filter ODBC data source rows in SQL, not in the TI script.

When an ODBC data source returns every row and the filtering happens only in
the TI script — via ``ItemSkip()`` or cube writes that are *always* guarded by
an ``IF`` — the server pulls rows it immediately discards.  Pushing the filter
into a SQL ``WHERE`` clause is both faster and clearer.

This rule fires only for ODBC data sources whose query has no ``WHERE`` clause,
and only in the record-processing blocks (Metadata, Data).

``DatasourceType`` and ``DatasourceQuery`` can be reassigned in the Prolog (they
are TI predefined variables); the runtime value wins over the process metadata.
The rule reads the override through the constant propagation index.  A
``DatasourceType`` that cannot be resolved to a single statically known value
silences the rule (a genuine ODBC/non-ODBC ambiguity is not worth guessing).
``DatasourceQuery`` is checked more leniently: if a conditional override (e.g.
an ``IF`` with no ``ELSE``) leaves *any* statically known variant without a
``WHERE`` clause, the rule still fires, since that variant's rows are pulled
unfiltered from SQL on whichever path reaches it.
"""

import re
from dataclasses import dataclass, field

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    Assignment,
    ExpressionStatement,
    FunctionCall,
    IfStatement,
    Program,
    WhileStatement,
    get_node_token,
    iter_expression_nodes,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

#: Cube-write functions whose exclusively-conditional use signals that row
#: filtering is being done in the TI script instead of in SQL.
WRITE_FUNCTIONS = frozenset({"cellputn", "cellputs", "cellincrementn"})

_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)

#: The datasource was overridden in the script to a value we cannot read
#: statically — so nothing can be proven and the rule must stay silent.
_DYNAMIC = object()


def _has_where(query: str) -> bool:
    """True when *query* contains a SQL ``WHERE`` keyword."""
    return _WHERE_RE.search(query) is not None


def _resolve_override(context: LintContext, name: str, metadata_value):
    """Resolve a datasource setting, honouring a Prolog override.

    Returns the statically known override value when the script reassigns
    *name* (a TI predefined variable such as ``DatasourceType``), the
    *metadata_value* when it is never reassigned, or :data:`_DYNAMIC` when it is
    reassigned to a value that cannot be read statically (so the caller must not
    fall back to the — now stale — metadata value).
    """
    # Query at line 0: the value entering the block, i.e. after the Prolog runs
    # but before any reassignment inside Metadata/Data itself.
    pv = context.possible_values(name, 0)
    if not pv.assigned:
        return metadata_value
    return pv.exact if isinstance(pv.exact, str) else _DYNAMIC


def _query_may_lack_where(context: LintContext, metadata_value) -> bool:
    """True when the ODBC query provably has no ``WHERE`` clause on at least
    one reachable path.

    A Prolog override of ``DatasourceQuery`` may apply on only some paths
    (e.g. an ``IF`` with no ``ELSE``): if *any* statically known variant has
    no ``WHERE`` clause, the rows on that path are still pulled unfiltered
    from SQL, so it counts even when other variants are safe. A variant that
    cannot be read statically at all proves nothing and is skipped.
    """
    pv = context.possible_values("DatasourceQuery", 0)
    if not pv.assigned:
        return bool(metadata_value) and not _has_where(metadata_value)
    return pv.any_of(lambda v: isinstance(v, str) and not _has_where(v))


def _iter_calls(node):
    """Yield every FunctionCall in an expression subtree."""
    return (n for n in iter_expression_nodes(node) if isinstance(n, FunctionCall))


@dataclass
class _Scan:
    """Calls found while walking a block, tagged by conditional context."""

    item_skips: list = field(default_factory=list)
    writes: list = field(default_factory=list)  # (call, conditional: bool)


def _classify(call: FunctionCall, in_conditional: bool, acc: _Scan) -> None:
    name = call.name.lower()
    if name == "itemskip":
        acc.item_skips.append(call)
    elif name in WRITE_FUNCTIONS:
        acc.writes.append((call, in_conditional))


def _always_writes(statements: list) -> bool:
    """True when every path through *statements* performs a cube write.

    An ``IF`` whose ``then``/``else`` branches both always write does not
    make the write conditional from the caller's point of view — a record
    reaching this point always ends up writing somewhere, regardless of
    which branch it takes. A missing ``ELSE`` (or a loop, which may run
    zero times) can never be proven to always write.
    """
    for stmt in statements:
        if isinstance(stmt, IfStatement):
            if _always_writes(stmt.then_body) and _always_writes(stmt.else_body or []):
                return True
        elif isinstance(stmt, Assignment):
            if any(
                call.name.lower() in WRITE_FUNCTIONS for call in _iter_calls(stmt.right)
            ):
                return True
        elif isinstance(stmt, ExpressionStatement):
            if any(
                call.name.lower() in WRITE_FUNCTIONS
                for call in _iter_calls(stmt.expression)
            ):
                return True
    return False


def _scan(statements: list, in_conditional: bool, acc: _Scan) -> None:
    """Walk statements, tracking whether a call sits inside an ``IF`` branch."""
    for stmt in statements:
        if isinstance(stmt, IfStatement):
            for call in _iter_calls(stmt.condition):
                _classify(call, in_conditional, acc)
            exhaustive = _always_writes(stmt.then_body) and _always_writes(
                stmt.else_body or []
            )
            branch_conditional = in_conditional if exhaustive else True
            _scan(stmt.then_body, branch_conditional, acc)
            _scan(stmt.else_body or [], branch_conditional, acc)
        elif isinstance(stmt, WhileStatement):
            for call in _iter_calls(stmt.condition):
                _classify(call, in_conditional, acc)
            # A loop is not a record filter: keep the surrounding conditionality.
            _scan(stmt.body, in_conditional, acc)
        elif isinstance(stmt, Assignment):
            for call in _iter_calls(stmt.right):
                _classify(call, in_conditional, acc)
        elif isinstance(stmt, ExpressionStatement):
            for call in _iter_calls(stmt.expression):
                _classify(call, in_conditional, acc)


class SqlWhereFilteringRule(BaseStatementRule):
    """Flags TI-side row filtering when the ODBC query lacks a ``WHERE`` clause."""

    CONFIG_KEY = "sql_where_filtering"
    METADATA = RuleMetadata(
        name="Filter ODBC Rows in SQL",
        description=(
            "Flags ItemSkip() or exclusively conditional writes in Metadata/Data "
            "when the ODBC data source query has no WHERE clause"
        ),
        auto_fix=False,
        explanation=(
            "When an ODBC data source returns all rows and the filtering happens "
            "only in the TI script, the server pulls rows it immediately "
            "discards. This is reported in the Metadata and Data blocks when the "
            "data source query has no WHERE clause and either:\n"
            "- ItemSkip() is used to skip records, or\n"
            "- every cube write (CellPutN, CellPutS, CellIncrementN) is guarded "
            "by an IF, so no unconditional write ever happens.\n\n"
            "Move the filter into a SQL WHERE clause so the database returns only "
            "the rows the process needs.\n\n"
            "A DatasourceType/DatasourceQuery reassignment in the Prolog "
            "overrides the process metadata and is used instead.\n\n"
            "Inspired by the Bedrock TM1 best practices "
            "(https://github.com/cubewise-code/bedrock)."
        ),
        config_example=("rules:\n  sql_where_filtering:\n    enabled: true"),
        examples=[
            RuleExample(
                code=(
                    "# Data block, ODBC query: SELECT ... FROM t\n"
                    "IF(vRegion @= 'EMEA');\n"
                    "  CellPutN(vAmount, 'Sales', vRegion, vMonth);\n"
                    "ENDIF;"
                ),
                description="all writes conditional, no WHERE — filter in SQL",
                valid=False,
            ),
            RuleExample(
                code=(
                    "# Data block, ODBC query: SELECT ... FROM t\n"
                    "IF(vRegion @= 'EMEA');\n"
                    "  ItemSkip();\n"
                    "ENDIF;"
                ),
                description="ItemSkip() filters rows, no WHERE — filter in SQL",
                valid=False,
            ),
            RuleExample(
                code=(
                    "# Data block, ODBC query: SELECT ... FROM t WHERE region = ?\n"
                    "CellPutN(vAmount, 'Sales', vRegion, vMonth);"
                ),
                description="filtering done in SQL WHERE clause",
                valid=True,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "S340"

    def interested_in(self):
        return [Program]

    def visit(self, statement, context: LintContext):
        if context.block not in ("metadata", "data"):
            return []

        # DatasourceType/DatasourceQuery can be overridden in the Prolog; the
        # runtime value wins over the process metadata.
        ds_type = _resolve_override(context, "DatasourceType", context.datasource_type)
        if ds_type is _DYNAMIC or (ds_type or "").lower() != "odbc":
            return []
        if not _query_may_lack_where(context, context.datasource_query):
            return []

        acc = _Scan()
        _scan(statement.statements, in_conditional=False, acc=acc)

        issues: list[LintIssue] = []
        if acc.item_skips:
            issues.append(
                self._issue(
                    acc.item_skips[0],
                    "ItemSkip() filters records in the TI script while the ODBC "
                    "data source query has no WHERE clause; filter rows in SQL "
                    "instead",
                )
            )
        if acc.writes and all(conditional for _, conditional in acc.writes):
            issues.append(
                self._issue(
                    acc.writes[0][0],
                    "all cube writes in this block are conditional and the ODBC "
                    "data source query has no WHERE clause; filter rows in SQL "
                    "instead of skipping them in TI",
                )
            )
        return issues

    def _issue(self, call: FunctionCall, message: str) -> LintIssue:
        token = get_node_token(call)
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )
        return LintIssue(
            rule_id=self.RULE_ID,
            message=message,
            line=line,
            column=column,
            position=position,
        )
