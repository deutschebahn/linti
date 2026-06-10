from linti.lexer.token import Token, TokenType
from linti.lexer.token_window import TokenWindow


def test_tokenwindow_previous_next_boundaries():
    tokens = [
        Token(TokenType.IDENTIFIER, "a", 0, 1, 1),
        Token(TokenType.EQUALS, "=", 1, 1, 1),
        Token(TokenType.NUMBER, "1", 2, 1, 1),
    ]

    window = TokenWindow(tokens)

    # index defaults to 0
    assert window.previous() is None
    assert window.previous(offset=2) is None
    assert window.next() == tokens[1]
    assert window.next(offset=2) == tokens[2]
    assert window.next(offset=3) is None

    window.set_index(1)
    assert window.previous() == tokens[0]
    assert window.next() == tokens[2]

    window.set_index(2)
    assert window.next() is None
    assert window.previous() == tokens[1]


def test_previous_non_ws_scans_without_fixed_limit():
    tokens = [Token(TokenType.IDENTIFIER, "a", 0, 1, 1)]
    tokens.extend(Token(TokenType.WHITESPACE, " ", i + 1, 1, 1) for i in range(30))
    tokens.append(Token(TokenType.PLUS, "+", 31, 1, 1))

    window = TokenWindow(tokens)
    window.set_index(len(tokens) - 1)

    assert window.previous_non_ws() == tokens[0]
