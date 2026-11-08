"""C152: a cube access needs an element whose buffered insert is still pending.

``DimensionElementInsert`` / ``HierarchyElementInsert`` are buffered. The new
element is in the dimension index at once (``DIMIX`` finds it), but cubes,
including ``}ElementAttributes_<dim>``, can address it only after the
Metadata phase has ended. Until then an attribute write is lost and a read
returns no value. Measured on PA 12.6.4:

* the phase spans Prolog and Metadata: an element inserted in the Prolog is
  still unreachable in the Metadata, on every source record;
* the buffered insert is the trigger: once it has run, an element inserted
  later in the phase is unreachable even when a Direct insert created it;
* elements that already existed are never affected.

The rule reports only what it can prove, walking the Prolog and the Metadata
AST path by path:

* the element is **provably new**: the insert sits in the branch of an ``IF``
  whose condition establishes ``DIMIX(dim, el) = 0`` or
  ``ElementIndex(dim, hier, el) = 0`` for that same element;
* the access targets the **same** dimension, hierarchy and element: equal
  literals (also through constant evaluation) or the same variable, not
  reassigned in between;
* the insert is pending on **every** path reaching the access. After an
  ``IF`` only entries both branches agree on survive; a branch that ends the
  path (``ProcessQuit``, ``ProcessError``, ``ItemSkip``, ...) does not count.

A Direct insert of the element makes it addressable and clears the entry,
unless a buffered insert into the same dimension ran before it on every path.
Unparseable statements clear all knowledge, and a ``WHILE`` body that contains
assignments or Direct inserts forgets what they may touch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    ExpressionStatement,
    FunctionCall,
    Identifier,
    IfStatement,
    Number,
    Program,
    String,
    UnaryExpression,
    UnknownStatement,
    WhileStatement,
    get_node_token,
    iter_function_calls,
    statement_expression,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.rules.semantic.conditional_control_flow_rule import (
    CONTROL_FLOW_STATEMENTS,
)
from linti.semantic.process_facts import iter_statements

#: A normalized argument: ``("lit", text)`` or ``("var", name)``.
Atom = tuple[str, str]
#: ``(dimension, hierarchy, element)``.
Key = tuple[Atom, Atom, Atom]
#: Where a pending insert happened: ``(section, line)``.
Origin = tuple[str, int]

#: The sections of the phase in which buffered inserts stay pending.
_PHASE_SECTIONS = ("prolog", "metadata")

#: Buffered inserts: name → (dimension, hierarchy, element) argument indexes.
_BUFFERED_INSERTS = {
    "dimensionelementinsert": (0, None, 2),
    "hierarchyelementinsert": (0, 1, 3),
}
_DIRECT_INSERTS = {
    "dimensionelementinsertdirect": (0, None, 2),
    "hierarchyelementinsertdirect": (0, 1, 3),
}
#: Attribute writes: name → (dimension, hierarchy, element) argument indexes.
_ATTRIBUTE_WRITES = {
    "attrputs": (1, None, 2),
    "attrputn": (1, None, 2),
    "elementattrputs": (1, 2, 3),
    "elementattrputn": (1, 2, 3),
}
#: Attribute reads: name → (dimension, hierarchy, element) argument indexes.
_ATTRIBUTE_READS = {
    "attrs": (0, None, 1),
    "attrn": (0, None, 1),
    "elementattrs": (0, 1, 2),
    "elementattrn": (0, 1, 2),
}
#: Cell access: name → (cube index, first coordinate index).
_CELL_WRITES = {"cellputs": (1, 2), "cellputn": (1, 2)}
_CELL_READS = {"cellgets": (0, 1), "cellgetn": (0, 1)}
#: The attribute cube of a dimension; its first coordinate is the element.
_ATTRIBUTE_CUBE_PREFIX = "}elementattributes_"
#: Calls after which the current path does not continue: they end the
#: process, the procedure or the record. ``Break`` only leaves a loop.
_PATH_ENDS = (CONTROL_FLOW_STATEMENTS - {"break"}) | {"itemskip"}
#: Existence probes: name → (dimension, hierarchy, element) argument indexes.
_INDEX_PROBES = {
    "dimix": (0, None, 1),
    "elementindex": (0, 1, 2),
}


def _normalize(text: str) -> str:
    """TM1 object names ignore case and spaces."""
    return text.replace(" ", "").lower()


@dataclass
class _State:
    """What is known on one execution path."""

    #: Elements proven absent on this path.
    absent: set[Key] = field(default_factory=set)
    #: Provably new elements with a pending insert → where it happened.
    pending: dict[Key, Origin] = field(default_factory=dict)
    #: Dimensions a buffered insert of a provably new element has edited on
    #: this path. A later Direct insert into them stays pending too.
    buffered_dims: set[Atom] = field(default_factory=set)
    #: The path has ended (ProcessQuit, ItemSkip, ...); nothing follows it.
    ended: bool = False

    def copy(self) -> _State:
        return _State(
            set(self.absent), dict(self.pending), set(self.buffered_dims), self.ended
        )

    def join(self, other: _State) -> _State:
        """Keep only what holds on both paths; an ended path adds nothing."""
        if self.ended:
            return other.copy()
        if other.ended:
            return self.copy()
        return _State(
            self.absent & other.absent,
            {key: at for key, at in self.pending.items() if key in other.pending},
            self.buffered_dims & other.buffered_dims,
        )

    def forget_variable(self, name: str) -> None:
        var = ("var", name)
        self.absent = {key for key in self.absent if var not in key}
        self.pending = {key: at for key, at in self.pending.items() if var not in key}
        self.buffered_dims.discard(var)

    def forget(self, key: Key) -> None:
        self.absent.discard(key)
        self.pending.pop(key, None)


class ElementUsedBeforeAvailableRule(BaseStatementRule):
    """Report a cube access to a provably new, still buffered element."""

    CONFIG_KEY = "element_used_before_available"
    SUPERSEDES = ("C151",)
    METADATA = RuleMetadata(
        name="Element Used Before Available",
        description="Detects cube access to an element whose buffered insert is not yet available",
        explanation=(
            "DimensionElementInsert and HierarchyElementInsert are buffered. The "
            "new element is in the dimension index at once, so DIMIX already "
            "finds it, but cubes, including }ElementAttributes_<dimension>, "
            "can address it only after the Metadata phase has ended. Until "
            "then an attribute write is lost and a read returns no value; the "
            "process only ends with minor errors.\n\n"
            "The phase spans Prolog and Metadata: an element inserted in the "
            "Prolog is still unreachable in Metadata, on every source record. "
            "Once a buffered insert has run, an element inserted later in the "
            "same dimension is unreachable as well, even when a Direct insert "
            "created it. Elements that already existed are not affected.\n\n"
            "The rule reports only what it can prove on one execution path:\n"
            "- the element is new: the insert sits in an IF branch whose "
            "condition establishes DIMIX(dim, el) = 0 or "
            "ElementIndex(dim, hier, el) = 0 for the same element;\n"
            "- the access targets the same dimension, hierarchy and element: "
            "equal literals, or the same variable not reassigned in between;\n"
            "- the insert is pending on every path to the access. A path that "
            "ends first (ProcessQuit, ProcessError, ProcessBreak, ItemReject, "
            "ItemSkip, a rollback) does not count.\n\n"
            "Checked writes: AttrPutS/N, ElementAttrPutS/N, and CellPutS/N to a "
            "}ElementAttributes_<dimension> cube. Checked reads: AttrS/N, "
            "ElementAttrS/N, and CellGetS/N from such a cube. Other cubes are "
            "skipped, because their dimension order is unknown. A Direct insert "
            "makes the element addressable at once, as long as no buffered "
            "insert into that dimension ran before it. Data and Epilog are "
            "fine, since the phase has ended by then.\n\n"
            "For the same call this finding replaces the general Discouraged "
            "Function Placement (C151) warning. Suppressing it with "
            "`# noqa: C152` lets the C151 warning through again.\n\n"
            "Fix it by moving the access to Data, or by inserting the element "
            "with the Direct variant, before any buffered insert into the "
            "dimension, if that fits the process."
        ),
        config_example=("rules:\n  element_used_before_available:\n    enabled: true"),
        examples=[
            RuleExample(
                code=(
                    "IF(DIMIX('Product', vProduct) = 0);\n"
                    "    DimensionElementInsert('Product', '', vProduct, 'N');\n"
                    "ENDIF;"
                ),
                description="Metadata: only create the element",
                procedure="metadata",
                variables=["vProduct"],
            ),
            RuleExample(
                code=(
                    "IF(DIMIX('Product', vProduct) = 0);\n"
                    "    DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
                    "    AttrPutS(vName, 'Product', vProduct, 'Caption');\n"
                    "ENDIF;"
                ),
                description="Metadata: a direct insert is addressable at once",
                procedure="metadata",
                variables=["vProduct", "vName"],
            ),
            RuleExample(
                code=(
                    "IF(DIMIX('Product', vProduct) = 0);\n"
                    "    DimensionElementInsert('Product', '', vProduct, 'N');\n"
                    "    AttrPutS(vName, 'Product', vProduct, 'Caption');\n"
                    "ENDIF;"
                ),
                description="Metadata: the attribute cube cannot address the new element yet",
                valid=False,
                procedure="metadata",
                variables=["vProduct", "vName"],
            ),
            RuleExample(
                code=(
                    "IF(DIMIX('Product', 'Total') = 0 & DIMIX('Product', 'Other') = 0);\n"
                    "    DimensionElementInsert('Product', '', 'Total', 'C');\n"
                    "    DimensionElementInsertDirect('Product', '', 'Other', 'N');\n"
                    "    AttrPutS('Other', 'Product', 'Other', 'Caption');\n"
                    "ENDIF;"
                ),
                description="Prolog: a buffered insert ran first, so the direct one waits too",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C152"

    def interested_in(self):
        # Visited once per section with the whole tree: the analysis is a
        # path-sensitive walk over the section, not a per-statement check.
        return [Program]

    def visit(self, statement, context: LintContext):
        section = (context.block or "").lower()
        if section not in _PHASE_SECTIONS:
            return []
        self._context = context
        self._issues: list[LintIssue] = []
        start = _State()
        if section == "metadata":
            start = self._carried_from_prolog(statement)
        self._section = section
        self._reporting = True
        self._walk(statement.statements, start)
        return self._issues

    # -- across the phase ---------------------------------------------------

    def _carried_from_prolog(self, metadata: Program) -> _State:
        """The inserts the Prolog leaves pending at the start of Metadata.

        Pending inserts and the dimensions buffered inserts edited carry over:
        both hold for the whole phase, whatever earlier source records did.
        Absence does not, since an earlier record may have inserted the
        element. An entry naming a
        variable survives only if no Metadata statement may change it between
        records: not assigned there, not a data source variable, and no
        unparseable statement that might hide an assignment.
        """
        facts = self._context.process_facts
        prolog = facts.section_ast("prolog") if facts is not None else None
        if prolog is None:
            return _State()
        self._section = "prolog"
        self._reporting = False
        end = self._walk(prolog.statements, _State())
        if end.ended:
            return _State()  # no path reaches the Metadata
        statements = list(iter_statements(metadata.statements))
        if any(isinstance(stmt, UnknownStatement) for stmt in statements):
            unstable = None  # every variable
        else:
            unstable = self._assigned_names(metadata.statements)
            unstable |= {name.lower() for name in self._context.variables or []}

        def stable(atom: Atom) -> bool:
            kind, name = atom
            return kind != "var" or (unstable is not None and name not in unstable)

        # The dimensions a buffered insert edited carry over too: a Direct
        # insert into one of them stays unreachable for the rest of the phase.
        return _State(
            pending={
                key: at
                for key, at in end.pending.items()
                if all(stable(atom) for atom in key)
            },
            buffered_dims={dim for dim in end.buffered_dims if stable(dim)},
        )

    # -- walk ---------------------------------------------------------------

    def _walk(self, statements, state: _State) -> _State:
        for stmt in statements:
            if state.ended:
                break
            state = self._step(stmt, state)
        return state

    def _step(self, stmt, state: _State) -> _State:
        if isinstance(stmt, UnknownStatement):
            return _State()
        # Every call the statement carries counts, wherever it sits: a Direct
        # insert on an assignment's right-hand side or in a condition makes
        # the element addressable just the same. Conditions run before the body.
        expr = statement_expression(stmt)
        if expr is not None:
            for call in iter_function_calls(expr):
                self._call(call, state)
        if (
            isinstance(stmt, ExpressionStatement)
            and isinstance(stmt.expression, FunctionCall)
            and stmt.expression.name.lower() in _PATH_ENDS
        ):
            state.ended = True
            return state
        if isinstance(stmt, Assignment):
            if isinstance(stmt.left, Identifier):
                state.forget_variable(stmt.left.name.lower())
            return state
        if isinstance(stmt, IfStatement):
            then_state = state.copy()
            then_state.absent |= self._absent_if(stmt.condition, True)
            else_state = state.copy()
            else_state.absent |= self._absent_if(stmt.condition, False)
            then_state = self._walk(stmt.then_body, then_state)
            else_state = self._walk(stmt.else_body or [], else_state)
            return then_state.join(else_state)
        if isinstance(stmt, WhileStatement):
            # The body may run zero or many times. Whatever it could change is
            # forgotten up front, so the single walk below is valid for every
            # iteration, and only what survives the body is kept afterwards.
            entry = state.copy()
            if self._has_direct_insert(stmt.body):
                entry = _State()
            for name in self._assigned_names(stmt.body):
                entry.forget_variable(name)
            after = self._walk(stmt.body, entry.copy())
            return entry.join(after)
        return state

    def _call(self, call: FunctionCall, state: _State) -> None:
        name = call.name.lower()
        if name in _BUFFERED_INSERTS:
            key = self._key(call, _BUFFERED_INSERTS[name])
            if key is not None and key in state.absent:
                state.pending.setdefault(key, self._origin(call))
                state.buffered_dims.add(key[0])
        elif name in _DIRECT_INSERTS:
            key = self._key(call, _DIRECT_INSERTS[name])
            if key is None:
                return
            if key in state.absent and key[0] in state.buffered_dims:
                state.pending.setdefault(key, self._origin(call))
            else:
                state.forget(key)
        elif self._reporting:
            key, is_read = self._access_key(call, name)
            if key is not None and key in state.pending:
                self._report(call, key, state.pending[key], is_read)

    def _origin(self, call: FunctionCall) -> Origin:
        token = get_node_token(call)
        return self._section, token.line if token else 0

    def _report(
        self, call: FunctionCall, key: Key, origin: Origin, is_read: bool
    ) -> None:
        token = get_node_token(call)
        element = f"'{self._element_text(call, key)}'"
        section, line = origin
        # "line N" is shifted by the reporter to the current section's offset,
        # so a Prolog insert seen from Metadata is named without a line.
        where = f"line {line}" if section == self._section else "the Prolog"
        if is_read:
            effect = "the read returns no value. Read it in Data."
        else:
            what = "value" if call.name.lower() in _CELL_WRITES else "attribute"
            effect = (
                f"the write is lost. Write the {what} in Data, or insert the "
                "element with the Direct variant before any buffered insert "
                "into this dimension."
            )
        self._issues.append(
            LintIssue(
                message=(
                    f"{call.name} uses element {element}, inserted in {where}, "
                    "before cubes can address it (after the Metadata phase); "
                    f"{effect}"
                ),
                line=token.line if token else 0,
                column=token.column if token else 0,
                position=token.position if token else 0,
                rule_id=self.RULE_ID,
            )
        )

    @staticmethod
    def _element_text(call: FunctionCall, key: Key) -> str:
        """The element as the source writes it: the literal, or the variable."""
        kind, text = key[2]
        if kind == "var":
            for node in call.args:
                if isinstance(node, Identifier) and node.name.lower() == text:
                    return node.name
        for node in call.args:
            if isinstance(node, String) and _normalize(node.value) == text:
                return node.value
        return text

    # -- keys ---------------------------------------------------------------

    def _atom(self, expr) -> Atom | None:
        if isinstance(expr, String):
            return ("lit", _normalize(expr.value))
        if isinstance(expr, Identifier):
            token = get_node_token(expr)
            constants = self._context.constants
            if token is not None and constants is not None:
                exact = constants.possible_values_at(
                    expr.name, self._section, token.line
                ).exact
                if isinstance(exact, str):
                    return ("lit", _normalize(exact))
            return ("var", expr.name.lower())
        return None

    def _key(self, call: FunctionCall, indexes) -> Key | None:
        dim_i, hier_i, el_i = indexes
        needed = max(i for i in indexes if i is not None)
        if len(call.args) <= needed:
            return None
        dim = self._atom(call.args[dim_i])
        hier = self._atom(call.args[hier_i]) if hier_i is not None else dim
        element = self._atom(call.args[el_i])
        if dim is None or hier is None or element is None:
            return None
        if hier == ("lit", ""):
            hier = dim  # an empty hierarchy name means the default hierarchy
        return dim, hier, element

    def _access_key(self, call: FunctionCall, name: str) -> tuple[Key | None, bool]:
        """The element a cube access addresses, and whether it is a read."""
        if name in _ATTRIBUTE_WRITES:
            return self._key(call, _ATTRIBUTE_WRITES[name]), False
        if name in _ATTRIBUTE_READS:
            return self._key(call, _ATTRIBUTE_READS[name]), True
        if name in _CELL_WRITES:
            return self._cell_key(call, *_CELL_WRITES[name]), False
        if name in _CELL_READS:
            return self._cell_key(call, *_CELL_READS[name]), True
        return None, False

    def _cell_key(self, call: FunctionCall, cube_i: int, element_i: int) -> Key | None:
        if len(call.args) <= element_i:
            return None
        cube = self._atom(call.args[cube_i])
        if cube is None or cube[0] != "lit":
            return None
        if not cube[1].startswith(_ATTRIBUTE_CUBE_PREFIX):
            return None
        dim_name = cube[1][len(_ATTRIBUTE_CUBE_PREFIX) :]
        # `}ElementAttributes_Dim:Hier` addresses a named hierarchy.
        dim_name, _, hier_name = dim_name.partition(":")
        element = self._atom(call.args[element_i])
        if not dim_name or element is None:
            return None
        dim = ("lit", dim_name)
        hier = ("lit", hier_name) if hier_name else dim
        return dim, hier, element

    # -- conditions ---------------------------------------------------------

    def _absent_if(self, cond, holds: bool) -> set[Key]:
        """Elements proven absent when *cond* evaluates to *holds*."""
        if isinstance(cond, UnaryExpression) and cond.operator.type == TokenType.NOT:
            return self._absent_if(cond.operand, not holds)
        if not isinstance(cond, BinaryExpression):
            return set()
        op = cond.operator.type
        # A & B holding means both hold; A % B (TI's "or") failing means both fail.
        if (op == TokenType.AND and holds) or (op == TokenType.OR and not holds):
            return self._absent_if(cond.left, holds) | self._absent_if(
                cond.right, holds
            )
        probe, zero_on_left = self._probe_against_zero(cond)
        if probe is None:
            return set()
        if zero_on_left:
            # Mirror the comparison: 0 < x reads as x > 0, 0 > x as x < 0.
            op = {
                TokenType.LESS: TokenType.GREATER,
                TokenType.GREATER: TokenType.LESS,
            }.get(op, op)
        # The index is never negative: "= 0" means absent, "<> 0" and "> 0"
        # mean present. Anything else proves nothing.
        means_absent = {
            TokenType.EQUALS: True,
            TokenType.NOT_EQUAL: False,
            TokenType.GREATER: False,
        }.get(op)
        if means_absent is None or means_absent != holds:
            return set()
        return {probe}

    def _probe_against_zero(self, cond: BinaryExpression):
        """``(key, zero_on_left)`` for ``probe <op> 0`` / ``0 <op> probe``."""
        for probe_side, zero_side, zero_on_left in (
            (cond.left, cond.right, False),
            (cond.right, cond.left, True),
        ):
            if not (isinstance(zero_side, Number) and _is_zero(zero_side.value)):
                continue
            if not isinstance(probe_side, FunctionCall):
                continue
            indexes = _INDEX_PROBES.get(probe_side.name.lower())
            if indexes is None:
                continue
            key = self._key(probe_side, indexes)
            if key is not None:
                return key, zero_on_left
        return None, False

    # -- loop helpers -------------------------------------------------------

    @staticmethod
    def _assigned_names(statements) -> set[str]:
        return {
            stmt.left.name.lower()
            for stmt in iter_statements(statements)
            if isinstance(stmt, Assignment) and isinstance(stmt.left, Identifier)
        }

    @staticmethod
    def _has_direct_insert(statements) -> bool:
        for stmt in iter_statements(statements):
            if isinstance(stmt, UnknownStatement):
                return True
            expr = statement_expression(stmt)
            if expr is None:
                continue
            if any(
                call.name.lower() in _DIRECT_INSERTS
                for call in iter_function_calls(expr)
            ):
                return True
        return False


def _is_zero(value) -> bool:
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False
