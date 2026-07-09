import pytest

from linti.lexer.lexer import Lexer
from linti.lexer.token import TokenType
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    ExpressionStatement,
    FunctionCall,
    Identifier,
    IfStatement,
    Number,
    Program,
    String,
    UnaryExpression,
    WhileStatement,
)
from linti.parser.parser import Parser


def _parse(code: str) -> Program:
    """Helper to tokenize and parse code."""
    tokens = Lexer(code).tokenize()
    return Parser(tokens).parse()


def test_parse_empty_program():
    """Test parsing empty input."""
    ast = _parse("")
    assert isinstance(ast, Program)
    assert len(ast.statements) == 0


def test_parse_single_assignment():
    """Test parsing a simple assignment."""
    ast = _parse("x = 5;")

    assert isinstance(ast, Program)
    assert len(ast.statements) == 1

    stmt = ast.statements[0]
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.left, Identifier)
    assert stmt.left.name == "x"
    assert isinstance(stmt.right, Number)
    assert stmt.right.value == 5


def test_parse_assignment_with_decimal_number():
    """Test parsing assignment with a decimal number literal."""
    ast = _parse("x = 5.25;")

    stmt = ast.statements[0]
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.right, Number)
    assert stmt.right.value == 5.25
    assert isinstance(stmt.right.value, float)


def test_parse_assignment_with_string():
    """Test parsing assignment with string literal."""
    ast = _parse("name = 'hello';")

    stmt = ast.statements[0]
    assert isinstance(stmt, Assignment)
    assert stmt.left.name == "name"
    assert isinstance(stmt.right, String)
    assert stmt.right.value == "hello"


def test_parse_multiple_assignments():
    """Test parsing multiple assignment statements."""
    code = """
    x = 1;
    y = 2;
    z = 3;
    """
    ast = _parse(code)

    assert len(ast.statements) == 3
    assert all(isinstance(stmt, Assignment) for stmt in ast.statements)
    assert ast.statements[0].left.name == "x"
    assert ast.statements[1].left.name == "y"
    assert ast.statements[2].left.name == "z"


def test_parse_expression_statement():
    """Test parsing standalone expression statement."""
    ast = _parse("42;")

    assert len(ast.statements) == 1
    stmt = ast.statements[0]
    assert isinstance(stmt, ExpressionStatement)
    assert isinstance(stmt.expression, Number)
    assert stmt.expression.value == 42


def test_parse_binary_expression_addition():
    """Test parsing addition expression."""
    ast = _parse("x = 1 + 2;")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.PLUS
    assert isinstance(stmt.right.left, Number)
    assert stmt.right.left.value == 1
    assert isinstance(stmt.right.right, Number)
    assert stmt.right.right.value == 2


def test_parse_binary_expression_multiplication():
    """Test parsing multiplication expression."""
    ast = _parse("x = 3 * 4;")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.STAR
    assert stmt.right.left.value == 3
    assert stmt.right.right.value == 4


def test_parse_binary_expression_pipe_concat():
    """Test parsing pipe concatenation expression."""
    ast = _parse("x = 'a' | 'b';")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.PIPE
    assert isinstance(stmt.right.left, String)
    assert stmt.right.left.value == "a"
    assert isinstance(stmt.right.right, String)
    assert stmt.right.right.value == "b"


def test_parse_operator_precedence():
    """Test that multiplication binds tighter than addition."""
    ast = _parse("x = 1 + 2 * 3;")

    stmt = ast.statements[0]
    # Should parse as: 1 + (2 * 3)
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.PLUS
    assert isinstance(stmt.right.left, Number)
    assert stmt.right.left.value == 1

    # Right side should be 2 * 3
    right = stmt.right.right
    assert isinstance(right, BinaryExpression)
    assert right.operator.type == TokenType.STAR
    assert right.left.value == 2
    assert right.right.value == 3


def test_parse_parenthesized_expression():
    """Test parsing parenthesized expression to override precedence."""
    ast = _parse("x = (1 + 2) * 3;")

    stmt = ast.statements[0]
    # Should parse as: (1 + 2) * 3
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.STAR

    # Left side should be 1 + 2
    left = stmt.right.left
    assert isinstance(left, BinaryExpression)
    assert left.operator.type == TokenType.PLUS
    assert left.left.value == 1
    assert left.right.value == 2

    assert stmt.right.right.value == 3


def test_parse_function_call_no_args():
    """Test parsing function call with no arguments."""
    ast = _parse("x = foo();")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, FunctionCall)
    assert stmt.right.name == "foo"
    assert len(stmt.right.args) == 0


