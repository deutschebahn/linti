"""Process-wide constant propagation for cross-block variable tracking.

The lint pipeline runs each TI section (Prolog, Metadata, Data, Epilog)
in isolation, so an individual rule cannot see what value a variable was
given in an earlier section.  ``ConstantPropagationIndex`` closes that gap:
it walks the *whole* process once, in TI execution order, and records the
value each variable holds at every point.  Rules read from it through the
single entry point ``LintContext.possible_values(name, line)`` — no rule has
to manage or persist cross-section state itself.

The returned :class:`PossibleValues` is a cascade: a rule takes exactly the
strength it needs.  :attr:`~PossibleValues.exact` yields the one fully known
scalar (and only then); :meth:`~PossibleValues.all_of` /
:meth:`~PossibleValues.any_of` / :attr:`~PossibleValues.values` reason over
*all* possibilities — a single known value is simply the one-element case;
:meth:`~PossibleValues.all_contain` / :meth:`~PossibleValues.any_contains`
answer substring questions and also accept a partially known variant as
evidence when a known fragment proves it; :attr:`~PossibleValues.partial`
exposes a partially known string; and :attr:`~PossibleValues.assigned` tells
whether the variable was written at all, even when its value is dynamic.

Tracking semantics
------------------
* Literal assignments (``sDim = 'plan';``, ``nMax = 12;``) are tracked.
* Expressions over known values are folded: ``+ - * /`` on numbers and
  ``|`` (concatenation) on strings.  ``sFull = sDim | ':' | sHier;`` yields
  a known value when both variables are known.
* A concatenation that mixes known and dynamic parts —
  ``sName = 'prefix_' | pDyn;`` — keeps its literal fragments as a
  :class:`PartialString` rather than collapsing to UNKNOWN.  Rules read it
  through :attr:`PossibleValues.partial`; :attr:`PossibleValues.exact` still
  reports only *fully* known values.
* Anything dynamic — function calls, parameters, datasource variables,
  predefined variables — is UNKNOWN.  The index never guesses.
* ``IF``/``ELSEIF``/``ELSE`` branches are joined: after the construct the
  variable holds the *set* of values its branches assign (plus its pre-IF
  value when a branch does not assign it).  Rules ask whether every variant
  satisfies a condition, or whether at least one does, via
  :meth:`PossibleValues.all_of` / :meth:`PossibleValues.any_of` (∀ / ∃
  respectively).  A branch with a dynamic value makes the set incomplete: "at
  least one variant matches" can still be shown, but "every variant matches"
  no longer can.  At most ``max_variants`` distinct values are kept; beyond
  that the variable degrades to UNKNOWN.  :attr:`PossibleValues.exact` still
  reports a value only when it is a single fully known scalar.
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

from dataclasses import dataclass
from typing import Optional, Union

from linti.lexer.token import TokenType
from linti.linter.parse_cache import SectionParseCache
from linti.model.process_ir import ProcessIR
from linti.parser.ast import (
    Assignment,
    ASTNode,
    BinaryExpression,
    Expression,
    Identifier,
    IfStatement,
    Number,
    String,
    UnaryExpression,
    UnknownStatement,
    WhileStatement,
    get_node_token,
)


class _Unknown:
    """Sentinel for a variable whose value cannot be determined statically."""

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class PartialString:
    """A string whose value is only partially known statically.

    A concatenation such as ``'prefix_' | pDyn | '_suffix'`` cannot be folded
    to a single string, but its literal fragments are still worth keeping.
    ``PartialString`` records them as a *normalized* sequence of segments:
    each segment is either a known ``str`` chunk or the :data:`UNKNOWN`
    sentinel (a gap).  Normalization guarantees no two adjacent chunks and no
    two adjacent gaps, and that a partial always contains at least one gap
    (a fully known concatenation folds back to a plain ``str`` instead).
    """

    segments: tuple[Union[str, _Unknown], ...]

    @property
    def known_fragments(self) -> tuple[str, ...]:
        """All known chunks, in order (the unknown gaps omitted)."""
        return tuple(seg for seg in self.segments if isinstance(seg, str))


def _normalize_segments(
    segments: list[Union[str, _Unknown]],
) -> Union[str, PartialString, _Unknown]:
    """Smart constructor for a ``|`` concatenation's result.

    *segments* is the two operands' segments concatenated back to back, so
    the boundary between them can leave two known chunks or two gaps sitting
    next to each other; this merges each such pair into one.  It then decides
    what the merged segments represent: a plain ``str`` when fully known, a
    :class:`PartialString` when a mix, or :data:`UNKNOWN` when nothing
    survived.
    """
    merged: list[Union[str, _Unknown]] = []
    for seg in segments:
        if isinstance(seg, str):
            if seg == "":
                continue
            if merged and isinstance(merged[-1], str):
                merged[-1] = merged[-1] + seg
                continue
        elif merged and merged[-1] is UNKNOWN:
            continue
        merged.append(seg)

    if not merged:
        return ""
    if all(isinstance(seg, str) for seg in merged):
        return "".join(seg for seg in merged if isinstance(seg, str))
    if not any(isinstance(seg, str) for seg in merged):
        return UNKNOWN
    return PartialString(tuple(merged))


def _as_segments(value: "Value") -> list[Union[str, _Unknown]]:
    """Promote a tracked value to a segment list for concatenation."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, PartialString):
        return list(value.segments)
    # Numbers and the UNKNOWN sentinel contribute an opaque gap.
    return [UNKNOWN]


