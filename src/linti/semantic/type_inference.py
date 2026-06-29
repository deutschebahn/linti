from linti.lexer.token import TokenType
from linti.parser.ast import (
    BinaryExpression,
    FunctionCall,
    Identifier,
    Number,
    String,
    UnaryExpression,
)

# TM1 built-in functions and their return types
# Keys are uppercase for case-insensitive matching
BUILTIN_RETURN_TYPES = {
    # String functions
    "SUBST": "string",
    "SUBSTR": "string",
    "UPPER": "string",
    "LOWER": "string",
    "TRIM": "string",
    "CHAR": "string",
    "STR": "string",
    "TIMST": "string",
    "TODAY": "string",
    "DATE": "string",
    "TIME": "string",
    "EXPAND": "string",
    "ATTRS": "string",
    "DIMNM": "string",
    "TABDIM": "string",
    "DTYPE": "string",
    # Numeric functions
    "DIMSIZ": "number",
    "NUMBR": "number",
    "INT": "number",
    "ROUND": "number",
    "MOD": "number",
    "LOG": "number",
    "LN": "number",
    "EXP": "number",
    "SQRT": "number",
    "ABS": "number",
    "MIN": "number",
    "MAX": "number",
    "DIMIX": "number",
    "ELCOMP": "number",
    "ELCOMPN": "number",
    "ELLEV": "number",
    "ELPAR": "number",
    "ELPARN": "number",
}


def infer_type(node):
    """
    Infer the type of an AST expression node.

    Args:
        node: An AST Expression node.

    Returns:
        "number", "string", or None if type cannot be determined.
    """
    if isinstance(node, Number):
        return "number"

    if isinstance(node, String):
        return "string"

    if isinstance(node, Identifier):
        # Cannot infer type from variable reference alone
        # Could be enhanced to track assignments
        return None

    if isinstance(node, BinaryExpression):
        left_type = infer_type(node.left)
        right_type = infer_type(node.right)

        if node.operator.type == TokenType.PIPE:
            if left_type == "string" and right_type == "string":
                return "string"
            return None

        # Numeric operations
        if left_type == "number" and right_type == "number":
            return "number"

        # Mixed operand types are invalid in TI (runtime error).
        # Unsupported combinations have no inferable static type here.
        return None

    if isinstance(node, FunctionCall):
        func_name_upper = node.name.upper()
        return BUILTIN_RETURN_TYPES.get(func_name_upper)

    if isinstance(node, UnaryExpression):
        if node.operator.type == TokenType.NOT:
            return "number"  # ~ produces a numeric (boolean) result
        if node.operator.type in (TokenType.PLUS, TokenType.MINUS):
            # Unary +/- are numeric operators in TI.
            return "number"
        return None

    return None
