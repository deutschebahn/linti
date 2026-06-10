from linti.lexer.token import Token, TokenType
from linti.parser.ast import Identifier, Number, UnaryExpression
from linti.semantic.type_inference import infer_type


def _op_token(token_type: TokenType, value: str) -> Token:
    return Token(token_type, value, 0, 1, 1)


def test_infer_type_unary_minus_number_is_numeric():
    expr = UnaryExpression(_op_token(TokenType.MINUS, "-"), Number(5))

    assert infer_type(expr) == "number"


def test_infer_type_unary_plus_identifier_is_numeric():
    expr = UnaryExpression(_op_token(TokenType.PLUS, "+"), Identifier("x"))

    assert infer_type(expr) == "number"


def test_infer_type_unary_not_is_numeric():
    expr = UnaryExpression(_op_token(TokenType.NOT, "~"), Identifier("x"))

    assert infer_type(expr) == "number"