#: A single (possibly partial) value: string, number, or partial string.
AtomicValue = Union[str, float, PartialString]


def _definitely_contains(value: AtomicValue, substring: str) -> bool:
    """True when *value* certainly contains *substring*, whatever its gaps hold.

    Three-valued at heart: an exact string answers definitely; a
    :class:`PartialString` is definite only when a *known fragment* contains the
    substring (fragments appear verbatim in the final value) — otherwise the
    substring might still hide in a gap or span a fragment boundary, which is
    "maybe" and never counts as evidence.  Numbers contain no text.
    """
    if isinstance(value, str):
        return substring in value
    if isinstance(value, PartialString):
        return any(substring in fragment for fragment in value.known_fragments)
    return False


#: A tracked value: an atomic value or the UNKNOWN sentinel.
Value = Union[AtomicValue, _Unknown]

#: Default cap on how many distinct values are tracked per variable before the
#: index degrades to "unknown" (see :class:`PossibleValues`).
DEFAULT_MAX_VARIANTS = 8


@dataclass(frozen=True)
class PossibleValues:
    """The set of values a variable may hold at a program point.

    This is the single answer type of the constant propagation API.  It is a
    *cascade*: a rule reads exactly the strength it needs, and each stronger
    accessor is a refinement of the level below it.

    1. **Exactly one value** — :attr:`exact` yields the sole fully known
       scalar, or ``None`` in every weaker situation.
    2. **All possible values** — :meth:`all_of` / :meth:`any_of` /
       :attr:`values` reason over every possibility.  A single known value is
       just the one-element case, so level 1 is contained in level 2.
       Arbitrary predicates are decidable only on *fully known* values, so a
       partially known variant never satisfies them; for substring questions
       — the one family that *is* decidable on partials — use
       :meth:`all_contain` / :meth:`any_contains` instead.
    3. **Partially known** — :attr:`partial` exposes the known fragments of a
       single half-dynamic string.
    4. **Written at all** — :attr:`assigned` distinguishes "never assigned"
       from "assigned but dynamic".

    Every query answers "is this *provable*?": an unknown — a gap in a partial,
    an incomplete set, a dynamic value — never counts as evidence, so
    ``False`` always means "not provable", not "provably false".

    ``values`` are the concrete (possibly partial) possibilities; ``complete``
    says whether they enumerate *every* possibility.  When ``complete`` is
    ``False`` the variable may additionally hold some fully dynamic value that
    could not be represented — so ``values`` can still show that a value is
    *possible* (∃), but not that something holds for *every* case (∀).
    """

    values: frozenset  # of AtomicValue; never contains the UNKNOWN sentinel
    #: Whether ``values`` enumerates every possibility, or the variable may
    #: additionally hold some dynamic value not represented in the set.
    complete: bool
    #: False only for a variable that was never written at all.
    assigned: bool = True

    @property
    def is_unknown(self) -> bool:
        """True when nothing at all is known about the value."""
        return not self.values and not self.complete

    def _sole(self) -> Optional[AtomicValue]:
        """The one value in ``values``, when it is complete and holds exactly one."""
        if self.complete and len(self.values) == 1:
            (only,) = self.values
            return only
        return None

    @property
    def exact(self) -> Optional[Union[str, float]]:
        """The single, fully known ``str``/``float`` value, or ``None``.

        Non-``None`` only when the variable holds exactly one statically known
        scalar — never for multi-variant, partial, or dynamic values.
        """
        only = self._sole()
        return only if isinstance(only, (str, float)) else None

    @property
    def partial(self) -> Optional[PartialString]:
        """The sole value when it is a :class:`PartialString`, else ``None``.

        Fully known values (use :attr:`exact`), fully unknown values, and
        multi-variant values all return ``None``.
        """
        only = self._sole()
        return only if isinstance(only, PartialString) else None

    def _all(self, holds_for) -> bool:
        """True iff *holds_for* is provable for every possible value (∀).

        The set must be complete and non-empty: a dynamic possibility
        (``complete is False``) could violate *holds_for*, which alone rules
        out a universal guarantee.
        """
        return (
            self.complete
            and bool(self.values)
            and all(holds_for(value) for value in self.values)
        )

    def _any(self, holds_for) -> bool:
        """True iff *holds_for* is provable for at least one possible value (∃)."""
        return any(holds_for(value) for value in self.values)

    def all_of(self, predicate) -> bool:
        """Check whether *predicate* provably holds for every possible value (∀).

        *predicate* receives only fully known ``str``/``float`` values; a
        partially known variant can't decide an arbitrary predicate, so its
        presence alone rules out a universal guarantee.
        """
        return self._all(lambda v: isinstance(v, (str, float)) and predicate(v))

    def any_of(self, predicate) -> bool:
        """Check whether *predicate* provably holds for at least one value (∃).

        *predicate* receives only fully known ``str``/``float`` values; a
        partially known variant is never proof that the predicate holds, so it
        is skipped rather than counted.
        """
        return self._any(lambda v: isinstance(v, (str, float)) and predicate(v))

    def all_contain(self, substring: str) -> bool:
        """Check whether *substring* is certainly present in every value (∀).

        The substring-aware counterpart of :meth:`all_of`: a partially known
        variant counts when one of its *known fragments* contains *substring*,
        because that fragment appears verbatim in the final value.
        """
        return self._all(lambda v: _definitely_contains(v, substring))

    def any_contains(self, substring: str) -> bool:
        """Check whether *substring* is certainly present in at least one value (∃).

        A partially known variant counts when one of its known fragments
        contains *substring*; a gap that merely *might* contain it does not
        count as proof.
        """
        return self._any(lambda v: _definitely_contains(v, substring))


