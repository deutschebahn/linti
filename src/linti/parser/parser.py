from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

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


IGNORED_FOR_PARSING = {TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT}


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

    def __init__(self, tokens: Sequence[Token], ignore_whitespace: bool = True):
        """
        Initialize the parser with a sequence of tokens.

        Args:
            tokens: Sequence of Token objects to parse.
            ignore_whitespace: If True, filters out WHITESPACE and NEWLINE tokens.
                              Default is True.
        """
        if ignore_whitespace:
            self.tokens = [t for t in tokens if t.type not in IGNORED_FOR_PARSING]
        else:
            self.tokens = list(tokens)

        self.pos = 0

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

        while not self.at_end():
            stmt = self._parse_one_statement()
            if stmt:
                statements.append(stmt)

        return Program(statements)

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

        except ParseError as e:
            # Error recovery: skip to next semicolon but stop at block
            # boundary keywords so outer block parsers can still see them.
            error_message = str(e)
            unknown_tokens = []
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
                unknown_tokens.append(self.current())
                self.advance()

            # Consume the semicolon if present
            if not self.at_end() and self.current().type == TokenType.SEMICOLON:
                unknown_tokens.append(self.current())
                self.advance()
            elif not unknown_tokens and not self.at_end():
                # Nothing was consumed (e.g. current token is a block
                # boundary).  Consume it to guarantee forward progress
                # and prevent an infinite loop.
                unknown_tokens.append(self.current())
                self.advance()

            return UnknownStatement(unknown_tokens, error_message)

    def _parse_assignment(self) -> Assignment:
        """
        Parse an assignment statement.

        Grammar: assignment := IDENTIFIER "=" expression ";"

        Returns:
            An Assignment AST node.

        Raises:
            ParseError: If assignment syntax is invalid.
        """
        # Check for identifier (regular or predefined)
        if self.at_end() or not self.is_identifier(self.current()):
            got = self._current_token_name_for_error()
            raise ParseError(f"Assignment must start with an identifier, got {got}")
        left_tok = self.advance()

        self.expect(TokenType.EQUALS, "Expected '=' in assignment")

        right_expr = self.parse_expression()

        self.expect(TokenType.SEMICOLON, "Expected ';' after assignment")

        return Assignment(
            Identifier(left_tok.value, left_tok), right_expr, token=left_tok
        )

    def _parse_block_until(self, stop_tokens: set[TokenType]) -> list[Statement]:
        """Parse a statement block until one of ``stop_tokens`` is reached."""
        body: list[Statement] = []
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
            else_tok = self.advance()
            self.expect(TokenType.SEMICOLON, "Expected ';' after ELSE")
            return self._parse_block_until({endif_token}), else_tok

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

        return IfStatement(
            condition, then_body, else_body, token=if_tok, else_token=else_tok
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
        elseif_tok = self.expect(TokenType.ELSEIF, "Expected 'ELSEIF'")
        self.expect(TokenType.LPAREN, "Expected '(' after ELSEIF")

        condition = self.parse_expression()

        self.expect(TokenType.RPAREN, "Expected ')' after ELSEIF condition")
        self.expect(TokenType.SEMICOLON, "Expected ';' after ELSEIF condition")

        then_body = self._parse_block_until(
            {TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF}
        )
        else_body, else_tok = self._parse_if_else_tail(TokenType.ENDIF)

        return IfStatement(
            condition, then_body, else_body, token=elseif_tok, else_token=else_tok
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
        while_tok = self.expect(TokenType.WHILE, "Expected 'WHILE'")
        self.expect(TokenType.LPAREN, "Expected '(' after WHILE")

        condition = self.parse_expression()

        self.expect(TokenType.RPAREN, "Expected ')' after WHILE condition")
        self.expect(TokenType.SEMICOLON, "Expected ';' after WHILE condition")

        # Parse statements in the loop body until END
        body = []
        while not self.at_end():
            if self.current().type == TokenType.END:
                break
            stmt = self._parse_one_statement()
            if stmt:
                body.append(stmt)

        self.expect(TokenType.END, "Expected 'END' to close WHILE statement")
        self.expect(TokenType.SEMICOLON, "Expected ';' after END")

        return WhileStatement(condition, body, token=while_tok)

    def _parse_expression_statement(self) -> ExpressionStatement:
        """
        Parse an expression statement.

        Grammar: expr_stmt := expression ";"

        Returns:
            An ExpressionStatement AST node.

        Raises:
            ParseError: If expression statement syntax is invalid.
        """
        expr = self.parse_expression()
        self.expect(TokenType.SEMICOLON, "Expected ';' after expression")
        # In TM1, a bare identifier used as a statement is a no-arg function call.
        if isinstance(expr, Identifier):
            expr = FunctionCall(name=expr.name, args=[], token=expr.token)
        return ExpressionStatement(expr)

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
                left = self._parse_call(left)
                continue

            prec = INFIX_PRECEDENCE.get(tok.type)
            if prec is None or prec < min_precedence:
                break

            op_tok = self.advance()  # consume operator

            # left-associative operators: parse RHS with prec+1
            rhs = self._parse_pratt(min_precedence=prec + 1)

            left = BinaryExpression(left=left, operator=op_tok, right=rhs)

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

        # Parenthesized expression
        if tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        # Number literal
        if tok.type == TokenType.NUMBER:
            self.advance()
            # TM1 has no integer type; all numbers are IEEE-754 doubles.
            return Number(float(tok.value), token=tok)

        # String literal
        if tok.type == TokenType.STRING:
            self.advance()
            return String(tok.value, token=tok)

        # Identifier (variable, function name, or predefined variable)
        if self.is_identifier(tok):
            tok_copy = tok  # Save token before advancing
            self.advance()
            ident = Identifier(tok_copy.value, tok_copy)

            # If immediately followed by '(' it becomes a call in _parse_pratt loop
            return ident

        # Optional unary +/-
        if tok.type in (TokenType.PLUS, TokenType.MINUS):
            op = self.advance()
            right = self._parse_pratt(min_precedence=Precedence.PREFIX)
            return UnaryExpression(operator=op, operand=right)

        # Logical NOT (~)
        if tok.type == TokenType.NOT:
            op = self.advance()
            right = self._parse_pratt(min_precedence=Precedence.PREFIX)
            return UnaryExpression(operator=op, operand=right)

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
        self.expect(TokenType.LPAREN)

        args: List[Expression] = []

        # empty args: "()"
        if self.match(TokenType.RPAREN):
            return FunctionCall(name=ident.name, args=args, token=ident.token)

        # one or more args
        while True:
            args.append(self.parse_expression())

            if self.match(TokenType.COMMA):
                continue

            self.expect(TokenType.RPAREN, "Expected ')' after function arguments")
            break

        return FunctionCall(name=ident.name, args=args, token=ident.token)
