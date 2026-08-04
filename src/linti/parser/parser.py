from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence

from linti.cst.node import CstKind, CstNode
from linti.lexer.token import Token, TokenType
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    Expression,
    ExpressionStatement,
    FunctionCall,
    Identifier,
    IfStatement,
    Number,
    Program,
    Statement,
    String,
    UnaryExpression,
    UnknownStatement,
    WhileStatement,
)


class ParseError(Exception):
    pass


class NestingDepthExceeded(ParseError):
    """Raised when control-flow nesting exceeds the configured maximum.

    A subclass of ParseError so it is catchable as one, but distinguishable so
    the statement-level error recovery re-raises it instead of swallowing it
    into an UnknownStatement — letting it unwind the whole recursive descent.
    """


# Default cap on control-flow nesting depth. Well under Python's recursion
# limit (~1000), far deeper than any realistic TI process.
DEFAULT_MAX_NESTING_DEPTH = 150


IGNORED_FOR_PARSING = {TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT}

#: Cell-address functions whose element arguments (every argument after the
#: leading cube name) may use the ``hierarchy:element`` reference syntax.
ELEMENT_REF_FUNCTIONS = frozenset({"cellisupdateable", "cellgets"})


@dataclass(frozen=True)
class Precedence:
    # higher number = binds stronger
    NONE: int = 0
    ASSIGN: int = 1
    LOGIC_OR: int = 2
    LOGIC_AND: int = 3
    COMPARE: int = 4
    SUM: int = 5
    PRODUCT: int = 6
    PREFIX: int = 7
    CALL: int = 8


# Pratt binding powers for infix operators
INFIX_PRECEDENCE = {
    # Logical operators (TI: & = AND, % = OR); bind weaker than comparisons
    TokenType.OR: Precedence.LOGIC_OR,
    TokenType.AND: Precedence.LOGIC_AND,
    TokenType.PLUS: Precedence.SUM,
    TokenType.MINUS: Precedence.SUM,
    TokenType.PIPE: Precedence.SUM,
    TokenType.STAR: Precedence.PRODUCT,
    TokenType.SLASH: Precedence.PRODUCT,
    TokenType.BACKSLASH: Precedence.PRODUCT,
    # Comparison operators
    TokenType.EQUALS: Precedence.COMPARE,
    TokenType.LESS: Precedence.COMPARE,
    TokenType.GREATER: Precedence.COMPARE,
    TokenType.LESS_EQUAL: Precedence.COMPARE,
    TokenType.GREATER_EQUAL: Precedence.COMPARE,
    TokenType.NOT_EQUAL: Precedence.COMPARE,
    TokenType.STRING_EQUALS: Precedence.COMPARE,
    TokenType.STRING_NOT_EQUAL: Precedence.COMPARE,
}


@dataclass(frozen=True)
class _Checkpoint:
    """A point the parser can retroactively open a CST node from.

    Records both the token position and how many sibling nodes had been
    collected, so a node opened later can still claim the tokens *and* the
    child nodes produced since.  That is what lets the Pratt loop wrap an
    already-parsed left operand in a BINARY_EXPR or CALL.
    """

    pos: int
    child_count: int


class _Span:
    """Handle for one open CST node, yielded by :meth:`Parser._span`."""

    __slots__ = ("kind", "node", "_ast", "_flatten")

    def __init__(self, kind: CstKind):
        self.kind = kind
        self.node: Optional[CstNode] = None
        self._ast = None
        self._flatten = False

    def attach(self, ast_node):
        """Bind *ast_node* to this span and return it unchanged.

        The ``cst`` back-pointer is set when the span closes, since that is
        when the node exists.  Written as ``return sp.attach(Assignment(...))``
        so the parse methods keep their original shape.
        """
        self._ast = ast_node
        return ast_node

    def flatten(self) -> None:
        """Drop the child nodes collected so far, keeping only the span.

        Used for error recovery: a half-built ASSIGNMENT inside a statement
        that turned out to be unparseable would be misleading as a child of
        the resulting UNKNOWN_STATEMENT.
        """
        self._flatten = True


