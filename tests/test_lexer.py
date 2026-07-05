import pytest

from linti.lexer.lexer import Lexer
from linti.lexer.token import TokenType


def _simplify(tokens):
    return [(t.type, t.value, t.position) for t in tokens]


def _simplify_loc(tokens):
    return [(t.type, t.value, t.position, t.line, t.column) for t in tokens]


@pytest.mark.parametrize("input_offset, expected_char", [(1, "=")])
def test_peek(input_offset, expected_char):
    lexer = Lexer("a=1;")
    char = lexer.peek(input_offset)
    assert char == expected_char


def test_tokenize_assignment_no_spaces():
    lexer = Lexer("a=1;")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "a", 0),
        (TokenType.EQUALS, "=", 1),
        (TokenType.NUMBER, "1", 2),
        (TokenType.SEMICOLON, ";", 3),
    ]


def test_tokenize_assignment_with_spaces_includes_whitespace_tokens():
    lexer = Lexer("a = 1;")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "a", 0),
        (TokenType.WHITESPACE, " ", 1),
        (TokenType.EQUALS, "=", 2),
        (TokenType.WHITESPACE, " ", 3),
        (TokenType.NUMBER, "1", 4),
        (TokenType.SEMICOLON, ";", 5),
    ]


def test_tokenize_assignment_with_spaces_includes_double_whitespace_tokens():
    lexer = Lexer("a  = 1;")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "a", 0),
        (TokenType.WHITESPACE, "  ", 1),
        (TokenType.EQUALS, "=", 3),
        (TokenType.WHITESPACE, " ", 4),
        (TokenType.NUMBER, "1", 5),
        (TokenType.SEMICOLON, ";", 6),
    ]


def test_unexpected_character_raises():
    lexer = Lexer("@")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [(TokenType.UNKNOWN, "@", 0)]


def test_tokenize_newline_emits_newline_token_with_location():
    lexer = Lexer("a\nb")
    tokens = lexer.tokenize()

    assert _simplify_loc(tokens) == [
        (TokenType.IDENTIFIER, "a", 0, 1, 1),
        (TokenType.NEWLINE, "\n", 1, 1, 2),
        (TokenType.IDENTIFIER, "b", 2, 2, 1),
    ]


def test_tokenize_space_before_newline_does_not_swallow_newline():
    lexer = Lexer("a \nb")
    tokens = lexer.tokenize()

    assert _simplify_loc(tokens) == [
        (TokenType.IDENTIFIER, "a", 0, 1, 1),
        (TokenType.WHITESPACE, " ", 1, 1, 2),
        (TokenType.NEWLINE, "\n", 2, 1, 3),
        (TokenType.IDENTIFIER, "b", 3, 2, 1),
    ]


@pytest.mark.parametrize(
    "text, expected_value, should_raise",
    [
        ("'abc'", "abc", False),
        ("'O''Brien'", "O'Brien", False),
        ("'a\nb'", "a\nb", False),
        ("'abc", None, True),
    ],
)
def test_string_method(text, expected_value, should_raise):
    lexer = Lexer(text)

    if should_raise:
        with pytest.raises(ValueError):
            lexer.string()
        return

    token = lexer.string()
    assert token.type == TokenType.STRING
    assert token.value == expected_value


@pytest.mark.parametrize(
    "text, expected_value",
    [
        ("123.45", "123.45"),
        ("0.5", "0.5"),
    ],
)
def test_tokenize_decimal_number(text, expected_value):
    lexer = Lexer(text)
    tokens = [t for t in lexer.tokenize() if t.type == TokenType.NUMBER]

    assert len(tokens) == 1
    assert tokens[0].value == expected_value


def test_tokenize_number_trailing_dot_not_consumed():
    lexer = Lexer("123.")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.NUMBER, "123", 0),
        (TokenType.UNKNOWN, ".", 3),
    ]


def test_tokenize_parentheses_tokens():
    lexer = Lexer("()")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.LPAREN, "(", 0),
        (TokenType.RPAREN, ")", 1),
    ]


def test_tokenize_comment_at_start_of_line():
    lexer = Lexer("# hello\n")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.COMMENT, "# hello", 0),
        (TokenType.NEWLINE, "\n", 7),
    ]


def test_tokenize_comment_after_leading_whitespace():
    lexer = Lexer("   # hello\n")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.WHITESPACE, "   ", 0),
        (TokenType.COMMENT, "# hello", 3),
        (TokenType.NEWLINE, "\n", 10),
    ]


