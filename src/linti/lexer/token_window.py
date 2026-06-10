class TokenWindow:

    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0

    def set_index(self, index):
        self.index = index

    def previous(self, offset=1):
        i = self.index - offset
        return self.tokens[i] if i >= 0 else None

    def next(self, offset=1):
        i = self.index + offset
        return self.tokens[i] if i < len(self.tokens) else None

    def previous_non_ws(self):
        """Return the closest previous non-WHITESPACE token, or ``None``."""
        from linti.lexer.token import (
            TokenType,  # local import to avoid circularity
        )

        offset = 1
        while True:
            tok = self.previous(offset)
            if tok is None:
                return None
            if tok.type != TokenType.WHITESPACE:
                return tok
            offset += 1