#: The fully unknown value of a *written* variable: could be anything.
TOP = PossibleValues(frozenset(), False)

#: The value of a variable that was never assigned: unknown and unwritten.
UNASSIGNED = PossibleValues(frozenset(), False, assigned=False)


def _single(value: AtomicValue) -> PossibleValues:
    """A PossibleValues holding exactly one known value."""
    return PossibleValues(frozenset({value}), True)


#: TI execution order of the four sections.
SECTION_ORDER = ("prolog", "metadata", "data", "epilog")

#: Sections that execute once per datasource record.
_REPEATING_SECTIONS = frozenset({"metadata", "data"})

#: A value event: the variable holds *value* from (section, line) onward.
_Event = tuple[int, int, PossibleValues]


class ConstantPropagationIndex:
    """Tracks variable values across all sections of one process.

    The index is independent of the per-rule reset cycle: it is created once
    per process model and shared by every ``LintContext``.  It builds lazily
    on the first :meth:`possible_values_at` call.
    """

    def __init__(
        self,
        process: ProcessIR,
        cache: Optional[SectionParseCache] = None,
        max_variants: int = DEFAULT_MAX_VARIANTS,
    ) -> None:
        self._process = process
        # Shared per-run lex/parse cache; own it when none is supplied (e.g.
        # in tests) so the index still parses each section only once.
        self._cache = cache if cache is not None else SectionParseCache(process)
        self._max_variants = max_variants
        # name (lower-cased) -> events sorted by (section index, line)
        self._events: Optional[dict[str, list[_Event]]] = None

    def possible_values_at(self, name: str, block: str, line: int) -> PossibleValues:
        """Return the set of values *name* may hold at *line* of *block*.

        Args:
            name: Variable name (case-insensitive).
            block: Section name: ``prolog``, ``metadata``, ``data`` or
                ``epilog``.
            line: 1-based line number relative to the section's code — the
                same coordinates rule tokens and AST nodes carry.

        Returns:
            The :class:`PossibleValues` cascade — :attr:`PossibleValues.exact`
            for the single fully known value, :meth:`PossibleValues.all_of` /
            :meth:`PossibleValues.any_of` across branch variants,
            :attr:`PossibleValues.partial` for a half-known string.  A variable
            that is dynamic at that point yields :data:`TOP`; one that was
            never written yields :data:`UNASSIGNED`.
        """
        if self._events is None:
            self._build()

        try:
            section_idx = SECTION_ORDER.index(block.lower())
        except ValueError:
            return UNASSIGNED

        events = self._events.get(name.lower())
        if not events:
            return UNASSIGNED

        for event_section, event_line, value in reversed(events):
            if (event_section, event_line) <= (section_idx, line):
                return value
        return UNASSIGNED

    # -- build ------------------------------------------------------------

    def _build(self) -> None:
        self._events = {}
        # name (lower-cased) -> PossibleValues at the current build position.
        # Persists across sections so a Prolog value stays visible in Data.
        env: dict[str, PossibleValues] = {}

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
                    self._record(env, name, section_idx, 0, TOP)

            self._interpret(ast.statements, section_idx, env)

    def _interpret(
        self, statements: list, section_idx: int, env: dict[str, PossibleValues]
    ) -> None:
        """Abstract-interpret straight-line statements, updating *env*."""
        for stmt in statements:
            if isinstance(stmt, Assignment):
                line = stmt.token.line if stmt.token else 0
                self._record(
                    env,
                    stmt.left.name,
                    section_idx,
                    line,
                    self._evaluate(stmt.right, env),
                )
            elif isinstance(stmt, IfStatement):
                self._interpret_if(stmt, section_idx, env)
            elif isinstance(stmt, WhileStatement):
                self._invalidate_loop(stmt, section_idx, env)
            elif isinstance(stmt, UnknownStatement):
                for name, line in _unknown_statement_assignments(stmt):
                    self._record(env, name, section_idx, line, TOP)

    def _interpret_if(
        self, stmt: IfStatement, section_idx: int, env: dict[str, PossibleValues]
    ) -> None:
        """Interpret both branches, then join them into the outer *env*.

        Each branch runs on its own copy (an empty ``else_body`` means the
        else path keeps the pre-IF values — fall-through).  ELSEIF is a nested
        ``IfStatement`` in ``else_body`` and is handled by the recursion.  The
        joined result is recorded at the construct's end line so it becomes
        visible only after the whole ``IF``.
        """
        then_env = dict(env)
        else_env = dict(env)
        self._interpret(stmt.then_body, section_idx, then_env)
        self._interpret(stmt.else_body, section_idx, else_env)

        end_line = _max_line(stmt)
        assigned = _assigned_names(stmt.then_body) | _assigned_names(stmt.else_body)
        for key in sorted(assigned):
            joined = self._join(then_env.get(key, TOP), else_env.get(key, TOP))
            self._record(env, key, section_idx, end_line, joined)

    def _invalidate_loop(
        self, stmt: WhileStatement, section_idx: int, env: dict[str, PossibleValues]
    ) -> None:
        """Mark every variable assigned in a loop body UNKNOWN from the header.

        The body may run zero or many times and earlier lines re-execute on a
        later iteration, so no in-loop value can be trusted from the loop on.
        """
        loop_line = stmt.token.line if stmt.token else 0
        for name in sorted(_assigned_names(stmt.body)):
            self._record(env, name, section_idx, loop_line, TOP)

    def _record(
        self,
        env: dict[str, PossibleValues],
        name: str,
        section_idx: int,
        line: int,
        value: PossibleValues,
    ) -> None:
        key = name.lower()
        self._events.setdefault(key, []).append((section_idx, line, value))
        env[key] = value

    def _join(self, a: PossibleValues, b: PossibleValues) -> PossibleValues:
        """Merge two branch outcomes into their set of possibilities."""
        values = a.values | b.values
        if len(values) > self._max_variants:
            return TOP
        return PossibleValues(values, a.complete and b.complete)

    # -- expression evaluation --------------------------------------------

    def _evaluate(
        self, expr: Expression, env: dict[str, PossibleValues]
    ) -> PossibleValues:
        """Evaluate *expr* to the set of values it may produce."""
        if isinstance(expr, Number):
            try:
                return _single(float(expr.value))
            except (TypeError, ValueError):
                return TOP
        if isinstance(expr, String):
            return _single(expr.value)
        if isinstance(expr, Identifier):
            return env.get(expr.name.lower(), TOP)
        if isinstance(expr, UnaryExpression):
            return self._evaluate_unary(expr, env)
        if isinstance(expr, BinaryExpression):
            return self._evaluate_binary(expr, env)
        # FunctionCall and anything unexpected: dynamic.
        return TOP

    def _evaluate_unary(
        self, expr: UnaryExpression, env: dict[str, PossibleValues]
    ) -> PossibleValues:
        operand = self._evaluate(expr.operand, env)
        results: set = set()
        saw_unknown = False
        for atom in _atoms(operand):
            value = _apply_unary(expr.operator.type, atom)
            if value is UNKNOWN:
                saw_unknown = True
            else:
                results.add(value)
        return self._collect(results, saw_unknown)

    def _evaluate_binary(
        self, expr: BinaryExpression, env: dict[str, PossibleValues]
    ) -> PossibleValues:
        left = self._evaluate(expr.left, env)
        right = self._evaluate(expr.right, env)
        op = expr.operator.type

        results: set = set()
        saw_unknown = False
        for a in _atoms(left):
            for b in _atoms(right):
                value = _apply_binary(op, a, b)
                if value is UNKNOWN:
                    saw_unknown = True
                else:
                    results.add(value)
        return self._collect(results, saw_unknown)

    def _collect(self, results: set, saw_unknown: bool) -> PossibleValues:
        """Build a PossibleValues from folded results, honouring the cap.

        *saw_unknown* records that some operand combination was fully dynamic
        (and thus could not be represented); the result is then incomplete.
        Too many distinct results degrade to the fully unknown value.
        """
        if not results:
            return TOP
        if len(results) > self._max_variants:
            return TOP
        return PossibleValues(frozenset(results), not saw_unknown)


