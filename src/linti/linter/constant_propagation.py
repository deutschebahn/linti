"""Process-wide constant propagation for cross-block variable tracking.

The lint pipeline runs each TI section (Prolog, Metadata, Data, Epilog)
in isolation, so an individual rule cannot see what value a variable was
given in an earlier section.  ``ConstantPropagationIndex`` closes that gap:
it walks the *whole* process once, in TI execution order, and records the
value each variable holds at every point.  Rules read from it through
``LintContext.constant_value(name, line)`` — no rule has to manage or
persist cross-section state itself.

Tracking semantics
------------------
* Literal assignments (``sDim = 'plan';``, ``nMax = 12;``) are tracked.
* Expressions over known values are folded: ``+ - * /`` on numbers and
  ``|`` (concatenation) on strings.  ``sFull = sDim | ':' | sHier;`` yields
  a known value when both variables are known.
* Anything dynamic — function calls, parameters, datasource variables,
  predefined variables — is UNKNOWN.  The index never guesses.
* An assignment inside an ``IF`` branch marks the variable UNKNOWN from
  that line on (the branch may not execute).
* An assignment inside a ``WHILE`` body marks the variable UNKNOWN from
  the ``WHILE`` line on (the loop body may run zero or many times).
* Metadata and Data execute once *per datasource record*.  A variable that
  is read there before it is written would carry a leftover value from the
  previous record, so every variable assigned anywhere in those sections
  starts the section as UNKNOWN; a top-level assignment then makes it known
  again from its line on (each record runs the same straight-line code).

Cost / laziness
---------------
Building the index reads each section's AST from the shared per-run
``SectionParseCache`` — which the lint loop populates anyway — and walks it
linearly.  Sections already linted are cache hits; any not yet reached are
parsed once here and reused when the lint loop gets to them, so no section
is ever lexed or parsed twice.  Because the walk still is not free and most
rules never ask for values, the index builds *lazily* on the first query
and is then cached for the lifetime of the process model.  Rules that do
not use it cost nothing.
"""

from typing import Optional, Union

from linti.lexer.token import TokenType
from linti.linter.parse_cache import SectionParseCache
from linti.model.process_ir import ProcessIR
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    Expression,
    Identifier,
    IfStatement,
    Number,
    String,
    UnaryExpression,
    UnknownStatement,
    WhileStatement,
)


class _Unknown:
    """Sentinel for a variable whose value cannot be determined statically."""

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()

#: A tracked value: a string, a number, or the UNKNOWN sentinel.
Value = Union[str, float, _Unknown]

#: TI execution order of the four sections.
SECTION_ORDER = ("prolog", "metadata", "data", "epilog")

#: Sections that execute once per datasource record.
_REPEATING_SECTIONS = frozenset({"metadata", "data"})

#: A value event: the variable holds *value* from (section, line) onward.
_Event = tuple[int, int, Value]


