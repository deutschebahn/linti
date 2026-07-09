"""Tests for the `hierarchy:element` reference syntax in cell-address args.

TI addresses an element within an explicit hierarchy as ``hierarchy:element``
(e.g. ``pTgtHier:vEle``). It is accepted only in the element arguments (every
argument after the leading cube name) of the cell-address functions that
support it — currently ``CellIsUpdateable``.
"""

from linti.lexer.lexer import Lexer
from linti.lexer.token import TokenType
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    FunctionCall,
    Identifier,
    IfStatement,
    UnknownStatement,
)
from linti.parser.parser import Parser


def _parse(code: str):
    return Parser(Lexer(code).tokenize()).parse()


def _first(code: str):
    return _parse(code).statements[0]


def test_colon_lexes_as_its_own_token():
    types = [t.type for t in Lexer("pHier:vEle").tokenize()]
    assert types == [TokenType.IDENTIFIER, TokenType.COLON, TokenType.IDENTIFIER]


def test_element_reference_in_second_argument():
    stmt = _first("nOk = CellIsUpdateable('cube', pTgtHier:vEle, sAttrName);")
    assert isinstance(stmt, Assignment)
    call = stmt.right
    assert isinstance(call, FunctionCall) and call.name == "CellIsUpdateable"
    assert len(call.args) == 3

    ref = call.args[1]
    assert isinstance(ref, BinaryExpression)
    assert ref.operator.type is TokenType.COLON
    assert isinstance(ref.left, Identifier) and ref.left.name == "pTgtHier"
    assert isinstance(ref.right, Identifier) and ref.right.name == "vEle"
    # Other arguments are untouched.
    assert isinstance(call.args[2], Identifier)


def test_element_reference_allowed_in_any_argument_after_the_first():
    call = _first("nOk = CellIsUpdateable('c', a:b, x, c:d);").right
    assert isinstance(call.args[1], BinaryExpression)
    assert isinstance(call.args[2], Identifier)
    assert isinstance(call.args[3], BinaryExpression)


def test_element_reference_inside_if_condition():
    code = (
        "If( CellIsUpdateable( '}ElementAttributes_' | pTgtDim, "
        "pTgtHier:vEle, sAttrName ) = 1 );\n  x = 1;\nENDIF;"
    )
    stmt = _first(code)
    assert isinstance(stmt, IfStatement)
    call = stmt.condition.left
    assert isinstance(call, FunctionCall) and call.name == "CellIsUpdateable"
    assert isinstance(call.args[1], BinaryExpression)
    assert call.args[1].operator.type is TokenType.COLON


def test_element_part_may_be_a_concatenation():
    call = _first("nOk = CellIsUpdateable('c', pHier:('E' | pSuffix));").right
    ref = call.args[1]
    assert isinstance(ref, BinaryExpression)
    assert ref.operator.type is TokenType.COLON
    assert isinstance(ref.right, BinaryExpression)  # the concatenation


def test_colon_not_allowed_in_first_argument():
    # The leading cube name cannot carry a colon reference.
    assert isinstance(
        _first("nOk = CellIsUpdateable(pCube:vBad, e);"), UnknownStatement
    )


def test_colon_not_allowed_in_other_functions():
    # Only functions in ELEMENT_REF_FUNCTIONS accept the syntax.
    assert isinstance(_first("nOk = CellGetN('cube', pHier:vEle);"), UnknownStatement)


def test_plain_cellisupdateable_without_colon_still_parses():
    call = _first("nOk = CellIsUpdateable('cube', 'EMEA', 'Sales');").right
    assert isinstance(call, FunctionCall)
    assert all(not isinstance(a, BinaryExpression) for a in call.args)
