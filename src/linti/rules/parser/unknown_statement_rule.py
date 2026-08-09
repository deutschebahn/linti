from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue, Severity
from linti.parser.ast import UnknownStatement
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

# Tokens that carry no position worth pointing at when locating the statement.
_IGNORED = frozenset(
    {TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT, TokenType.EOF}
)


class UnknownStatementRule(BaseStatementRule):
    """Flags statements the parser could not understand.

    When a statement cannot be parsed it lands in the AST as an
    ``UnknownStatement`` (error recovery keeps the rest of the section
    lintable).  Every AST-based rule silently skips such a statement, so any
    issue hiding inside it goes unseen — linting quality is reduced for that
    span.  This rule surfaces that fact with the exact file and line so the
    user knows coverage is incomplete and can fix the syntax.
    """

    CONFIG_KEY = "unknown_statement"
    METADATA = RuleMetadata(
        name="Unparseable Statement",
        description=(
            "Flags statements that could not be parsed, warning that linting "
            "quality is reduced for that code"
        ),
        auto_fix=False,
        # A warning, not an error, because this finding has two possible owners
        # and linti cannot tell them apart from the inside: either the TI really
        # is malformed (yours to fix), or linti's parser does not cover the
        # construct (ours to fix). Failing a build on the second case would be
        # wrong, so by default this reports without blocking. Projects where
        # unparseable TI is always a genuine syntax error can promote it back
        # with `rules.unknown_statement.severity: error`.
        severity=Severity.WARNING,
        explanation=(
            "The parser could not understand this statement and kept it in the "
            "AST as an unknown statement so the rest of the section could still "
            "be linted. AST-based rules skip unknown statements entirely, so any "
            "problem inside one is never reported — linting quality is reduced "
            "there. Fixing the syntax (a missing semicolon, an unbalanced "
            "parenthesis, a stray token) restores full coverage.\n\n"
            "This can equally mean linti's parser does not yet cover a construct "
            "TM1 accepts. If the process compiles on the server, it is a linti "
            "gap worth reporting — that is why this is a warning and does not "
            "fail a build by default."
        ),
        config_example=(
            "rules:\n  unknown_statement:\n    enabled: true\n    severity: warning"
        ),
        examples=[
            RuleExample(
                code="nValue = 1;",
                description="A well-formed statement parses and is fully linted",
                valid=True,
            ),
            RuleExample(
                code="nValue = 1",
                description="Missing terminating semicolon — cannot be parsed",
                valid=False,
            ),
        ],
    )

    DEPRECATED_IDS = ["E110"]

    @property
    def RULE_ID(self) -> str:
        return "P110"

    def interested_in(self):
        return [UnknownStatement]

    def visit(self, statement, context: LintContext):
        anchor = self._anchor_token(statement)
        line = anchor.line if anchor else 1
        column = anchor.column if anchor else 1
        position = anchor.position if anchor else 0
        return [
            LintIssue(
                message=(
                    "Statement could not be parsed; linting quality is reduced "
                    "here because rules cannot inspect it"
                ),
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]

    @staticmethod
    def _anchor_token(statement: UnknownStatement):
        """First meaningful token of the statement, for an accurate location."""
        for tok in statement.tokens:
            if tok.type not in _IGNORED:
                return tok
        return statement.tokens[0] if statement.tokens else None
