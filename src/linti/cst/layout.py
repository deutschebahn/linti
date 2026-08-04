"""Re-rendering a statement across several lines.

This is the half of the CST's purpose that reading alone cannot serve: given a
line that is too long, produce the same code laid out over several lines.  It
works by walking the tree and deciding, per construct, whether the construct
fits on the line it starts on — and if not, where it may be split.

Two things it deliberately does **not** do:

* **Re-space anything.** Text that stays on one line is copied verbatim from
  the source, so F220/F230/F250/F260 keep sole ownership of intra-line spacing
  and cannot end up fighting this module.
* **Join lines.** Only breaks are added.  A caller that finds no over-long line
  never calls in here at all.

The layout it produces is the hanging style :mod:`linti.cst.lines` describes,
so re-linting the output with F310 finds nothing to change.
"""

from __future__ import annotations

from typing import Optional, Sequence

from linti.cst.node import TRIVIA_TOKEN_TYPES as _TRIVIA_TYPES, CstKind, CstNode
from linti.lexer.token import Token, TokenType

#: Constructs that can be re-rendered as a unit.  An IF/WHILE *statement* is
#: not among them: it spans its whole body, whose statements own their own
#: lines, so only its header is ever reflowed.
REFLOWABLE_KINDS = frozenset(
    {
        CstKind.ASSIGNMENT,
        CstKind.EXPRESSION_STATEMENT,
        CstKind.IF_HEADER,
        CstKind.WHILE_HEADER,
    }
)

_WHITESPACE_TYPES = frozenset({TokenType.WHITESPACE, TokenType.NEWLINE})


def reflow_target(node: Optional[CstNode]) -> Optional[CstNode]:
    """The nearest enclosing construct that can be re-rendered, or None.

    Walking up rather than down is what makes an ELSEIF header resolve to its
    own header instead of the header of the IF it hangs off.
    """
    while node is not None:
        if node.kind in REFLOWABLE_KINDS:
            return node
        node = node.parent
    return None