class Parser:
    """
    Minimal Pratt parser for TM1-like TI expressions + assignment statements.

    Grammar (informal):
      statement   := assignment
      assignment  := IDENTIFIER "=" expression ";"
      expression  := pratt_expression
      primary     := NUMBER | STRING | IDENTIFIER | "(" expression ")"
      call        := IDENTIFIER "(" [expression ("," expression)*] ")"
    """

    def __init__(
        self,
        tokens: Sequence[Token],
        ignore_whitespace: bool = True,
        max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH,
    ):
        """
        Initialize the parser with a sequence of tokens.

        Args:
            tokens: Sequence of Token objects to parse.
            ignore_whitespace: If True, filters out WHITESPACE and NEWLINE tokens.
                              Default is True.
            max_nesting_depth: Maximum control-flow nesting depth before a
                              NestingDepthExceeded is raised (guards against a
                              RecursionError on pathological input).
        """
        self.raw_tokens: list[Token] = list(tokens)
        if ignore_whitespace:
            kept = [
                (i, t)
                for i, t in enumerate(self.raw_tokens)
                if t.type not in IGNORED_FOR_PARSING
            ]
            self.tokens = [t for _, t in kept]
            #: Maps a position in ``self.tokens`` back to ``self.raw_tokens``.
            #: The CST spans raw indices so trivia stays addressable.
            self._raw_index = [i for i, _ in kept]
        else:
            self.tokens = list(tokens)
            self._raw_index = list(range(len(self.tokens)))

        self.pos = 0
        self._max_nesting_depth = max_nesting_depth
        self._depth = 0

        #: CST nodes closed but not yet claimed by an enclosing span, in source
        #: order.  A closing span takes everything from its checkpoint onward.
        self._pending: list[CstNode] = []
        #: Root of the concrete syntax tree; set by :meth:`parse`.
        self.cst: Optional[CstNode] = None

    # -----------------------------
    # CST construction
    # -----------------------------
    def _checkpoint(self) -> _Checkpoint:
        """Mark the current position so a node can be opened here later."""
        return _Checkpoint(pos=self.pos, child_count=len(self._pending))

    def _raw_span(self, start_pos: int, end_pos: int) -> tuple[int, int]:
        """Translate a ``self.tokens`` range into a ``self.raw_tokens`` range.

        The result is half-open and includes any trivia *between* the first and
        last significant token, but not the trivia around them — that belongs
        to the enclosing node.
        """
        if end_pos <= start_pos:
            # Nothing was consumed (e.g. an empty block).  Anchor the empty
            # span where the next token would have been.
            anchor = (
                self._raw_index[start_pos]
                if start_pos < len(self._raw_index)
                else len(self.raw_tokens)
            )
            return anchor, anchor
        return self._raw_index[start_pos], self._raw_index[end_pos - 1] + 1

    @contextmanager
    def _span(
        self, kind: CstKind, checkpoint: Optional[_Checkpoint] = None
    ) -> Iterator[_Span]:
        """Open a CST node covering everything parsed inside the block.

        Pass *checkpoint* to open the node retroactively at an earlier point —
        the Pratt loop uses that to wrap an already-parsed left operand.

        The node is closed in a ``finally``, so a ParseError unwinding through
        here still leaves a well-formed (if partial) tree.
        """
        mark = self._checkpoint() if checkpoint is None else checkpoint
        span = _Span(kind)
        try:
            yield span
        finally:
            children = self._pending[mark.child_count :]
            del self._pending[mark.child_count :]
            if span._flatten:
                children = []
            raw_start, raw_end = self._raw_span(mark.pos, self.pos)
            node = CstNode(kind, raw_start, raw_end, children)
            for child in children:
                child.parent = node
            self._pending.append(node)
            span.node = node
            if span._ast is not None:
                span._ast.cst = node

    # -----------------------------
    # basic stream helpers
    # -----------------------------
    def at_end(self) -> bool:
        """
        Check if the parser has reached the end of input.

        Returns:
            True if past the last token or current token is EOF, False otherwise.
        """
        return self.pos >= len(self.tokens) or self.current().type == TokenType.EOF

    def current(self) -> Token:
        """
        Get the current token without advancing.

        Returns:
            The token at the current position.

        Raises:
            ParseError: If past the end of input.
        """
        if self.pos >= len(self.tokens):
            # If you don't have EOF tokens, we synthesize an EOF-ish error token
            raise ParseError("Unexpected end of input")
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Optional[Token]:
        """
        Look ahead at a future token without advancing.

        Args:
            offset: Number of positions to look ahead (default 1).

        Returns:
            The token at (current position + offset), or None if past end of input.
        """
        i = self.pos + offset
        if i >= len(self.tokens):
            return None
        return self.tokens[i]

    def advance(self) -> Token:
        """
        Consume and return the current token, moving to the next.

        Returns:
            The current token before advancing.

        Raises:
            ParseError: If at end of input.
        """
        tok = self.current()
        self.pos += 1
        return tok

    def match(self, token_type: TokenType) -> bool:
        """
        Check if current token matches the given type and consume it if so.

        Args:
            token_type: The TokenType to match against.

        Returns:
            True if matched and consumed, False otherwise.
        """
        if not self.at_end() and self.current().type == token_type:
            self.advance()
            return True
        return False

    def expect(self, token_type: TokenType, message: str | None = None) -> Token:
        """
        Assert current token matches the given type and consume it.

        Args:
            token_type: The TokenType expected.
            message: Optional custom error message.

        Returns:
            The matched token.

        Raises:
            ParseError: If token does not match or at end of input.
        """
        if self.at_end() or self.current().type != token_type:
            got = self._current_token_name_for_error()
            want = token_type.name
            raise ParseError(message or f"Expected {want}, got {got}")
        return self.advance()

    def is_identifier(self, token: Token) -> bool:
        """
        Check if a token is any kind of identifier (regular or predefined).

        Args:
            token: The token to check.

        Returns:
            True if token is IDENTIFIER or PREDEFINED_IDENTIFIER, False otherwise.
        """
        return token.type in (TokenType.IDENTIFIER, TokenType.PREDEFINED_IDENTIFIER)

    def _current_token_name_for_error(self) -> str:
        """Return current token type name or EOF when at end of stream."""
        return "EOF" if self.at_end() else self.current().type.name

    # -----------------------------
    # entry points
    # -----------------------------
    def parse(self) -> Program:
        """
        Parse the entire token stream into a Program AST.

        Returns:
            A Program node containing all statements.

        Raises:
            ParseError: If any statement is invalid.
        """
        statements = []

        with self._span(CstKind.PROGRAM) as span:
            while not self.at_end():
                stmt = self._parse_one_statement()
                if stmt:
                    statements.append(stmt)
            program = span.attach(Program(statements))

        # The root claims the entire stream so leading and trailing trivia are
        # inside the tree — a CST that stops at the last semicolon could not
        # render a file back out.
        root = program.cst
        root.start = 0
        root.end = len(self.raw_tokens)
        self.cst = root

        return program

    def _parse_one_statement(self) -> Optional[Statement]:
        """
        Parse a single statement with error recovery.

        Returns:
            A Statement node (Assignment, ExpressionStatement, IfStatement, or UnknownStatement),
            or None if nothing to parse.

        On parse error, returns an UnknownStatement and skips to the next semicolon
        to allow the parser to continue with subsequent statements.
        """
        if self.at_end():
            return None

        self._depth += 1
        try:
            if self._depth > self._max_nesting_depth:
                raise NestingDepthExceeded(
                    f"Maximum nesting depth ({self._max_nesting_depth}) exceeded"
                )
            return self._parse_statement_dispatch()
        finally:
            self._depth -= 1

    def _parse_statement_dispatch(self) -> Optional[Statement]:
        """Dispatch to the concrete statement parser, with error recovery.

        On a ParseError the offending tokens are collected into an
        UnknownStatement so parsing can continue.  A NestingDepthExceeded is
        deliberately *not* recovered — it propagates so the whole recursive
        descent unwinds instead of hitting a RecursionError.
        """
        # Where this statement began.  The concrete parsers advance as they go,
        # so by the time one fails ``self.pos`` sits at the point of failure —
        # recording the start lets the UnknownStatement carry the *whole*
        # statement (as its docstring promises) instead of only the tail after
        # the error, which is what positions E110 and lets version-aware rules
        # still see the call hiding inside a broken statement.
        start = self.pos
        children_before = len(self._pending)
        try:
            # Check for IF statement
            if self.current().type == TokenType.IF:
                return self._parse_if_statement()

            # Check for WHILE statement
            if self.current().type == TokenType.WHILE:
                return self._parse_while_statement()

            # Try to parse an assignment: IDENTIFIER "=" expression ";"
            if self.is_identifier(self.current()):
                next_tok = self.peek()
                if next_tok and next_tok.type == TokenType.EQUALS:
                    return self._parse_assignment()

            # Otherwise it's an expression statement: expression ";"
            return self._parse_expression_statement()

        except NestingDepthExceeded:
            # Never recover a depth overflow — let it unwind to the caller.
            raise
        except ParseError as e:
            # Error recovery: skip to next semicolon but stop at block
            # boundary keywords so outer block parsers can still see them.
            error_message = str(e)
            block_boundaries = {
                TokenType.ELSE,
                TokenType.ELSEIF,
                TokenType.ENDIF,
                TokenType.END,
            }

            while (
                not self.at_end()
                and self.current().type != TokenType.SEMICOLON
                and self.current().type not in block_boundaries
            ):
                self.advance()

            # Consume the semicolon if present
            if not self.at_end() and self.current().type == TokenType.SEMICOLON:
                self.advance()
            elif self.pos == start and not self.at_end():
                # Nothing was consumed (e.g. current token is a block
                # boundary).  Consume it to guarantee forward progress
                # and prevent an infinite loop.
                self.advance()

            # Discard whatever the failed parse left behind: a half-built
            # ASSIGNMENT node inside an UNKNOWN_STATEMENT would claim structure
            # the source does not have.  The statement stays a flat span.
            del self._pending[children_before:]
            raw_start, raw_end = self._raw_span(start, self.pos)
            node = CstNode(CstKind.UNKNOWN_STATEMENT, raw_start, raw_end, [])
            self._pending.append(node)

            statement = UnknownStatement(self.tokens[start : self.pos], error_message)
            statement.cst = node
            return statement

    def _parse_assignment(self) -> Assignment:
        """
        Parse an assignment statement.

        Grammar: assignment := IDENTIFIER "=" expression ";"

        Returns:
            An Assignment AST node.

        Raises:
            ParseError: If assignment syntax is invalid.
        """
        with self._span(CstKind.ASSIGNMENT) as span:
            # Check for identifier (regular or predefined)
            if self.at_end() or not self.is_identifier(self.current()):
                got = self._current_token_name_for_error()
                raise ParseError(f"Assignment must start with an identifier, got {got}")

            with self._span(CstKind.IDENTIFIER) as target:
                left_tok = self.advance()
                left = target.attach(Identifier(left_tok.value, left_tok))

            self.expect(TokenType.EQUALS, "Expected '=' in assignment")

            right_expr = self.parse_expression()

            self.expect(TokenType.SEMICOLON, "Expected ';' after assignment")

            return span.attach(Assignment(left, right_expr, token=left_tok))

    def _parse_block_until(self, stop_tokens: set[TokenType]) -> list[Statement]:
        """Parse a statement block until one of ``stop_tokens`` is reached."""
        body: list[Statement] = []
        with self._span(CstKind.BLOCK):
            while not self.at_end() and self.current().type not in stop_tokens:
                stmt = self._parse_one_statement()
                if stmt:
                    body.append(stmt)
        return body

    def _parse_if_else_tail(
        self, endif_token: TokenType
    ) -> tuple[list[Statement], Optional[Token]]:
        """Parse optional ELSEIF/ELSE branch content of an IF chain.

        Returns a ``(else_body, else_token)`` tuple.  ``else_token`` is the
        ELSE keyword token when a (possibly empty) ELSE clause is present,
        otherwise ``None``.
        """
        if not self.at_end() and self.current().type == TokenType.ELSEIF:
            return [self._parse_elseif_branch()], None

        if not self.at_end() and self.current().type == TokenType.ELSE:
            with self._span(CstKind.ELSE_CLAUSE):
                else_tok = self.advance()
                self.expect(TokenType.SEMICOLON, "Expected ';' after ELSE")
                body = self._parse_block_until({endif_token})
            return body, else_tok

        return [], None

    def _parse_if_statement(self) -> IfStatement:
        """
        Parse an IF/ENDIF statement with optional ELSEIF/ELSE branches.

        Grammar:
          if_stmt := IF "(" expression ")" ";" statement*
                     [ELSEIF "(" expression ")" ";" statement*]*
                     [ELSE ";" statement*]
                     ENDIF ";"

        ELSEIF branches are modelled as nested IfStatements in else_body.

        Returns:
            An IfStatement AST node.

        Raises:
            ParseError: If IF statement syntax is invalid.
        """
        with self._span(CstKind.IF_STATEMENT) as span:
            with self._span(CstKind.IF_HEADER):
                if_tok = self.expect(TokenType.IF, "Expected 'IF'")
                self.expect(TokenType.LPAREN, "Expected '(' after IF")

                condition = self.parse_expression()

                self.expect(TokenType.RPAREN, "Expected ')' after IF condition")
                self.expect(TokenType.SEMICOLON, "Expected ';' after IF condition")

            then_body = self._parse_block_until(
                {TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF}
            )
            else_body, else_tok = self._parse_if_else_tail(TokenType.ENDIF)

            self.expect(TokenType.ENDIF, "Expected 'ENDIF' to close IF statement")
            self.expect(TokenType.SEMICOLON, "Expected ';' after ENDIF")

            return span.attach(
                IfStatement(
                    condition, then_body, else_body, token=if_tok, else_token=else_tok
                )
            )

    def _parse_elseif_branch(self) -> IfStatement:
        """
        Parse an ELSEIF branch as a nested IfStatement.

        Grammar:
          elseif := ELSEIF "(" expression ")" ";" statement*
                    [ELSEIF ...]*
                    [ELSE ";" statement*]

        Note: The closing ENDIF is consumed by the outermost _parse_if_statement.

        Returns:
            An IfStatement AST node representing the ELSEIF chain.
        """
        with self._span(CstKind.ELSEIF_CLAUSE) as span:
            with self._span(CstKind.IF_HEADER):
                elseif_tok = self.expect(TokenType.ELSEIF, "Expected 'ELSEIF'")
                self.expect(TokenType.LPAREN, "Expected '(' after ELSEIF")

                condition = self.parse_expression()

                self.expect(TokenType.RPAREN, "Expected ')' after ELSEIF condition")
                self.expect(TokenType.SEMICOLON, "Expected ';' after ELSEIF condition")

            then_body = self._parse_block_until(
                {TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF}
            )
            else_body, else_tok = self._parse_if_else_tail(TokenType.ENDIF)

            return span.attach(
                IfStatement(
                    condition,
                    then_body,
                    else_body,
                    token=elseif_tok,
                    else_token=else_tok,
                )
            )

    def _parse_while_statement(self) -> WhileStatement:
        """
        Parse a WHILE/END statement.

        Grammar:
          while_stmt := WHILE "(" expression ")" ";" statement* END ";"

        Returns:
            A WhileStatement AST node.

        Raises:
            ParseError: If WHILE statement syntax is invalid.
        """
        with self._span(CstKind.WHILE_STATEMENT) as span:
            with self._span(CstKind.WHILE_HEADER):
                while_tok = self.expect(TokenType.WHILE, "Expected 'WHILE'")
                self.expect(TokenType.LPAREN, "Expected '(' after WHILE")

                condition = self.parse_expression()

                self.expect(TokenType.RPAREN, "Expected ')' after WHILE condition")
                self.expect(TokenType.SEMICOLON, "Expected ';' after WHILE condition")

            # Parse statements in the loop body until END
            body = self._parse_block_until({TokenType.END})

            self.expect(TokenType.END, "Expected 'END' to close WHILE statement")
            self.expect(TokenType.SEMICOLON, "Expected ';' after END")

            return span.attach(WhileStatement(condition, body, token=while_tok))

    def _parse_expression_statement(self) -> ExpressionStatement:
        """
        Parse an expression statement.

        Grammar: expr_stmt := expression ";"

        Returns:
            An ExpressionStatement AST node.

        Raises:
            ParseError: If expression statement syntax is invalid.
        """
        with self._span(CstKind.EXPRESSION_STATEMENT) as span:
            expr = self.parse_expression()
            self.expect(TokenType.SEMICOLON, "Expected ';' after expression")
            # In TM1, a bare identifier used as a statement is a no-arg function call.
            if isinstance(expr, Identifier):
                call = FunctionCall(name=expr.name, args=[], token=expr.token)
                # The desugared call has no parentheses of its own, so it keeps
                # the identifier's CST node — the source really is just a name.
                call.cst = expr.cst
                expr = call
            return span.attach(ExpressionStatement(expr))

    def parse_expression(self) -> Expression:
        """
        Parse an expression using Pratt parsing.

        Returns:
            An Expression AST node (Number, String, Identifier, BinaryExpression, FunctionCall, etc.).

        Raises:
            ParseError: If expression is invalid.
        """
        return self._parse_pratt(min_precedence=Precedence.NONE)

    # -----------------------------
    # Pratt parser core
    # -----------------------------
    def _parse_pratt(self, min_precedence: int) -> Expression:
        """
        Core Pratt parsing algorithm for expressions.

        Handles operator precedence and associativity correctly by:
        1. Parsing a prefix/primary expression
        2. While next token is an infix operator with precedence >= min_precedence:
           - Recursively parse the right side with stronger precedence
           - Combine left, operator, and right into a BinaryExpression

        Args:
            min_precedence: Minimum precedence level to consider for infix operators.

        Returns:
            An Expression AST node.

        Raises:
            ParseError: If expression is invalid.
        """
        # Taken before the left operand so a CALL or BINARY_EXPR node can be
        # opened *around* it once we know the operand was only the left side.
        mark = self._checkpoint()
        left = self._parse_prefix()

        while True:
            if self.at_end():
                break

            tok = self.current()

            # function call: IDENTIFIER already handled as primary,
            # but call "()" is parsed as a postfix on IDENTIFIER nodes.
            # We implement call parsing as: if next token is LPAREN and left is Identifier.
            if tok.type == TokenType.LPAREN and isinstance(left, Identifier):
                # call binds very strong; no need to compare with min_precedence unless you add more postfix ops
                with self._span(CstKind.CALL, mark) as span:
                    left = span.attach(self._parse_call(left))
                continue

            prec = INFIX_PRECEDENCE.get(tok.type)
            if prec is None or prec < min_precedence:
                break

            with self._span(CstKind.BINARY_EXPR, mark) as span:
                op_tok = self.advance()  # consume operator

                # left-associative operators: parse RHS with prec+1
                rhs = self._parse_pratt(min_precedence=prec + 1)

                left = span.attach(
                    BinaryExpression(left=left, operator=op_tok, right=rhs)
                )

        return left

    def _parse_prefix(self) -> Expression:
        """
        Parse prefix and primary expressions.

        Handles:
        - Numeric literals (NUMBER)
        - String literals (STRING)
        - Identifiers (IDENTIFIER)
        - Parenthesized expressions (LPAREN ... RPAREN)
        - Unary operators (+, -, ~)

        Returns:
            An Expression AST node (Number, String, Identifier, or UnaryExpression for unary).

        Raises:
            ParseError: If token is not a valid primary expression.
        """
        tok = self.current()

        # Parenthesized expression.  The AST discards the parentheses and keeps
        # only the inner expression; the CST keeps them as a PAREN_GROUP so a
        # formatter can still see (and break inside) them.
        if tok.type == TokenType.LPAREN:
            with self._span(CstKind.PAREN_GROUP):
                self.advance()
                expr = self.parse_expression()
                self.expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        # Number literal
        if tok.type == TokenType.NUMBER:
            with self._span(CstKind.NUMBER) as span:
                self.advance()
                # TM1 has no integer type; all numbers are IEEE-754 doubles.
                return span.attach(Number(float(tok.value), token=tok))

        # String literal
        if tok.type == TokenType.STRING:
            with self._span(CstKind.STRING) as span:
                self.advance()
                return span.attach(String(tok.value, token=tok))

        # Inline `If(cond, then, else)` expression function. TI overloads `If`:
        # the statement form (IF ... ENDIF) is intercepted by the statement
        # dispatcher before expression parsing, so an IF token reaching here is
        # always the function form. Treat it as the callee name — the Pratt
        # loop parses the argument list via _parse_call, yielding a FunctionCall.
        next_tok = self.peek()
        if tok.type == TokenType.IF and next_tok and next_tok.type == TokenType.LPAREN:
            with self._span(CstKind.IDENTIFIER) as span:
                self.advance()
                return span.attach(Identifier(tok.value, tok))

        # Identifier (variable, function name, or predefined variable)
        if self.is_identifier(tok):
            with self._span(CstKind.IDENTIFIER) as span:
                tok_copy = tok  # Save token before advancing
                self.advance()
                # If immediately followed by '(' it becomes a call in _parse_pratt loop
                return span.attach(Identifier(tok_copy.value, tok_copy))

        # Optional unary +/-
        if tok.type in (TokenType.PLUS, TokenType.MINUS):
            with self._span(CstKind.UNARY_EXPR) as span:
                op = self.advance()
                right = self._parse_pratt(min_precedence=Precedence.PREFIX)
                return span.attach(UnaryExpression(operator=op, operand=right))

        # Logical NOT (~)
        if tok.type == TokenType.NOT:
            with self._span(CstKind.UNARY_EXPR) as span:
                op = self.advance()
                right = self._parse_pratt(min_precedence=Precedence.PREFIX)
                return span.attach(UnaryExpression(operator=op, operand=right))

        raise ParseError(
            f"Unexpected token in expression: {tok.type.name} ({tok.value!r})"
        )

    def _parse_call(self, ident: Identifier) -> FunctionCall:
        """
        Parse a function call expression.

        Grammar: call := IDENTIFIER "(" [expr ("," expr)*] ")"

        Args:
            ident: An Identifier node representing the function name.

        Returns:
            A FunctionCall AST node with the function name and arguments.

        Raises:
            ParseError: If function call syntax is invalid.
        """
        args: List[Expression] = []

        # ARG_LIST spans '(' through ')' — the unit a line-breaking formatter
        # rewraps, and the only place commas survive.
        with self._span(CstKind.ARG_LIST):
            self.expect(TokenType.LPAREN)

            # empty args: "()"
            if self.match(TokenType.RPAREN):
                return FunctionCall(name=ident.name, args=args, token=ident.token)

            # Some cell-address functions accept a `hierarchy:element` reference in
            # their element arguments — every argument after the leading cube name.
            allow_element_ref = ident.name.lower() in ELEMENT_REF_FUNCTIONS

            # one or more args
            while True:
                # ARGUMENT wraps the expression rather than carrying it: the
                # expression keeps its own ``cst``, and the wrapper marks the
                # comma-delimited slot a formatter may break at.
                with self._span(CstKind.ARGUMENT):
                    mark = self._checkpoint()
                    arg = self.parse_expression()
                    # Only the 2nd..n argument may carry the colon reference; a
                    # non-empty ``args`` means at least the cube name is already parsed.
                    if allow_element_ref and args:
                        arg = self._maybe_element_reference(arg, mark)
                args.append(arg)

                if self.match(TokenType.COMMA):
                    continue

                self.expect(TokenType.RPAREN, "Expected ')' after function arguments")
                break

        return FunctionCall(name=ident.name, args=args, token=ident.token)

    def _maybe_element_reference(
        self, left: Expression, mark: _Checkpoint
    ) -> Expression:
        """Fold a trailing ``:element`` onto *left* as a hierarchy:element ref.

        TI addresses an element within an explicit hierarchy as
        ``hierarchy:element`` (e.g. ``pTgtHier:vEle``).  COLON is deliberately
        not a general infix operator, so it is only recognised here, in the
        element arguments of the cell-address functions that accept it.  The
        reference is represented as a ``BinaryExpression`` over the COLON token
        so existing expression walks traverse both sides unchanged.
        """
        if self.at_end() or self.current().type != TokenType.COLON:
            return left
        with self._span(CstKind.ELEMENT_REF, mark) as span:
            colon = self.advance()
            right = self.parse_expression()
            return span.attach(BinaryExpression(left=left, operator=colon, right=right))