def _atoms(pv: PossibleValues) -> list:
    """The concrete atoms of *pv*, plus an UNKNOWN gap when incomplete.

    The extra UNKNOWN stands in for the "some dynamic value" possibility an
    incomplete set carries, so folding preserves it (e.g. a known suffix
    survives ``anything | '_x'``).
    """
    atoms = list(pv.values)
    if not pv.complete:
        atoms.append(UNKNOWN)
    return atoms


def _apply_unary(op_type: TokenType, atom: Value) -> Value:
    """Apply a unary operator to one atom, or UNKNOWN when not foldable."""
    if isinstance(atom, float):
        if op_type is TokenType.MINUS:
            return -atom
        if op_type is TokenType.PLUS:
            return atom
    return UNKNOWN


def _apply_binary(op_type: TokenType, a: Value, b: Value) -> Value:
    """Apply a binary operator to two atoms, or UNKNOWN when not foldable."""
    if op_type is TokenType.PIPE:
        # Concatenation keeps known fragments even when a side is dynamic;
        # a fully known concatenation folds back to a plain string.
        return _normalize_segments(_as_segments(a) + _as_segments(b))
    if isinstance(a, float) and isinstance(b, float):
        if op_type is TokenType.PLUS:
            return a + b
        if op_type is TokenType.MINUS:
            return a - b
        if op_type is TokenType.STAR:
            return a * b
        if op_type is TokenType.SLASH:
            return UNKNOWN if b == 0 else a / b
    return UNKNOWN


def _max_line(node: ASTNode) -> int:
    """The greatest source line touched by *node* and its descendants.

    The AST does not record the ``ENDIF`` line, so this approximates "after the
    IF" for placing a joined branch event.
    """
    lines: list[int] = []
    tok = get_node_token(node)
    if tok is not None:
        lines.append(tok.line)
    operator = getattr(node, "operator", None)
    if operator is not None and hasattr(operator, "line"):
        lines.append(operator.line)
    for tok in getattr(node, "tokens", None) or []:
        lines.append(tok.line)
    for attr in ("condition", "left", "right", "operand"):
        child = getattr(node, attr, None)
        if isinstance(child, ASTNode):
            lines.append(_max_line(child))
    for attr in ("then_body", "else_body", "body", "args"):
        for child in getattr(node, attr, None) or []:
            if isinstance(child, ASTNode):
                lines.append(_max_line(child))
    return max(lines, default=0)


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