def test_parse_function_call_single_arg():
    """Test parsing function call with one argument."""
    ast = _parse("x = foo(42);")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, FunctionCall)
    assert stmt.right.name == "foo"
    assert len(stmt.right.args) == 1
    assert isinstance(stmt.right.args[0], Number)
    assert stmt.right.args[0].value == 42


def test_parse_function_call_multiple_args():
    """Test parsing function call with multiple arguments."""
    ast = _parse("x = add(1, 2, 3);")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, FunctionCall)
    assert stmt.right.name == "add"
    assert len(stmt.right.args) == 3
    assert all(isinstance(arg, Number) for arg in stmt.right.args)
    assert stmt.right.args[0].value == 1
    assert stmt.right.args[1].value == 2
    assert stmt.right.args[2].value == 3


def test_parse_function_call_with_expression_args():
    """Test parsing function call with expression arguments."""
    ast = _parse("x = func(1 + 2, y);")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, FunctionCall)
    assert len(stmt.right.args) == 2

    # First arg should be binary expression
    assert isinstance(stmt.right.args[0], BinaryExpression)
    assert stmt.right.args[0].operator.type == TokenType.PLUS

    # Second arg should be identifier
    assert isinstance(stmt.right.args[1], Identifier)
    assert stmt.right.args[1].name == "y"


def test_parse_nested_function_calls():
    """Test parsing nested function calls."""
    ast = _parse("x = outer(inner(5));")

    stmt = ast.statements[0]
    outer_call = stmt.right
    assert isinstance(outer_call, FunctionCall)
    assert outer_call.name == "outer"
    assert len(outer_call.args) == 1

    inner_call = outer_call.args[0]
    assert isinstance(inner_call, FunctionCall)
    assert inner_call.name == "inner"
    assert len(inner_call.args) == 1
    assert inner_call.args[0].value == 5


def test_parse_inline_if_expression():
    """TI overloads `If` as an inline expression function: If(cond, then, else)."""
    ast = _parse(
        "sVar3 = If( pLegacy <> 1, Subst( v3 , Scan( '-' , v3 ) + 1 , Long( v3 ) ), v3 );"
    )

    stmt = ast.statements[0]
    assert isinstance(stmt.right, FunctionCall)
    assert stmt.right.name == "If"
    assert len(stmt.right.args) == 3
    # cond, then (a nested call), else (a bare identifier)
    assert isinstance(stmt.right.args[0], BinaryExpression)
    assert isinstance(stmt.right.args[1], FunctionCall)
    assert isinstance(stmt.right.args[2], Identifier)
    assert stmt.right.args[2].name == "v3"


def test_parse_nested_inline_if_expression():
    """An inline If may nest inside another inline If's arguments."""
    ast = _parse("x = If(a = 1, If(b = 2, 'p', 'q'), 'r');")

    outer = ast.statements[0].right
    assert isinstance(outer, FunctionCall) and outer.name == "If"
    inner = outer.args[1]
    assert isinstance(inner, FunctionCall) and inner.name == "If"
    assert len(inner.args) == 3


def test_statement_form_if_is_not_an_expression():
    """The IF ... ENDIF statement form must still parse as an IfStatement."""
    ast = _parse("IF(pFlag = 1);\n  sDim = 'Region';\nENDIF;")
    assert isinstance(ast.statements[0], IfStatement)


def test_parse_unary_minus():
    """Test parsing unary minus operator."""
    ast = _parse("x = -5;")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, UnaryExpression)
    assert stmt.right.operator.type == TokenType.MINUS
    assert isinstance(stmt.right.operand, Number)
    assert stmt.right.operand.value == 5


def test_parse_unary_plus():
    """Test parsing unary plus operator (is a no-op)."""
    ast = _parse("x = +5;")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, UnaryExpression)
    assert stmt.right.operator.type == TokenType.PLUS
    assert isinstance(stmt.right.operand, Number)
    assert stmt.right.operand.value == 5


def test_parse_identifier_stores_token():
    """Test that identifier nodes store original token for position info."""
    ast = _parse("myVar = 123;")

    stmt = ast.statements[0]
    ident = stmt.left
    assert isinstance(ident, Identifier)
    assert ident.name == "myVar"
    assert ident.token is not None
    assert ident.token.type == TokenType.IDENTIFIER
    assert ident.token.value == "myVar"
    assert ident.token.position == 0


