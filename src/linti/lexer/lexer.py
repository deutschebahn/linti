from linti.lexer.token import (
    KEYWORDS,
    OPERATORS,
    TM1_PREDEFINED_VARIABLES_UPPER,
    Token,
    TokenType,
)

EOF_CHAR = "\0"


class Lexer:
    def __init__(self, text: str):
        self.text = text
        self.position = 0
        self.line = 1
        self.column = 1
        self.current_char = text[0] if text else EOF_CHAR

    def advance(self):
        if self.current_char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1

        self.position += 1
        if self.position < len(self.text):
            self.current_char = self.text[self.position]
        else:
            self.current_char = EOF_CHAR

    def peek(self, offset: int = 1):
        pos = self.position + offset
        if pos >= len(self.text):
            return "\0"
        return self.text[self.position + offset]

    def simple_token(self, token_type):
        start_pos = self.position
        line = self.line
        column = self.column
        value = self.current_char

        self.advance()

        return Token(token_type, value, start_pos, line, column)

    def whitespace(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        while (
            self.current_char != EOF_CHAR
            and self.current_char != "\n"
            and self.current_char.isspace()
        ):
            chars.append(self.current_char)
            self.advance()

        return Token(TokenType.WHITESPACE, "".join(chars), start_pos, line, column)

    def newline(self):
        start_pos = self.position
        line = self.line
        column = self.column

        self.advance()

        return Token(TokenType.NEWLINE, "\n", start_pos, line, column)

    def identifier(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        while self.current_char != EOF_CHAR and (
            self.current_char.isalnum() or self.current_char == "_"
        ):
            chars.append(self.current_char)
            self.advance()

        result = "".join(chars)

        # Check for keywords (case-insensitive)
        upper = result.upper()
        if upper in KEYWORDS:
            token_type = KEYWORDS[upper]
        # Check for predefined variables (case-insensitive)
        elif result.upper() in TM1_PREDEFINED_VARIABLES_UPPER:
            token_type = TokenType.PREDEFINED_IDENTIFIER
        else:
            token_type = TokenType.IDENTIFIER

        return Token(token_type, result, start_pos, line, column)

    def operator(self):
        start_pos = self.position
        line = self.line
        column = self.column

        # Try longest match first (3 characters, then 2, then 1)
        three_char = self.current_char + self.peek(1) + self.peek(2)

        if three_char in OPERATORS:
            self.advance()
            self.advance()
            self.advance()
            token_type = OPERATORS[three_char]
            return Token(token_type, three_char, start_pos, line, column)

        # Try 2 characters
        two_char = self.current_char + self.peek()

        if two_char in OPERATORS:
            self.advance()
            self.advance()
            token_type = OPERATORS[two_char]
            return Token(token_type, two_char, start_pos, line, column)

        # Fallback to single character
        one_char = self.current_char

        if one_char in OPERATORS:
            self.advance()
            token_type = OPERATORS[one_char]
            return Token(token_type, one_char, start_pos, line, column)

    def unknown(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        while self.current_char != EOF_CHAR and not self.current_char.isspace():
            chars.append(self.current_char)
            self.advance()

        return Token(TokenType.UNKNOWN, "".join(chars), start_pos, line, column)

    def string(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        self.advance()

        while True:
            char = self.current_char

            if char == "\0":
                raise ValueError("Unterminated string literal")

            if char == "\n":
                chars.append(char)
                self.advance()
                continue

            if char == "'":
                if self.peek() == "'":
                    chars.append("'")
                    self.advance()  # first '
                    self.advance()  # second '
                    continue
                else:
                    break  # end of string

            chars.append(char)
            self.advance()

        self.advance()  # skip closing quote

        return Token(TokenType.STRING, "".join(chars), start_pos, line, column)

    def number(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        while self.current_char != EOF_CHAR and self.current_char.isdigit():
            chars.append(self.current_char)
            self.advance()

        return Token(TokenType.NUMBER, "".join(chars), start_pos, line, column)

    def comment(self):
        start_pos = self.position
        line = self.line
        column = self.column

        chars: list[str] = []

        while self.current_char != EOF_CHAR and self.current_char != "\n":
            chars.append(self.current_char)
            self.advance()

        return Token(TokenType.COMMENT, "".join(chars), start_pos, line, column)

    def tokenize(self):
        tokens = []
        last_non_ws_type = None

        while self.current_char != EOF_CHAR:

            if self.current_char == "\n":
                tok = self.newline()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char.isspace():
                tokens.append(self.whitespace())
                continue

            if self.current_char == "(":
                tok = self.simple_token(TokenType.LPAREN)
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char == ")":
                tok = self.simple_token(TokenType.RPAREN)
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char.isalpha() or self.current_char == "_":
                tok = self.identifier()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char.isdigit():
                tok = self.number()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char == "=":
                tok = Token(
                    TokenType.EQUALS, "=", self.position, self.line, self.column
                )
                tokens.append(tok)
                last_non_ws_type = tok.type
                self.advance()
                continue

            if self.current_char == ";":
                tok = Token(
                    TokenType.SEMICOLON, ";", self.position, self.line, self.column
                )
                tokens.append(tok)
                last_non_ws_type = tok.type
                self.advance()
                continue

            if self.current_char == ",":
                tok = Token(TokenType.COMMA, ",", self.position, self.line, self.column)
                tokens.append(tok)
                last_non_ws_type = tok.type
                self.advance()
                continue

            if self.current_char == "'":
                tok = self.string()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char == "#" and (
                last_non_ws_type is None
                or last_non_ws_type == TokenType.NEWLINE
                or last_non_ws_type == TokenType.SEMICOLON
            ):
                tok = self.comment()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            if self.current_char == "@":
                # @ is only valid as part of @= or @<> operators
                next_char = self.peek()
                if next_char == "=":
                    tok = self.operator()
                    tokens.append(tok)
                    last_non_ws_type = tok.type
                elif next_char == "<" and self.peek(2) == ">":
                    tok = self.operator()
                    tokens.append(tok)
                    last_non_ws_type = tok.type
                else:
                    tok = self.unknown()
                    tokens.append(tok)
                    last_non_ws_type = tok.type
                continue

            if self.current_char in "+-*/=<>&%|~":
                tok = self.operator()
                tokens.append(tok)
                last_non_ws_type = tok.type
                continue

            tok = self.unknown()
            tokens.append(tok)
            last_non_ws_type = tok.type

        return tokens
