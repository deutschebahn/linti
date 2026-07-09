"""Process-wide constant evaluation for cross-block variable tracking.

The lint pipeline runs each TI section (Prolog, Metadata, Data, Epilog)
in isolation, so an individual rule cannot see what value a variable was
given in an earlier section.  ``ConstantEvaluationIndex`` closes that gap:
it walks the *whole* process once, in TI execution order, and records the
value each variable holds at every point.  Rules read from it through the
single entry point ``LintContext.possible_values(name, line)`` — no rule has
to manage or persist cross-section state itself.

The returned value is a :class:`~linti.linter.possible_values.PossibleValues`
— see that module for the full cascade rules read through (:attr:`exact`,
:meth:`all_of`/:meth:`any_of`, :attr:`partial`, :attr:`assigned`).  This
module is the *interpreter*: it walks the TI AST and decides, section by
section, what value each variable provably holds.

Tracking semantics
------------------
* Literal assignments (``sDim = 'plan';``, ``nMax = 12;``) are tracked.
* Expressions over known values are folded: ``+ - * /`` on numbers and
  ``|`` (concatenation) on strings.  ``sFull = sDim | ':' | sHier;`` yields
  a known value when both variables are known.  A concatenation that mixes
  known and dynamic parts — ``sName = 'prefix_' | pDyn;`` — keeps its
  literal fragments as a
  :class:`~linti.linter.possible_values.PartialString` rather than
  collapsing to fully unknown (see
  :func:`~linti.linter.possible_values.normalize_string_segments`).
* Anything dynamic — function calls, parameters, datasource variables,
  predefined variables — is UNKNOWN.  The index never guesses.
* ``IF``/``ELSEIF``/``ELSE`` branches are joined: after the construct the
  variable holds the *set* of values its branches assign (plus its pre-IF
  value when a branch does not assign it).  A branch with a dynamic value
  makes the set incomplete: "at least one variant matches" can still be
  shown, but "every variant matches" no longer can.  At most ``max_values_per_variable``
  distinct values are kept; beyond that the variable degrades to UNKNOWN.
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

from typing import Optional

from linti.lexer.token import TokenType
from linti.linter.parse_cache import SectionParseCache
from linti.semantic.possible_values import (
    TOP,
    UNASSIGNED,
    UNKNOWN,
    PossibleValues,
    Value,
    as_segments,
    normalize_string_segments,
    single,
)
from linti.model.process_ir import ProcessIR
from linti.parser.ast import (
    Assignment,
    ASTNode,
    BinaryExpression,
    Expression,
    FunctionCall,
    Identifier,
    IfStatement,
    Number,
    String,
    UnaryExpression,
    UnknownStatement,
    WhileStatement,
    get_node_token,
)

#: Default cap on how many distinct values are tracked per variable before the
#: index degrades to "unknown" (see :class:`~linti.linter.possible_values.PossibleValues`).
DEFAULT_MAX_VALUES_PER_VARIABLE = 8

#: TI execution order of the four sections.
SECTION_ORDER = ("prolog", "metadata", "data", "epilog")

#: Sections that execute once per datasource record.
_REPEATING_SECTIONS = frozenset({"metadata", "data"})

#: A value event: the variable holds *value* from (section, line) onward.
_Event = tuple[int, int, PossibleValues]


class ConstantEvaluationIndex:
    """Tracks variable values across all sections of one process.

    The index is independent of the per-rule reset cycle: it is created once
    per process model and shared by every ``LintContext``.  It builds lazily
    on the first :meth:`possible_values_at` call.
    """

    def __init__(
        self,
        process: ProcessIR,
        cache: Optional[SectionParseCache] = None,
        max_values_per_variable: int = DEFAULT_MAX_VALUES_PER_VARIABLE,
    ) -> None:
        self._process = process
        # Shared per-run lex/parse cache; own it when none is supplied (e.g.
        # in tests) so the index still parses each section only once.
        self._cache = cache if cache is not None else SectionParseCache(process)
        self._max_values_per_variable = max_values_per_variable
        # name (lower-cased) -> events sorted by (section index, line)
        self._events: Optional[dict[str, list[_Event]]] = None
        # Build-scoped memo tables keyed by node identity, so the per-node
        # subtree scans (_max_line, _assigned_names) run once per node instead
        # of being re-walked on every enclosing IF/WHILE exit — otherwise an
        # ELSEIF chain (nested IfStatements) costs O(n^2). Every AST node stays
        # alive in self._cache for the whole build, so id() cannot be reused.
        self._max_line_memo: dict[int, int] = {}
        self._assigned_memo: dict[int, set[str]] = {}

    def possible_values_at(self, name: str, block: str, line: int) -> PossibleValues:
        """Return the set of values *name* may hold at *line* of *block*.

        Args:
            name: Variable name (case-insensitive).
            block: Section name: ``prolog``, ``metadata``, ``data`` or
                ``epilog``.
            line: 1-based line number relative to the section's code — the
                same coordinates rule tokens and AST nodes carry.

        Returns:
            The :class:`~linti.linter.possible_values.PossibleValues`
            cascade.  A variable that is dynamic at that point yields
            :data:`~linti.linter.possible_values.TOP`; one that was never
            written yields :data:`~linti.linter.possible_values.UNASSIGNED`.
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

        # DatasourceType/DatasourceQuery are TI predefined variables that
        # already hold the process metadata value before Prolog even runs —
        # seed them so a conditional reassignment (e.g. an IF with no ELSE)
        # joins against that starting value instead of the untaken branch
        # collapsing to unknown.
        if self._process.datasource_type is not None:
            self._record(
                env, "datasourcetype", 0, 0, single(self._process.datasource_type)
            )
        if self._process.datasource_query is not None:
            self._record(
                env, "datasourcequery", 0, 0, single(self._process.datasource_query)
            )

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
                for name in sorted(self._assigned_names(ast.statements)):
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

        end_line = self._max_line(stmt)
        assigned = self._assigned_names(stmt.then_body) | self._assigned_names(
            stmt.else_body
        )
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
        for name in sorted(self._assigned_names(stmt.body)):
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
        if len(values) > self._max_values_per_variable:
            return TOP
        return PossibleValues(values, a.complete and b.complete)

    # -- subtree scans (memoized per node) --------------------------------

    def _max_line(self, node: ASTNode) -> int:
        """The greatest source line touched by *node* and its descendants.

        The AST does not record the ``ENDIF`` line, so this approximates
        "after the IF" for placing a joined branch event.  Memoized on node
        identity: each node's subtree is scanned once per build, so an ELSEIF
        chain costs O(n) overall rather than O(n^2).
        """
        cached = self._max_line_memo.get(id(node))
        if cached is not None:
            return cached

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
                lines.append(self._max_line(child))
        for attr in ("then_body", "else_body", "body", "args"):
            for child in getattr(node, attr, None) or []:
                if isinstance(child, ASTNode):
                    lines.append(self._max_line(child))

        result = max(lines, default=0)
        self._max_line_memo[id(node)] = result
        return result

    def _assigned_names(self, statements: list) -> set[str]:
        """All variable names (lower-cased) assigned anywhere in *statements*.

        Per-statement results are memoized on node identity, so a nested
        ``IfStatement`` (an ELSEIF branch) is scanned once instead of again by
        every enclosing IF.  The returned set is a fresh accumulator; the
        cached per-node sets are only ever combined with ``|`` / ``|=``, never
        mutated in place.
        """
        names: set[str] = set()
        for stmt in statements:
            names |= self._assigned_in_stmt(stmt)
        return names

    def _assigned_in_stmt(self, stmt) -> set[str]:
        cached = self._assigned_memo.get(id(stmt))
        if cached is not None:
            return cached

        if isinstance(stmt, Assignment):
            names = {stmt.left.name.lower()}
        elif isinstance(stmt, IfStatement):
            names = self._assigned_names(stmt.then_body) | self._assigned_names(
                stmt.else_body
            )
        elif isinstance(stmt, WhileStatement):
            names = self._assigned_names(stmt.body)
        elif isinstance(stmt, UnknownStatement):
            names = {name for name, _ in _unknown_statement_assignments(stmt)}
        else:
            names = set()

        self._assigned_memo[id(stmt)] = names
        return names

    # -- expression evaluation --------------------------------------------

    def _evaluate(
        self, expr: Expression, env: dict[str, PossibleValues]
    ) -> PossibleValues:
        """Evaluate *expr* to the set of values it may produce."""
        if isinstance(expr, Number):
            try:
                return single(float(expr.value))
            except (TypeError, ValueError):
                return TOP
        if isinstance(expr, String):
            return single(expr.value)
        if isinstance(expr, Identifier):
            return env.get(expr.name.lower(), TOP)
        if isinstance(expr, UnaryExpression):
            return self._evaluate_unary(expr, env)
        if isinstance(expr, BinaryExpression):
            return self._evaluate_binary(expr, env)
        if isinstance(expr, FunctionCall) and _is_inline_if(expr):
            # TI's inline If(cond, then, else) picks one of two branches at
            # runtime; the condition does not affect the value set, so fold it
            # to the join of both branches — the same way the IF/ELSE statement
            # form is joined. An unknown branch keeps the join incomplete.
            return self._join(
                self._evaluate(expr.args[1], env), self._evaluate(expr.args[2], env)
            )
        # Other function calls and anything unexpected: dynamic.
        return TOP

    def _evaluate_unary(
        self, expr: UnaryExpression, env: dict[str, PossibleValues]
    ) -> PossibleValues:
        operand = self._evaluate(expr.operand, env)
        results: set = set()
        saw_unknown = False
        for atom in _atoms(operand):
            value = _apply_unary_operator(expr.operator.type, atom)
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
                value = _apply_binary_operator(op, a, b)
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
        if len(results) > self._max_values_per_variable:
            return TOP
        return PossibleValues(frozenset(results), not saw_unknown)