class Reflow:
    """Renders one construct across as few lines as the limit allows."""

    def __init__(
        self,
        tokens: Sequence[Token],
        source: str,
        *,
        limit: int,
        indent_size: int = 4,
    ) -> None:
        self._tokens = tokens
        self._source = source
        self._limit = limit
        self._indent_size = indent_size

    # -----------------------------
    # public API
    # -----------------------------
    def can_reflow(self, node: CstNode) -> bool:
        """Whether *node* may be re-rendered at all.

        A comment inside the span would have to move with the code around it,
        and a comment that lands on the wrong line silently comments out what
        follows.  A multi-line string cannot move either — its line breaks are
        part of its value.  Neither is worth guessing about.
        """
        for token in self._tokens[node.start : node.end]:
            if token.type == TokenType.COMMENT:
                return False
            if token.type == TokenType.STRING and "\n" in token.value:
                return False
        return True

    def render(self, node: CstNode, indent: int) -> Optional[str]:
        """Re-render *node* starting at column *indent*, or None to leave it.

        Returns None when the node must not be touched, or when the rendering
        is what the source already says — a fix that changes nothing would
        make the auto-fix loop look busy without converging.
        """
        if not self.can_reflow(node):
            return None
        rendered = self._render(node, indent, indent)
        return None if rendered == self._text(node.start, node.end) else rendered

    # -----------------------------
    # rendering
    # -----------------------------
    def _render(self, node: CstNode, first_col: int, base: int) -> str:
        """Render *node*, whose first line starts at column *first_col*.

        *base* is the indentation a construct returns to after breaking — the
        column its closing delimiter belongs at.
        """
        flat = self._flat(node.start, node.end)
        if first_col + len(flat) <= self._limit:
            return flat

        if node.kind in (CstKind.ASSIGNMENT, CstKind.EXPRESSION_STATEMENT):
            return self._render_statement(node, first_col, base)
        if node.kind in (CstKind.IF_HEADER, CstKind.WHILE_HEADER):
            return self._render_header(node, base)
        if node.kind is CstKind.CALL:
            return self._render_call(node, first_col, base)
        if node.kind is CstKind.ARG_LIST:
            return self._render_arg_list(node, base)
        if node.kind is CstKind.BINARY_EXPR:
            return self._render_binary(node, first_col, base)
        if node.kind is CstKind.PAREN_GROUP:
            return self._render_paren_group(node, base)
        if node.kind is CstKind.ARGUMENT:
            # A pure wrapper around one expression — break through it, or a
            # nested call that is still too long would never be reached.
            return self._render_wrapper(node, first_col, base, flat)

        # Nothing here can be broken — a single long literal, say.
        return flat

    def _render_wrapper(
        self, node: CstNode, first_col: int, base: int, flat: str
    ) -> str:
        """Render a node that only wraps one child of identical extent."""
        if len(node.children) != 1:
            return flat
        child = node.children[0]
        if (child.start, child.end) != (node.start, node.end):
            return flat
        return self._render(child, first_col, base)

    def _render_statement(self, node: CstNode, first_col: int, base: int) -> str:
        """``lhs = <expr>;`` — keep the head, break inside the expression."""
        payload = node.children[-1] if node.children else None
        if payload is None:
            return self._flat(node.start, node.end)

        head = self._flat(node.start, payload.start)
        tail = self._flat(payload.end, node.end)
        body = self._render(payload, first_col + len(head), base)
        return f"{head}{body}{tail}"

    def _render_header(self, node: CstNode, base: int) -> str:
        """``IF( <cond> );`` — put the condition on its own lines."""
        condition = node.children[0] if node.children else None
        if condition is None:
            return self._flat(node.start, node.end)

        inner = base + self._indent_size
        head = self._flat(node.start, condition.start).rstrip()
        tail = self._flat(condition.end, node.end).lstrip()
        body = self._render(condition, inner, inner)
        return f"{head}\n{' ' * inner}{body}\n{' ' * base}{tail}"

    def _render_call(self, node: CstNode, first_col: int, base: int) -> str:
        """``Name( ... )`` — the name stays put, the argument list breaks."""
        arg_list = next((c for c in node.children if c.kind is CstKind.ARG_LIST), None)
        if arg_list is None:
            return self._flat(node.start, node.end)

        head = self._flat(node.start, arg_list.start)
        return head + self._render(arg_list, first_col + len(head), base)

    def _render_arg_list(self, node: CstNode, base: int) -> str:
        """One argument per line, closing paren back at *base*."""
        arguments = [c for c in node.children if c.kind is CstKind.ARGUMENT]
        if not arguments:
            return self._flat(node.start, node.end)

        inner = base + self._indent_size
        parts = ["("]
        for position, argument in enumerate(arguments):
            body = self._render(argument, inner, inner)
            separator = "," if position < len(arguments) - 1 else ""
            parts.append(f"\n{' ' * inner}{body}{separator}")
        parts.append(f"\n{' ' * base})")
        return "".join(parts)

    def _render_paren_group(self, node: CstNode, base: int) -> str:
        """``( <expr> )`` used for grouping, not for a call."""
        inner_node = node.children[0] if node.children else None
        if inner_node is None:
            return self._flat(node.start, node.end)

        inner = base + self._indent_size
        body = self._render(inner_node, inner, inner)
        return f"(\n{' ' * inner}{body}\n{' ' * base})"

    def _render_binary(self, node: CstNode, first_col: int, base: int) -> str:
        """Break an operator chain, with each operator leading its line.

        The chain is flattened first: the parser nests ``a & b & c`` to the
        left, and rendering that shape literally would step the indentation
        one level deeper per operator.
        """
        operands = self._operand_chain(node)
        if len(operands) < 2:
            return self._flat(node.start, node.end)

        # A chain that already owns its line continues at that same column;
        # one that follows a prefix (``sX = ``) hangs one level deeper.
        continuation = base if first_col <= base else base + self._indent_size

        # The first operand still sits on the line the construct started on,
        # so anything *it* opens closes back at the original base.  Only the
        # operands that move to their own lines take the continuation as base.
        first = operands[0]
        parts = [self._render(first, first_col, base)]
        previous = first
        for operand in operands[1:]:
            operator = self._flat(previous.end, operand.start).strip()
            body = self._render(operand, continuation + len(operator) + 1, continuation)
            parts.append(f"\n{' ' * continuation}{operator} {body}")
            previous = operand
        return "".join(parts)

    def _operand_chain(self, node: CstNode) -> list[CstNode]:
        """Flatten a left-nested chain of *the same* operator into its operands.

        Only same-operator nesting may be flattened.  ``nA = 1 & nB = 2`` is
        left-nested twice over, but its ``=`` and ``&`` levels mean different
        things, and breaking at both would scatter ``nA`` and ``1`` onto
        separate lines.
        """
        operator = self._operator_of(node)
        if operator is None:
            return list(node.children)

        left, right = node.children
        inner = self._operator_of(left)
        if inner is not None and inner.type == operator.type:
            return self._operand_chain(left) + [right]
        return [left, right]

    def _operator_of(self, node: CstNode) -> Optional[Token]:
        """The operator token joining a binary node's two operands."""
        if node.kind is not CstKind.BINARY_EXPR or len(node.children) != 2:
            return None
        left, right = node.children
        for index in range(left.end, right.start):
            token = self._tokens[index]
            if token.type not in _TRIVIA_TYPES:
                return token
        return None

    # -----------------------------
    # source access
    # -----------------------------
    def _text(self, start: int, end: int) -> str:
        """Exact source text of a raw token range."""
        if start >= end:
            return ""
        return self._source[
            self._tokens[start].position : self._tokens[end - 1].end_position
        ]

    def _flat(self, start: int, end: int) -> str:
        """Source text of a token range, on one line.

        Only whitespace runs that *contain* a newline are rewritten, and only
        to a single space.  Spacing that was already within one line is copied
        through untouched, so this never second-guesses the spacing rules —
        including the space in ``lhs = rhs``, which callers slice as its own
        range.
        """
        parts: list[str] = []
        run: list[Token] = []

        def flush():
            if not run:
                return
            text = "".join(t.raw_text(self._source) for t in run)
            parts.append(" " if "\n" in text else text)
            run.clear()

        for token in self._tokens[start:end]:
            if token.type in _WHITESPACE_TYPES:
                run.append(token)
                continue
            flush()
            parts.append(token.raw_text(self._source))

        flush()
        return "".join(parts)