def test_tokenize_comment_only_after_semicolon_inline():
    lexer = Lexer("a=1; # c\nb")
    tokens = lexer.tokenize()

    assert [t.type for t in tokens] == [
        TokenType.IDENTIFIER,
        TokenType.EQUALS,
        TokenType.NUMBER,
        TokenType.SEMICOLON,
        TokenType.WHITESPACE,
        TokenType.COMMENT,
        TokenType.NEWLINE,
        TokenType.IDENTIFIER,
    ]
    assert tokens[5].value == "# c"


def test_tokenize_hash_is_not_comment_mid_statement():
    lexer = Lexer("a # c")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "a", 0),
        (TokenType.WHITESPACE, " ", 1),
        (TokenType.UNKNOWN, "#", 2),
        (TokenType.WHITESPACE, " ", 3),
        (TokenType.IDENTIFIER, "c", 4),
    ]


@pytest.mark.parametrize(
    "op_text, token_type_name, expected_value",
    [
        ("+", "PLUS", "+"),
        ("-", "MINUS", "-"),
        ("*", "STAR", "*"),
        ("/", "SLASH", "/"),
        ("@=", "STRING_EQUALS", "@="),
        ("@<>", "STRING_NOT_EQUAL", "@<>"),
    ],
)
def test_tokenize_operator_tokens(op_text, token_type_name, expected_value):
    if not hasattr(TokenType, token_type_name):
        pytest.skip(f"TokenType.{token_type_name} not defined in this project")

    tokens = Lexer(op_text).tokenize()
    assert len(tokens) == 1

    tok = tokens[0]
    assert tok.type == getattr(TokenType, token_type_name)
    assert tok.value == expected_value
    assert tok.position == 0


@pytest.mark.parametrize(
    "expr, operator_type_name",
    [
        ("a+b", "PLUS"),
        ("a-b", "MINUS"),
        ("a*b", "STAR"),
        ("a/b", "SLASH"),
    ],
)
def test_tokenize_operator_in_expression(expr, operator_type_name):
    if not hasattr(TokenType, operator_type_name):
        pytest.skip(f"TokenType.{operator_type_name} not defined in this project")

    tokens = Lexer(expr).tokenize()
    assert [t.type for t in tokens] == [
        TokenType.IDENTIFIER,
        getattr(TokenType, operator_type_name),
        TokenType.IDENTIFIER,
    ]


def test_tokenize_string_comparison_operator():
    """Test that @= is tokenized as STRING_EQUALS for string comparison."""
    lexer = Lexer("sName @= 'test'")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "sName", 0),
        (TokenType.WHITESPACE, " ", 5),
        (TokenType.STRING_EQUALS, "@=", 6),
        (TokenType.WHITESPACE, " ", 8),
        (TokenType.STRING, "test", 9),
    ]


def test_tokenize_string_comparison_in_if_condition():
    """Test that @= works correctly in IF conditions."""
    lexer = Lexer("IF (sName @= 'John');")
    tokens = lexer.tokenize()

    assert [t.type for t in tokens if t.type != TokenType.WHITESPACE] == [
        TokenType.IF,
        TokenType.LPAREN,
        TokenType.IDENTIFIER,
        TokenType.STRING_EQUALS,
        TokenType.STRING,
        TokenType.RPAREN,
        TokenType.SEMICOLON,
    ]


def test_tokenize_string_not_equal_operator():
    """Test that @<> is tokenized as STRING_NOT_EQUAL for string not equal comparison."""
    lexer = Lexer("sName @<> 'test'")
    tokens = lexer.tokenize()

    assert _simplify(tokens) == [
        (TokenType.IDENTIFIER, "sName", 0),
        (TokenType.WHITESPACE, " ", 5),
        (TokenType.STRING_NOT_EQUAL, "@<>", 6),
        (TokenType.WHITESPACE, " ", 9),
        (TokenType.STRING, "test", 10),
    ]


def test_tokenize_string_not_equal_in_if_condition():
    """Test that @<> works correctly in IF conditions."""
    lexer = Lexer("IF (sName @<> 'John');")
    tokens = lexer.tokenize()

    assert [t.type for t in tokens if t.type != TokenType.WHITESPACE] == [
        TokenType.IF,
        TokenType.LPAREN,
        TokenType.IDENTIFIER,
        TokenType.STRING_NOT_EQUAL,
        TokenType.STRING,
        TokenType.RPAREN,
        TokenType.SEMICOLON,
    ]