# -- ConstantEvaluationIndex internals: literal folding and AST scans ------


def _is_inline_if(expr: FunctionCall) -> bool:
    """True for a well-formed inline ``If(cond, then, else)`` call.

    TI overloads ``If`` as an expression function taking exactly three
    arguments; only that shape folds to a branch join.  Any other arity is a
    malformed or unrelated call and stays dynamic.
    """
    return expr.name.lower() == "if" and len(expr.args) == 3


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


def _apply_unary_operator(op_type: TokenType, atom: Value) -> Value:
    """Apply a unary operator to one atom, or UNKNOWN when not foldable."""
    if isinstance(atom, float):
        if op_type is TokenType.MINUS:
            return -atom
        if op_type is TokenType.PLUS:
            return atom
    return UNKNOWN


def _apply_binary_operator(op_type: TokenType, a: Value, b: Value) -> Value:
    """Apply a binary operator to two atoms, or UNKNOWN when not foldable."""
    if op_type is TokenType.PIPE:
        # Concatenation keeps known fragments even when a side is dynamic;
        # a fully known concatenation folds back to a plain string.
        return normalize_string_segments(as_segments(a) + as_segments(b))
    if isinstance(a, float) and isinstance(b, float):
        if op_type is TokenType.PLUS:
            return a + b
        if op_type is TokenType.MINUS:
            return a - b
        if op_type is TokenType.STAR:
            return a * b
        if op_type is TokenType.SLASH:
            return UNKNOWN if b == 0 else a / b
        if op_type is TokenType.BACKSLASH:
            # TI's \ division defines divide-by-zero as 0 rather than undefined.
            return 0.0 if b == 0 else a / b
    return UNKNOWN


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
