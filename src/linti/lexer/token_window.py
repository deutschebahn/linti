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

    def _find_neighbor(self, step, skip):
        offset = 1
        while True:
            tok = step(offset)
            if tok is None:
                return None
            if tok.type not in skip:
                return tok
            offset += 1

    def previous_non_ws(self):
        """Return the closest previous non-WHITESPACE token, or ``None``."""
        from linti.lexer.token import (
            TokenType,  # local import to avoid circularity
        )

        return self._find_neighbor(self.previous, {TokenType.WHITESPACE})

    def next_non_ws(self):
        """Return the closest following non-WHITESPACE/NEWLINE token, or ``None``."""
        from linti.lexer.token import (
            TokenType,  # local import to avoid circularity
        )

        return self._find_neighbor(self.next, {TokenType.WHITESPACE, TokenType.NEWLINE})
