from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    IDENTIFIER = auto()
    PREDEFINED_IDENTIFIER = auto()  # TM1 system variables
    NUMBER = auto()
    EQUALS = auto()
    STRING_EQUALS = auto()  # @= for string comparison
    STRING_NOT_EQUAL = auto()  # @<> for string not equal
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LESS = auto()
    GREATER = auto()
    LESS_EQUAL = auto()
    GREATER_EQUAL = auto()
    NOT_EQUAL = auto()
    AND = auto()
    OR = auto()
    NOT = auto()  # ~ logical negation
    PIPE = auto()
    SEMICOLON = auto()
    COMMA = auto()
    WHITESPACE = auto()
    NEWLINE = auto()
    STRING = auto()
    COMMENT = auto()
    UNKNOWN = auto()
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    IF = auto()
    ELSE = auto()
    ELSEIF = auto()
    ENDIF = auto()
    WHILE = auto()
    END = auto()
    EOF = auto()


KEYWORDS: dict[str, TokenType] = {
    "IF": TokenType.IF,
    "ELSE": TokenType.ELSE,
    "ELSEIF": TokenType.ELSEIF,
    "ENDIF": TokenType.ENDIF,
    "WHILE": TokenType.WHILE,
    "END": TokenType.END,
}

# TM1 predefined system variables (canonical casing)
TM1_PREDEFINED_VARIABLES: set[str] = {
    # TurboIntegrator Local Variables
    "DatasourceASCIIDecimalSeparator",
    "DatasourceASCIIThousandSeparator",
    "DatasourceASCIIDelimiter",
    "DatasourceASCIIHeaderRecords",
    "DatasourceASCIIQuoteCharacter",
    "DatasourceCubeview",
    "DatasourceDimensionSubset",
    "DatasourceJsonRootPointer",
    "DatasourceJsonVariableMapping",
    "DatasourceNameForServer",
    "DatasourceNameForClient",
    "DatasourcePassword",
    "DatasourceQuery",
    "DatasourceType",
    "DatasourceUsername",
    "MinorErrorLogMax",
    "NValue",
    "OnMinorErrorDoItemSkip",
    "SValue",
    "Value_Is_String",
    # Implicit Global Variables
    "DataMinorErrorCount",
    "MetadataMinorErrorCount",
    "ProcessReturnCode",
    "PrologMinorErrorCount",
}

# Case-insensitive lookup set
TM1_PREDEFINED_VARIABLES_UPPER: set[str] = {v.upper() for v in TM1_PREDEFINED_VARIABLES}

OPERATORS = {
    "@<>": TokenType.STRING_NOT_EQUAL,
    "<=": TokenType.LESS_EQUAL,
    ">=": TokenType.GREATER_EQUAL,
    "<>": TokenType.NOT_EQUAL,
    "@=": TokenType.STRING_EQUALS,
    "|": TokenType.PIPE,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "=": TokenType.EQUALS,
    "<": TokenType.LESS,
    ">": TokenType.GREATER,
    "&": TokenType.AND,
    "%": TokenType.OR,
    "~": TokenType.NOT,
}

#: Token types that represent binary (infix) operators.
BINARY_OP_TYPES: frozenset["TokenType"] = frozenset(
    {
        TokenType.PLUS,
        TokenType.MINUS,
        TokenType.STAR,
        TokenType.SLASH,
        TokenType.EQUALS,
        TokenType.LESS,
        TokenType.GREATER,
        TokenType.LESS_EQUAL,
        TokenType.GREATER_EQUAL,
        TokenType.NOT_EQUAL,
        TokenType.STRING_EQUALS,
        TokenType.STRING_NOT_EQUAL,
        TokenType.AND,
        TokenType.OR,
        TokenType.PIPE,
    }
)

#: Token types that represent an expression value (right-hand side of a binary
#: operator or the result of a sub-expression).  A PLUS or MINUS preceded by
#: one of these is a *binary* operator; otherwise it is unary.
EXPRESSION_VALUE_TYPES: frozenset["TokenType"] = frozenset(
    {
        TokenType.IDENTIFIER,
        TokenType.PREDEFINED_IDENTIFIER,
        TokenType.NUMBER,
        TokenType.STRING,
        TokenType.RPAREN,
    }
)


def is_unary_plus_minus(window) -> bool:
    """Return True when the current PLUS/MINUS token is a unary operator.

    A sign is unary when no expression value immediately precedes it (after
    skipping whitespace).  Examples: ``-1``, ``(-nVal)``, ``func(-1)``.
    """
    prev = window.previous_non_ws()
    if prev is None:
        return True
    return prev.type not in EXPRESSION_VALUE_TYPES


@dataclass
class Token:
    type: TokenType
    value: str
    position: int  # start index in the full input string
    line: int
    column: int
