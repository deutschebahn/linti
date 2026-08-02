class ASTNode:
    """Base class for all abstract syntax tree nodes."""

    pass


def get_node_token(node):
    """Safely extract a token from an AST node.

    Returns the token if the node has one, otherwise ``None``.
    """
    return getattr(node, "token", None)


#: Expression attributes to descend into when walking an expression subtree.
_EXPR_CHILD_ATTRS = ("left", "right", "operand", "condition")


def iter_expression_nodes(node):
    """Yield *node* and every descendant expression node.

    Walks the operand/condition and ``args`` children of an expression subtree.
    The linter's statement walk stops at statement boundaries, so rules that
    need to inspect the expressions *within* a statement (function calls, string
    literals, …) traverse them with this helper instead of re-implementing the
    same descent.
    """
    if not isinstance(node, ASTNode):
        return
    yield node
    for attr in _EXPR_CHILD_ATTRS:
        child = getattr(node, attr, None)
        if isinstance(child, ASTNode):
            yield from iter_expression_nodes(child)
    for child in getattr(node, "args", None) or []:
        if isinstance(child, ASTNode):
            yield from iter_expression_nodes(child)


class Statement(ASTNode):
    """Base class for all statement nodes."""

    pass


class Expression(ASTNode):
    """Base class for all expression nodes."""

    pass


class Program(ASTNode):
    """
    Represents a complete TI process program.

    Attributes:
        statements: List of Statement nodes representing the program body.
    """

    def __init__(self, statements):
        self.statements = statements


class ExpressionStatement(Statement):
    """
    Represents a standalone expression followed by semicolon.

    Attributes:
        expression: The Expression being evaluated.
        token: Optional Token for position information.
    """

    def __init__(self, expression, token=None):
        self.expression = expression
        self.token = token


class Assignment(Statement):
    """
    Represents an assignment statement.

    Attributes:
        left: An Identifier representing the variable being assigned.
        right: An Expression representing the value being assigned.
        token: Optional Token for position information (the identifier token).
    """

    def __init__(self, left, right, token=None):
        self.left = left
        self.right = right
        self.token = token


class IfStatement(Statement):
    """
    Represents an IF/ENDIF control flow statement.

    Attributes:
        condition: Expression representing the condition.
        then_body: List of Statement nodes in the IF block.
        else_body: Optional list of Statement nodes in the ELSE block.
        token: Optional Token for position information (the IF/ELSEIF token).
        else_token: Optional Token for the ELSE keyword.  Set only when an
            ELSE clause is present, which lets callers tell an empty ELSE
            (``else_token`` set, ``else_body`` empty) apart from no ELSE at
            all (``else_token`` is ``None``).  ELSEIF branches keep this
            ``None`` — they are modelled as nested IfStatements in else_body.
    """

    def __init__(
        self, condition, then_body, else_body=None, token=None, else_token=None
    ):
        self.condition = condition
        self.then_body = then_body
        self.else_body = else_body or []
        self.token = token
        self.else_token = else_token


class WhileStatement(Statement):
    """
    Represents a WHILE/END control flow statement.

    Attributes:
        condition: Expression representing the loop condition.
        body: List of Statement nodes in the loop body.
        token: Optional Token for position information (the WHILE token).
    """

    def __init__(self, condition, body, token=None):
        self.condition = condition
        self.body = body
        self.token = token


class UnknownStatement(Statement):
    """
    Represents a statement that could not be parsed.

    Used for error recovery to allow the parser to continue processing
    remaining statements even when encountering invalid syntax.

    Attributes:
        tokens: List of Token objects that comprise the unknown statement.
        error_message: Description of why this statement could not be parsed.
    """

    def __init__(self, tokens, error_message="Unknown statement"):
        self.tokens = tokens
        self.error_message = error_message


class Identifier(Expression):
    """
    Represents a variable or function name identifier.

    Attributes:
        name: String containing the identifier name.
        token: Original Token object (for position information).
    """

    def __init__(self, name, token=None):
        self.name = name
        self.token = token


class Number(Expression):
    """
    Represents a numeric literal.

    Attributes:
        value: The number as a float (TM1 numbers are IEEE-754 doubles).
        token: Optional Token for position information.
    """

    def __init__(self, value, token=None):
        self.value = value
        self.token = token


class String(Expression):
    """
    Represents a string literal.

    Attributes:
        value: String content (without surrounding quotes).
        token: Optional Token for position information.
    """

    def __init__(self, value, token=None):
        self.value = value
        self.token = token


class BinaryExpression(Expression):
    """
    Represents a binary operation (e.g., a + b, a * b).

    Attributes:
        left: Left operand Expression.
        operator: TokenType representing the operator (+, -, *, /, etc.).
        right: Right operand Expression.
    """

    def __init__(self, left, operator, right):
        self.left = left
        self.operator = operator
        self.right = right


class UnaryExpression(Expression):
    """
    Represents a unary operation (e.g., ~condition, -x).

    Attributes:
        operator: Token representing the operator (~, -, +).
        operand: The Expression being operated on.
    """

    def __init__(self, operator, operand):
        self.operator = operator
        self.operand = operand


class FunctionCall(Expression):
    """
    Represents a function call expression.

    Attributes:
        name: String containing the function name.
        args: List of Expression arguments passed to the function.
        token: Original Token object for the function name (for position information).
    """

    def __init__(self, name, args, token=None):
        self.name = name
        self.args = args
        self.token = token


# Walking helpers that need the node classes above. ``iter_expression_nodes``
# lives near the top with ``get_node_token``; these two build on it.


def iter_function_calls(node):
    """Yield every FunctionCall in an expression subtree."""
    return (n for n in iter_expression_nodes(node) if isinstance(n, FunctionCall))


#: The statement types that can carry an expression, and therefore a function
#: call.  A rule registering on exactly these is handed every statement in the
#: program — nested ones included — because the linter recurses into IF/WHILE
#: bodies.  Kept next to :func:`statement_expression` so registration and the
#: mapping below stay a single edit point: the linter's registry dispatches on
#: the exact ``type(node)``, so a rule whose list goes stale would silently stop
#: seeing the new statement type rather than fail.
EXPRESSION_CARRYING_STATEMENTS = (
    Assignment,
    ExpressionStatement,
    IfStatement,
    WhileStatement,
)


def statement_expression(statement):
    """The expression a visited statement carries a function call in, if any.

    Pairs with the linter's statement walk: a rule that registers on
    :data:`EXPRESSION_CARRYING_STATEMENTS` is handed every statement in the
    program — nested ones included — and this maps each to the expression worth
    inspecting, so the rule does not need its own recursive descent.  Returns
    ``None`` for a statement that carries no expression.

    """
    if isinstance(statement, Assignment):
        return statement.right
    if isinstance(statement, ExpressionStatement):
        return statement.expression
    if isinstance(statement, (IfStatement, WhileStatement)):
        return statement.condition
    return None