class ConstantPropagationIndex:
    """Tracks variable values across all sections of one process.

    The index is independent of the per-rule reset cycle: it is created once
    per process model and shared by every ``LintContext``.  It builds lazily
    on the first :meth:`value_at` call.
    """

    def __init__(
        self,
        process: ProcessIR,
        cache: Optional[SectionParseCache] = None,
    ) -> None:
        self._process = process
        # Shared per-run lex/parse cache; own it when none is supplied (e.g.
        # in tests) so the index still parses each section only once.
        self._cache = cache if cache is not None else SectionParseCache(process)
        # name (lower-cased) -> events sorted by (section index, line)
        self._events: Optional[dict[str, list[_Event]]] = None
        # name (lower-cased) -> value at the current build position
        self._current: dict[str, Value] = {}

    def value_at(self, name: str, block: str, line: int) -> Optional[Value]:
        """Return the constant value *name* holds at *line* of *block*.

        Args:
            name: Variable name (case-insensitive).
            block: Section name: ``prolog``, ``metadata``, ``data`` or
                ``epilog``.
            line: 1-based line number relative to the section's code — the
                same coordinates rule tokens and AST nodes carry.

        Returns:
            The value (``str`` or ``float``) if it is statically known at
            that point, or ``None`` when it is unknown or never assigned.
        """
        if self._events is None:
            self._build()

        try:
            section_idx = SECTION_ORDER.index(block.lower())
        except ValueError:
            return None

        events = self._events.get(name.lower())
        if not events:
            return None

        for event_section, event_line, value in reversed(events):
            if (event_section, event_line) <= (section_idx, line):
                return None if value is UNKNOWN else value
        return None

    # -- build ------------------------------------------------------------

    def _build(self) -> None:
        self._events = {}
        self._current = {}

        for section_idx, section in enumerate(SECTION_ORDER):
            proc_info = getattr(self._process, section)
            if proc_info is None:
                continue

            ast = self._cache.get(section).ast
            if ast is None:
                # Section failed to parse (nesting too deep); skip it.
                continue

            if section in _REPEATING_SECTIONS:
                # Reads before the first write would see the previous
                # record's value — invalidate every name assigned here.
                for name in sorted(_assigned_names(ast.statements)):
                    self._record(name, section_idx, 0, UNKNOWN)

            self._walk_top_level(ast.statements, section_idx)

    def _walk_top_level(self, statements: list, section_idx: int) -> None:
        """Walk unconditional statements, folding values as we go."""
        for stmt in statements:
            if isinstance(stmt, Assignment):
                line = stmt.token.line if stmt.token else 0
                self._record(
                    stmt.left.name, section_idx, line, self._evaluate(stmt.right)
                )
            elif isinstance(stmt, IfStatement):
                self._mark_conditional(stmt.then_body, section_idx, None)
                self._mark_conditional(stmt.else_body, section_idx, None)
            elif isinstance(stmt, WhileStatement):
                loop_line = stmt.token.line if stmt.token else None
                self._mark_conditional(stmt.body, section_idx, loop_line)
            elif isinstance(stmt, UnknownStatement):
                for name, line in _unknown_statement_assignments(stmt):
                    self._record(name, section_idx, line, UNKNOWN)

    def _mark_conditional(
        self, statements: list, section_idx: int, loop_line: Optional[int]
    ) -> None:
        """Mark conditionally-executed assignments as UNKNOWN.

        Inside a loop (*loop_line* set) the invalidation starts at the loop
        header, because a later iteration re-executes earlier lines.
        """
        for stmt in statements:
            if isinstance(stmt, Assignment):
                line = loop_line
                if line is None:
                    line = stmt.token.line if stmt.token else 0
                self._record(stmt.left.name, section_idx, line, UNKNOWN)
            elif isinstance(stmt, IfStatement):
                self._mark_conditional(stmt.then_body, section_idx, loop_line)
                self._mark_conditional(stmt.else_body, section_idx, loop_line)
            elif isinstance(stmt, WhileStatement):
                inner_line = loop_line
                if inner_line is None and stmt.token:
                    inner_line = stmt.token.line
                self._mark_conditional(stmt.body, section_idx, inner_line)
            elif isinstance(stmt, UnknownStatement):
                for name, line in _unknown_statement_assignments(stmt):
                    self._record(name, section_idx, loop_line or line, UNKNOWN)

    def _record(self, name: str, section_idx: int, line: int, value: Value) -> None:
        key = name.lower()
        self._events.setdefault(key, []).append((section_idx, line, value))
        self._current[key] = value

    # -- expression folding ------------------------------------------------

    def _evaluate(self, expr: Expression) -> Value:
        """Fold *expr* to a constant, or UNKNOWN when anything is dynamic."""
        if isinstance(expr, Number):
            try:
                return float(expr.value)
            except (TypeError, ValueError):
                return UNKNOWN
        if isinstance(expr, String):
            return expr.value
        if isinstance(expr, Identifier):
            return self._current.get(expr.name.lower(), UNKNOWN)
        if isinstance(expr, UnaryExpression):
            return self._evaluate_unary(expr)
        if isinstance(expr, BinaryExpression):
            return self._evaluate_binary(expr)
        # FunctionCall and anything unexpected: dynamic.
        return UNKNOWN

    def _evaluate_unary(self, expr: UnaryExpression) -> Value:
        operand = self._evaluate(expr.operand)
        if isinstance(operand, float):
            if expr.operator.type is TokenType.MINUS:
                return -operand
            if expr.operator.type is TokenType.PLUS:
                return operand
        return UNKNOWN

    def _evaluate_binary(self, expr: BinaryExpression) -> Value:
        left = self._evaluate(expr.left)
        right = self._evaluate(expr.right)
        if left is UNKNOWN or right is UNKNOWN:
            return UNKNOWN

        op = expr.operator.type
        if isinstance(left, str) and isinstance(right, str):
            if op is TokenType.PIPE:
                return left + right
            return UNKNOWN

        if isinstance(left, float) and isinstance(right, float):
            if op is TokenType.PLUS:
                return left + right
            if op is TokenType.MINUS:
                return left - right
            if op is TokenType.STAR:
                return left * right
            if op is TokenType.SLASH:
                return UNKNOWN if right == 0 else left / right

        return UNKNOWN


def _assigned_names(statements: list) -> set[str]:
    """All variable names (lower-cased) assigned anywhere in *statements*."""
    names: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, Assignment):
            names.add(stmt.left.name.lower())
        elif isinstance(stmt, IfStatement):
            names |= _assigned_names(stmt.then_body)
            names |= _assigned_names(stmt.else_body)
        elif isinstance(stmt, WhileStatement):
            names |= _assigned_names(stmt.body)
        elif isinstance(stmt, UnknownStatement):
            names |= {name for name, _ in _unknown_statement_assignments(stmt)}
    return names


def _unknown_statement_assignments(stmt: UnknownStatement) -> list[tuple[str, int]]:
    """Best-effort scan of an unparseable statement for ``<identifier> =``.

    The statement's effect cannot be modelled, so any variable it appears to
    assign must be invalidated rather than silently kept at a stale value.
    """
    assignments: list[tuple[str, int]] = []
    meaningful = [
        tok
        for tok in stmt.tokens
        if tok.type not in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT)
    ]
    for tok, nxt in zip(meaningful, meaningful[1:]):
        if (
            tok.type in (TokenType.IDENTIFIER, TokenType.PREDEFINED_IDENTIFIER)
            and nxt.type is TokenType.EQUALS
        ):
            assignments.append((tok.value, tok.line))
    return assignments
