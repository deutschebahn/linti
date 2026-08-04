"""The concrete syntax tree: a lossless view of the token stream.

Where the AST answers *what does this code mean*, the CST answers *what does
this code look like*.  Every raw token — whitespace, newlines and comments
included — falls inside exactly one node, so any subtree can be rendered back
to its exact source text.  That is what makes structural auto-fixes (rewrapping
a long line, re-indenting a continuation line) possible at all: the AST drops
parentheses, commas, semicolons and all trivia, so nothing can be written back
out of it.

Nodes address tokens by **index into the raw token list**, not by holding token
objects.  A node spans ``[start, end)``; every index in that range that no child
covers belongs to the node itself, which is where trivia lives.  The root spans
the whole stream, so leading and trailing trivia are in the tree too.

The tree is built by :class:`~linti.parser.parser.Parser` as it parses, and the
AST is projected out of the same walk — one parse, one tree of record.  Each AST
node carries a ``cst`` back-pointer to its node here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator, Optional, Sequence

from linti.lexer.token import Token, TokenType

#: Token types that carry no syntax — they sit between the tokens that do.
TRIVIA_TOKEN_TYPES = frozenset(
    {TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT}
)


class CstKind(Enum):
    """What a node is, syntactically.

    Includes the constructs the AST desugars away — ``PAREN_GROUP``,
    ``ARG_LIST``, ``ELSEIF_CLAUSE`` — because a formatter needs to see the code
    as written, not as interpreted.
    """

    PROGRAM = auto()
    BLOCK = auto()

    ASSIGNMENT = auto()
    EXPRESSION_STATEMENT = auto()
    UNKNOWN_STATEMENT = auto()

    IF_STATEMENT = auto()
    IF_HEADER = auto()
    ELSEIF_CLAUSE = auto()
    ELSE_CLAUSE = auto()

    WHILE_STATEMENT = auto()
    WHILE_HEADER = auto()

    CALL = auto()
    ARG_LIST = auto()
    ARGUMENT = auto()
    PAREN_GROUP = auto()

    BINARY_EXPR = auto()
    UNARY_EXPR = auto()
    ELEMENT_REF = auto()

    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()


#: Node kinds that stand for one complete statement.
STATEMENT_KINDS = frozenset(
    {
        CstKind.ASSIGNMENT,
        CstKind.EXPRESSION_STATEMENT,
        CstKind.UNKNOWN_STATEMENT,
        CstKind.IF_STATEMENT,
        CstKind.WHILE_STATEMENT,
    }
)


@dataclass
class CstNode:
    """One syntactic construct, addressed as a half-open raw-token range.

    Attributes:
        kind: What the node is.
        start: First raw token index, inclusive.
        end: One past the last raw token index.
        children: Child nodes, in source order and non-overlapping.
        parent: Enclosing node, or ``None`` for the root.
    """

    kind: CstKind
    start: int
    end: int
    children: list["CstNode"] = field(default_factory=list)
    parent: Optional["CstNode"] = None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CstNode({self.kind.name}, {self.start}:{self.end}, {len(self.children)} children)"

    # -----------------------------
    # token access
    # -----------------------------
    def tokens(self, all_tokens: Sequence[Token]) -> Sequence[Token]:
        """The raw tokens this node spans, trivia included."""
        return all_tokens[self.start : self.end]

    def significant_tokens(self, all_tokens: Sequence[Token]) -> list[Token]:
        """The node's tokens with whitespace, newlines and comments removed."""
        return [
            t
            for t in all_tokens[self.start : self.end]
            if t.type not in TRIVIA_TOKEN_TYPES
        ]

    def first_significant(self, all_tokens: Sequence[Token]) -> Optional[Token]:
        """The node's first non-trivia token, or ``None`` if it has none."""
        for token in all_tokens[self.start : self.end]:
            if token.type not in TRIVIA_TOKEN_TYPES:
                return token
        return None

    def last_significant(self, all_tokens: Sequence[Token]) -> Optional[Token]:
        """The node's last non-trivia token, or ``None`` if it has none."""
        for token in reversed(all_tokens[self.start : self.end]):
            if token.type not in TRIVIA_TOKEN_TYPES:
                return token
        return None

    # -----------------------------
    # source access
    # -----------------------------
    def span(self, all_tokens: Sequence[Token]) -> Optional[tuple[int, int]]:
        """``(start, end)`` character offsets, or ``None`` for an empty node."""
        if self.start >= self.end:
            return None
        return all_tokens[self.start].position, all_tokens[self.end - 1].end_position

    def text(self, source: str, all_tokens: Sequence[Token]) -> str:
        """The exact source text this node spans.

        Sliced from *source* rather than joined from token values, because a
        STRING token's value has lost its quotes.
        """
        span = self.span(all_tokens)
        if span is None:
            return ""
        return source[span[0] : span[1]]

    # -----------------------------
    # traversal
    # -----------------------------
    def walk(self) -> Iterator["CstNode"]:
        """Yield this node and every descendant, parents before children."""
        yield self
        for child in self.children:
            yield from child.walk()

    def covers(self, token_index: int) -> bool:
        """Whether *token_index* falls inside this node's span."""
        return self.start <= token_index < self.end

    def covering_node(self, token_index: int) -> Optional["CstNode"]:
        """The innermost node containing *token_index*, or ``None``.

        Trivia resolves to the innermost node that *encloses* it, since no
        child claims it.
        """
        if not self.covers(token_index):
            return None
        node = self
        while True:
            for child in node.children:
                if child.covers(token_index):
                    node = child
                    break
            else:
                return node

    def ancestors(self) -> Iterator["CstNode"]:
        """Yield the enclosing nodes, innermost first."""
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def enclosing_statement(self) -> Optional["CstNode"]:
        """The nearest enclosing statement node, this one included."""
        if self.kind in STATEMENT_KINDS:
            return self
        for ancestor in self.ancestors():
            if ancestor.kind in STATEMENT_KINDS:
                return ancestor
        return None