def test_parse_mixed_statements():
    """Test parsing a mix of assignments and expression statements."""
    code = """
    42;
    x = 10;
    y = x + 5;
    100;
    """
    ast = _parse(code)

    assert len(ast.statements) == 4
    assert isinstance(ast.statements[0], ExpressionStatement)
    assert isinstance(ast.statements[1], Assignment)
    assert isinstance(ast.statements[2], Assignment)
    assert isinstance(ast.statements[3], ExpressionStatement)


def test_parse_comments_are_ignored():
    """Test that comments are filtered out during parsing."""
    code = """
    # This is a comment
    x = 5; # inline comment
    # Another comment
    y = 10;
    """
    ast = _parse(code)

    # Should only see 2 assignments
    assert len(ast.statements) == 2
    assert ast.statements[0].left.name == "x"
    assert ast.statements[1].left.name == "y"


def test_parse_while_simple():
    """Test parsing a simple WHILE/END loop."""
    code = """
    WHILE (x < 10);
        x = x + 1;
    END;
    """
    ast = _parse(code)
    assert len(ast.statements) == 1

    stmt = ast.statements[0]
    assert isinstance(stmt, WhileStatement)
    assert isinstance(stmt.condition, BinaryExpression)
    assert len(stmt.body) == 1
    assert isinstance(stmt.body[0], Assignment)


def test_parse_while_empty_body():
    """Test parsing WHILE with empty body."""
    code = "WHILE (1);END;"
    ast = _parse(code)
    assert len(ast.statements) == 1
    assert isinstance(ast.statements[0], WhileStatement)
    assert len(ast.statements[0].body) == 0


def test_parse_while_multiple_statements():
    """Test parsing WHILE with multiple statements in body."""
    code = """
    WHILE (n > 0);
        x = x + n;
        n = n - 1;
        LogOutput('INFO', 'loop');
    END;
    """
    ast = _parse(code)
    assert len(ast.statements) == 1

    stmt = ast.statements[0]
    assert isinstance(stmt, WhileStatement)
    assert len(stmt.body) == 3
    assert isinstance(stmt.body[0], Assignment)
    assert isinstance(stmt.body[1], Assignment)
    assert isinstance(stmt.body[2], ExpressionStatement)


def test_parse_while_nested_if():
    """Test parsing WHILE containing an IF statement."""
    code = """
    WHILE (i < 10);
        IF (i > 5);
            x = 1;
        ENDIF;
        i = i + 1;
    END;
    """
    ast = _parse(code)
    assert len(ast.statements) == 1

    from linti.parser.ast import IfStatement

    stmt = ast.statements[0]
    assert isinstance(stmt, WhileStatement)
    assert len(stmt.body) == 2
    assert isinstance(stmt.body[0], IfStatement)
    assert isinstance(stmt.body[1], Assignment)


def test_parse_nested_while():
    """Test parsing nested WHILE loops."""
    code = """
    WHILE (i < 10);
        WHILE (j < 5);
            x = i + j;
        END;
        i = i + 1;
    END;
    """
    ast = _parse(code)
    assert len(ast.statements) == 1

    outer = ast.statements[0]
    assert isinstance(outer, WhileStatement)
    assert len(outer.body) == 2
    assert isinstance(outer.body[0], WhileStatement)
    assert isinstance(outer.body[1], Assignment)

    inner = outer.body[0]
    assert len(inner.body) == 1
    assert isinstance(inner.body[0], Assignment)


def test_parse_while_lowercase():
    """Test parsing while/end in lowercase."""
    code = "while (x < 5);x = x + 1;end;"
    ast = _parse(code)
    assert len(ast.statements) == 1
    assert isinstance(ast.statements[0], WhileStatement)


def test_parse_while_missing_end():
    """Test error recovery when END is missing."""
    from linti.parser.ast import UnknownStatement

    code = "WHILE (x < 5);x = 1;"
    ast = _parse(code)
    # Should produce UnknownStatement(s) via error recovery
    assert len(ast.statements) >= 1
    has_unknown = any(isinstance(s, UnknownStatement) for s in ast.statements)
    assert has_unknown


def test_parse_if_elseif():
    """Test parsing IF/ELSEIF/ENDIF."""
    code = """
    IF (x = 1);
        a = 1;
    ELSEIF (x = 2);
        a = 2;
    ENDIF;
    """
    ast = _parse(code)
    assert len(ast.statements) == 1

    stmt = ast.statements[0]
    assert isinstance(stmt, IfStatement)
    assert len(stmt.then_body) == 1
    assert stmt.then_body[0].left.name == "a"

    # ELSEIF is modelled as a nested IfStatement in else_body
    assert len(stmt.else_body) == 1
    elseif = stmt.else_body[0]
    assert isinstance(elseif, IfStatement)
    assert len(elseif.then_body) == 1
    assert elseif.then_body[0].left.name == "a"
    assert len(elseif.else_body) == 0


