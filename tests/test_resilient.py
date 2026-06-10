"""Tests for parser error recovery on unknown statements."""

from linti.lexer.lexer import Lexer
from linti.parser.ast import Assignment, ExpressionStatement, UnknownStatement
from linti.parser.parser import Parser


def test_parser_recovers_from_unknown_statement():
    """Parser recovers from an unknown keyword and continues parsing."""
    code = "nVar = 1;\nUNKNOWN_KEYWORD async process;\nsVar = 'test';\n"

    tokens = Lexer(code).tokenize()
    program = Parser(tokens).parse()

    assert len(program.statements) == 3
    assert isinstance(program.statements[0], Assignment)
    assert isinstance(program.statements[1], UnknownStatement)
    assert isinstance(program.statements[2], Assignment)


def test_unknown_statement_captures_error_message():
    """UnknownStatement stores the parse error message."""
    code = "UNKNOWN_KEYWORD async process;\n"

    tokens = Lexer(code).tokenize()
    program = Parser(tokens).parse()

    assert len(program.statements) == 1
    stmt = program.statements[0]
    assert isinstance(stmt, UnknownStatement)
    assert stmt.error_message != ""


def test_recovery_preserves_surrounding_statements():
    """Statements before and after an error are parsed correctly."""
    code = "nA = 1;\n= broken;\nnB = 2;\nFunc();\n"

    tokens = Lexer(code).tokenize()
    program = Parser(tokens).parse()

    assignments = [s for s in program.statements if isinstance(s, Assignment)]
    unknowns = [s for s in program.statements if isinstance(s, UnknownStatement)]
    expressions = [s for s in program.statements if isinstance(s, ExpressionStatement)]

    assert len(assignments) == 2
    assert len(unknowns) >= 1
    assert len(expressions) == 1
