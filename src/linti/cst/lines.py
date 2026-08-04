"""Physical-line model derived from the CST.

Token lookaround can tell a rule what sits next to a token, but not whether the
line it is on *starts* a statement or *continues* one — and that distinction is
the whole difference between

.. code-block:: none

    sValue = CellGetS(
        'Cube',
        'Elem'
    );

being correctly formatted and being three badly indented statements.  This
module answers that question once per section and hands rules the result.

The house style is a **hanging indent**: an opening delimiter stays at the end
of its line, everything inside it is indented one level deeper, and the line
that closes it returns to the level of the line that opened it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from linti.cst.node import TRIVIA_TOKEN_TYPES, CstKind, CstNode, STATEMENT_KINDS
from linti.lexer.token import Token, TokenType

#: Nodes that begin a line the way a statement does, without being one.
CLAUSE_KINDS = frozenset({CstKind.ELSEIF_CLAUSE, CstKind.ELSE_CLAUSE})

#: Keywords that close a construct.  They are plain tokens inside their
#: statement rather than nodes of their own, so they need naming explicitly.
CLOSING_KEYWORDS = frozenset({TokenType.ENDIF, TokenType.END})

#: How a continuation line should be indented.  ``hanging`` is the house
#: style; ``aligned`` keeps content under the opening delimiter; ``ignore``
#: leaves hand-formatted continuations alone.
HANGING = "hanging"
ALIGNED = "aligned"
IGNORE = "ignore"
CONTINUATION_STYLES = (HANGING, ALIGNED, IGNORE)


@dataclass(frozen=True)
class LineInfo:
    """What one physical line is, structurally.

    Attributes:
        line: 1-based line number.
        first_token: First non-trivia token starting on this line, or None for
            a blank or comment-only line.
        indent_token: The leading WHITESPACE token, or None when the line
            starts at column 1.
        indent_width: Number of leading whitespace characters.
        is_blank: The line holds no tokens but whitespace.
        is_comment_only: The line's only content is a comment.
        inside_multiline_token: The line falls *within* a token that started
            earlier — a multi-line string literal.  Its layout is data, not
            code, and must never be reindented.
        statement: The CST statement node this line belongs to, or None.
        is_continuation: The line continues a statement begun on an earlier
            line, rather than starting one.
        block_level: Control-flow nesting depth (number of enclosing blocks).
        delim_depth: Unclosed ``(`` at the start of this line, counted from the
            start of its statement.
        anchor_columns: For each open delimiter, the 1-based column its content
            aligns under — the first token after that ``(`` on the ``(``'s own
            line, or None when the ``(`` ended its line.  Only the ``aligned``
            continuation style reads this.
        starts_with_closer: The first significant token is ``)``.
    """

    line: int
    first_token: Optional[Token] = None
    indent_token: Optional[Token] = None
    indent_width: int = 0
    is_blank: bool = False
    is_comment_only: bool = False
    inside_multiline_token: bool = False
    statement: Optional[CstNode] = None
    is_continuation: bool = False
    block_level: int = 0
    delim_depth: int = 0
    anchor_columns: tuple[Optional[int], ...] = ()
    starts_with_closer: bool = False

    @property
    def is_code(self) -> bool:
        """Whether this line carries code whose indentation is meaningful."""
        return (
            self.first_token is not None
            and not self.is_blank
            and not self.is_comment_only
            and not self.inside_multiline_token
        )


class LineIndex:
    """Per-line structural facts about one lexed and parsed section."""

    def __init__(self, tokens: Sequence[Token], root: CstNode) -> None:
        self._tokens = tokens
        self._root = root
        self._lines: dict[int, LineInfo] = {}
        self._build()

    # -----------------------------
    # public API
    # -----------------------------
    def get(self, line: int) -> Optional[LineInfo]:
        """The model for *line*, or None if the section has no such line."""
        return self._lines.get(line)

    def __iter__(self):
        for line in sorted(self._lines):
            yield self._lines[line]

    def leads_line(self, token: Token) -> bool:
        """Whether *token* is the first significant token on its line.

        Spacing rules ask this before judging the whitespace *in front of* a
        token: on a continuation line that whitespace is indentation, which
        belongs to F310, not to them.
        """
        info = self.get(token.line)
        return info is not None and info.first_token is token

    def expected_indent(
        self, line: int, indent_size: int, style: str = HANGING
    ) -> Optional[int]:
        """Canonical indentation for *line*, or None when it has no opinion.

        A statement line is always indented by its control-flow nesting.  How a
        *continuation* line is indented depends on *style*:

        ``hanging`` (the house style)
            One level per delimiter the line sits inside, at least one level,
            so an operator continuation outside any parentheses still hangs::

                sX = 'aaa'
                    | 'bbb';

            A line that *closes* a delimiter returns to the level of the line
            that opened it, which is what puts ``);`` back under its statement.

        ``aligned``
            Continuation content lines up under the first argument of the call
            it belongs to, falling back to hanging where that is impossible
            (the ``(`` ended its line, so there is nothing to align with).

        ``ignore``
            No opinion at all — hand-formatted continuations are left alone.
        """
        info = self.get(line)
        if info is None or not info.is_code:
            return None

        base = info.block_level * indent_size
        if not info.is_continuation:
            return base
        if style == IGNORE:
            return None

        if style == ALIGNED:
            anchor = self._anchor_for(info)
            if anchor is not None:
                return anchor - 1

        level = info.delim_depth - (1 if info.starts_with_closer else 0)
        if not info.starts_with_closer:
            level = max(level, 1)
        return base + max(level, 0) * indent_size

    @staticmethod
    def _anchor_for(info: LineInfo) -> Optional[int]:
        """Column the aligned style wants, or None when nothing lines up.

        A line that closes a delimiter aligns with the level *outside* it, so
        ``)`` lands under the construct it closes rather than under the
        arguments it follows.
        """
        level = info.delim_depth - 1 if info.starts_with_closer else info.delim_depth
        if level <= 0 or level > len(info.anchor_columns):
            return None
        return info.anchor_columns[level - 1]

    # -----------------------------
    # construction
    # -----------------------------
    def _build(self) -> None:
        starts = self._statement_start_indices()
        multiline = self._lines_inside_multiline_tokens()

        for line, (index, token) in self._first_token_per_line().items():
            if line in multiline:
                self._lines[line] = LineInfo(line=line, inside_multiline_token=True)
                continue
            self._lines[line] = self._describe(line, index, token, starts)

        for line in sorted(multiline):
            self._lines.setdefault(
                line, LineInfo(line=line, inside_multiline_token=True)
            )

    def _describe(self, line, index, token, starts) -> LineInfo:
        """Build the model for a line, given its first token."""
        indent_token = token if token.type == TokenType.WHITESPACE else None
        indent_width = len(indent_token.value) if indent_token else 0

        significant = self._first_significant_on_line(index, line)
        if significant is None:
            trailing = self._first_non_whitespace_on_line(index, line)
            return LineInfo(
                line=line,
                indent_token=indent_token,
                indent_width=indent_width,
                is_blank=trailing is None or trailing[1].type == TokenType.NEWLINE,
                is_comment_only=trailing is not None
                and trailing[1].type == TokenType.COMMENT,
            )

        sig_index, sig_token = significant
        node = self._root.covering_node(sig_index)
        statement = node.enclosing_statement() if node else None

        starts_statement = sig_index in starts
        is_closing_keyword = sig_token.type in CLOSING_KEYWORDS
        open_delimiters = self._open_delimiters(statement, sig_index)

        return LineInfo(
            line=line,
            first_token=sig_token,
            indent_token=indent_token,
            indent_width=indent_width,
            statement=statement,
            is_continuation=not starts_statement and not is_closing_keyword,
            block_level=self._block_level(node),
            delim_depth=len(open_delimiters),
            anchor_columns=tuple(self._anchor_column(i) for i in open_delimiters),
            starts_with_closer=sig_token.type == TokenType.RPAREN,
        )

    def _statement_start_indices(self) -> dict[int, CstNode]:
        """Token indices at which a statement or a clause begins."""
        starts: dict[int, CstNode] = {}
        for node in self._root.walk():
            if node.kind not in STATEMENT_KINDS and node.kind not in CLAUSE_KINDS:
                continue
            index = self._first_significant_index(node)
            if index is not None:
                starts.setdefault(index, node)
        return starts

    def _first_significant_index(self, node: CstNode) -> Optional[int]:
        for index in range(node.start, node.end):
            if self._tokens[index].type not in TRIVIA_TOKEN_TYPES:
                return index
        return None

    def _first_token_per_line(self) -> dict[int, tuple[int, Token]]:
        first: dict[int, tuple[int, Token]] = {}
        for index, token in enumerate(self._tokens):
            first.setdefault(token.line, (index, token))
        return first

    def _lines_inside_multiline_tokens(self) -> set[int]:
        """Lines that continue a token started on an earlier line.

        Only a string literal can do this, and reindenting inside one would
        change the value of the string.
        """
        inside: set[int] = set()
        for token in self._tokens:
            if token.type == TokenType.NEWLINE:
                continue
            spanned = token.value.count("\n")
            for offset in range(1, spanned + 1):
                inside.add(token.line + offset)
        return inside

    def _first_significant_on_line(self, index, line):
        for i in range(index, len(self._tokens)):
            token = self._tokens[i]
            if token.line != line:
                return None
            if token.type not in TRIVIA_TOKEN_TYPES:
                return i, token
        return None

    def _first_non_whitespace_on_line(self, index, line):
        for i in range(index, len(self._tokens)):
            token = self._tokens[i]
            if token.line != line:
                return None
            if token.type != TokenType.WHITESPACE:
                return i, token
        return None

    @staticmethod
    def _block_level(node: Optional[CstNode]) -> int:
        """Control-flow nesting depth: how many blocks enclose *node*."""
        if node is None:
            return 0
        level = 1 if node.kind is CstKind.BLOCK else 0
        return level + sum(1 for a in node.ancestors() if a.kind is CstKind.BLOCK)

    def _open_delimiters(self, statement: Optional[CstNode], index: int) -> list[int]:
        """Token indices of the ``(`` still open at *index*, outermost first."""
        if statement is None:
            return []
        stack: list[int] = []
        for i in range(statement.start, index):
            token_type = self._tokens[i].type
            if token_type == TokenType.LPAREN:
                stack.append(i)
            elif token_type == TokenType.RPAREN and stack:
                stack.pop()
        return stack

    def _anchor_column(self, lparen_index: int) -> Optional[int]:
        """Column of the first token after a ``(`` on the ``(``'s own line.

        None when the ``(`` ended its line — there is then nothing on screen to
        align continuation content with.
        """
        lparen = self._tokens[lparen_index]
        for i in range(lparen_index + 1, len(self._tokens)):
            token = self._tokens[i]
            if token.line != lparen.line:
                return None
            if token.type not in TRIVIA_TOKEN_TYPES:
                return token.column
        return None