def test_parse_if_elseif_else():
    """Test parsing IF/ELSEIF/ELSE/ENDIF."""
    code = """
    IF (x = 1);
        a = 10;
    ELSEIF (x = 2);
        a = 20;
    ELSE;
        a = 30;
    ENDIF;
    """
    ast = _parse(code)
    stmt = ast.statements[0]
    assert isinstance(stmt, IfStatement)
    assert len(stmt.then_body) == 1

    # First ELSEIF
    elseif = stmt.else_body[0]
    assert isinstance(elseif, IfStatement)
    assert len(elseif.then_body) == 1

    # ELSE body inside the ELSEIF node
    assert len(elseif.else_body) == 1
    assert isinstance(elseif.else_body[0], Assignment)
    assert elseif.else_body[0].right.value == 30


def test_parse_multiple_elseif():
    """Test parsing IF with multiple ELSEIF branches."""
    code = """
    IF (x = 1);
        a = 1;
    ELSEIF (x = 2);
        a = 2;
    ELSEIF (x = 3);
        a = 3;
    ELSE;
        a = 0;
    ENDIF;
    """
    ast = _parse(code)
    stmt = ast.statements[0]
    assert isinstance(stmt, IfStatement)

    # First ELSEIF
    elseif1 = stmt.else_body[0]
    assert isinstance(elseif1, IfStatement)
    assert len(elseif1.then_body) == 1

    # Second ELSEIF (nested in first ELSEIF's else_body)
    elseif2 = elseif1.else_body[0]
    assert isinstance(elseif2, IfStatement)
    assert len(elseif2.then_body) == 1

    # ELSE body
    assert len(elseif2.else_body) == 1
    assert isinstance(elseif2.else_body[0], Assignment)


def test_if_without_else_has_no_else_token():
    """An IF without ELSE leaves else_token None and else_body empty."""
    ast = _parse("IF (x = 1);\n    a = 1;\nENDIF;")
    stmt = ast.statements[0]
    assert stmt.else_token is None
    assert stmt.else_body == []


def test_empty_else_is_distinguishable_from_no_else():
    """An empty ELSE sets else_token even though else_body is empty.

    This disambiguates it from an IF that has no ELSE at all, which the AST
    could not express before.
    """
    ast = _parse("IF (x = 1);\n    a = 1;\nELSE;\nENDIF;")
    stmt = ast.statements[0]
    assert stmt.else_token is not None
    assert stmt.else_token.type == TokenType.ELSE
    assert stmt.else_body == []


def test_else_with_body_sets_else_token():
    """A populated ELSE sets else_token and keeps its statements."""
    ast = _parse("IF (x = 1);\n    a = 1;\nELSE;\n    a = 2;\nENDIF;")
    stmt = ast.statements[0]
    assert stmt.else_token is not None
    assert len(stmt.else_body) == 1


def test_elseif_keeps_else_token_none():
    """An ELSEIF branch is modelled in else_body, so else_token stays None."""
    ast = _parse("IF (x = 1);\n    a = 1;\nELSEIF (x = 2);\n    a = 2;\nENDIF;")
    stmt = ast.statements[0]
    assert stmt.else_token is None
    assert isinstance(stmt.else_body[0], IfStatement)


def test_parse_elseif_lowercase():
    """Test parsing elseif in lowercase."""
    code = "if (x = 1);a = 1;elseif (x = 2);a = 2;endif;"
    ast = _parse(code)
    stmt = ast.statements[0]
    assert isinstance(stmt, IfStatement)
    assert isinstance(stmt.else_body[0], IfStatement)


def test_parse_not_operator():
    """Test parsing ~ (NOT) operator."""
    ast = _parse("IF (~(x = 1));a = 1;ENDIF;")

    stmt = ast.statements[0]
    assert isinstance(stmt, IfStatement)
    condition = stmt.condition
    assert isinstance(condition, UnaryExpression)
    assert condition.operator.type == TokenType.NOT
    # operand is a parenthesized comparison
    assert isinstance(condition.operand, BinaryExpression)


def test_parse_not_operator_simple():
    """Test parsing ~ on an identifier."""
    ast = _parse("x = ~flag;")

    stmt = ast.statements[0]
    assert isinstance(stmt.right, UnaryExpression)
    assert stmt.right.operator.type == TokenType.NOT
    assert isinstance(stmt.right.operand, Identifier)
    assert stmt.right.operand.name == "flag"


