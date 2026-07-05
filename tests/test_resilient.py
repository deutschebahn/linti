"""Tests for parser error recovery on unknown statements."""

import pytest

from linti.lexer.lexer import Lexer
from linti.parser.ast import Assignment, ExpressionStatement, UnknownStatement
from linti.parser.parser import NestingDepthExceeded, Parser


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


def test_deep_nesting_raises_instead_of_recursion_error():
    """Nesting past the cap raises NestingDepthExceeded, not RecursionError."""
    code = "IF(1);" * 300 + "nX = 1;\n" + "ENDIF;" * 300

    tokens = Lexer(code).tokenize()
    with pytest.raises(NestingDepthExceeded):
        Parser(tokens, max_nesting_depth=150).parse()


def test_deep_nesting_boundary_low_cap():
    """Overflow triggers just above the cap; legal depth still parses."""
    # Four nested IFs: depth 4 is under a cap of 5, so this parses cleanly.
    ok_code = "IF(1);" * 4 + "nX = 1;\n" + "ENDIF;" * 4
    program = Parser(Lexer(ok_code).tokenize(), max_nesting_depth=5).parse()
    assert len(program.statements) == 1

    # Six nested IFs exceed a cap of 5.
    deep_code = "IF(1);" * 6 + "nX = 1;\n" + "ENDIF;" * 6
    with pytest.raises(NestingDepthExceeded):
        Parser(Lexer(deep_code).tokenize(), max_nesting_depth=5).parse()


def test_deep_while_nesting_raises():
    """WHILE nesting is guarded the same way as IF."""
    code = "WHILE(1);" * 50 + "nX = 1;\n" + "END;" * 50
    with pytest.raises(NestingDepthExceeded):
        Parser(Lexer(code).tokenize(), max_nesting_depth=10).parse()