def test_parse_not_with_function_call():
    """Test parsing ~ before a function call."""
    ast = _parse("IF (~IsError());a = 1;ENDIF;")

    stmt = ast.statements[0]
    condition = stmt.condition
    assert isinstance(condition, UnaryExpression)
    assert condition.operator.type == TokenType.NOT
    assert isinstance(condition.operand, FunctionCall)
    assert condition.operand.name == "IsError"


def test_parse_error_missing_semicolon():
    """Test that missing semicolon creates UnknownStatement (error recovery)."""
    from linti.parser.ast import UnknownStatement

    program = _parse("x = 5")
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], UnknownStatement)
    assert "Expected ';'" in program.statements[0].error_message


def test_parse_error_missing_equals():
    """Test that missing equals sign creates UnknownStatement (error recovery)."""
    from linti.parser.ast import UnknownStatement

    program = _parse("x 5;")
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], UnknownStatement)


def test_parse_error_unexpected_token():
    """Test that unexpected token creates UnknownStatement (error recovery)."""
    from linti.parser.ast import UnknownStatement

    program = _parse("x = @;")
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], UnknownStatement)
    assert "Unexpected token" in program.statements[0].error_message


def test_parse_error_unterminated_paren():
    """Test that unterminated parenthesis creates UnknownStatement (error recovery)."""
    from linti.parser.ast import UnknownStatement

    program = _parse("x = (1 + 2;")
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], UnknownStatement)
    assert "Expected ')'" in program.statements[0].error_message


def test_parse_error_missing_function_close_paren():
    """Test that missing closing paren in function call creates UnknownStatement (error recovery)."""
    from linti.parser.ast import UnknownStatement

    program = _parse("x = foo(1, 2;")
    assert len(program.statements) == 1
    assert isinstance(program.statements[0], UnknownStatement)
    assert "Expected ')'" in program.statements[0].error_message


@pytest.mark.parametrize(
    "code, expected_type",
    [
        ("x = 5;", Number),
        ("x = 'text';", String),
        ("x = y;", Identifier),
        ("x = 1 + 2;", BinaryExpression),
        ("x = func();", FunctionCall),
    ],
)
def test_parse_assignment_right_side_types(code, expected_type):
    """Test various expression types on right side of assignment."""
    ast = _parse(code)
    stmt = ast.statements[0]
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.right, expected_type)


def test_parse_complex_expression():
    """Test parsing a complex nested expression."""
    ast = _parse("result = (a + b) * func(x, y + 2) - 10;")

    stmt = ast.statements[0]
    assert isinstance(stmt, Assignment)
    assert stmt.left.name == "result"

    # The entire right side is a subtraction
    assert isinstance(stmt.right, BinaryExpression)
    assert stmt.right.operator.type == TokenType.MINUS

    # Left side of subtraction is (a + b) * func(...)
    left_mult = stmt.right.left
    assert isinstance(left_mult, BinaryExpression)
    assert left_mult.operator.type == TokenType.STAR

    # Check function call is present
    func_call = left_mult.right
    assert isinstance(func_call, FunctionCall)
    assert func_call.name == "func"
    assert len(func_call.args) == 2


def test_parse_at_end():
    """Test at_end() method."""
    tokens = Lexer("x = 5;").tokenize()
    parser = Parser(tokens)

    assert not parser.at_end()
    parser.parse()
    assert parser.at_end()


def test_parse_current_and_advance():
    """Test current() and advance() methods."""
    tokens = Lexer("x = 5;").tokenize()
    parser = Parser(tokens)

    # First non-whitespace token is IDENTIFIER
    tok = parser.current()
    assert tok.type == TokenType.IDENTIFIER

    parser.advance()
    tok = parser.current()
    assert tok.type == TokenType.EQUALS


def test_parse_match():
    """Test match() method."""
    tokens = Lexer("x = 5;").tokenize()
    parser = Parser(tokens)

    # Match IDENTIFIER
    assert parser.match(TokenType.IDENTIFIER)
    # Now at EQUALS
    assert not parser.match(TokenType.IDENTIFIER)
    assert parser.match(TokenType.EQUALS)


def test_parse_peek():
    """Test peek() method."""
    tokens = Lexer("x = 5;").tokenize()
    parser = Parser(tokens)

    # Current is IDENTIFIER
    assert parser.current().type == TokenType.IDENTIFIER
    # Peek ahead 1
    next_tok = parser.peek(1)
    assert next_tok.type == TokenType.EQUALS
    # Current should still be IDENTIFIER
    assert parser.current().type == TokenType.IDENTIFIER
