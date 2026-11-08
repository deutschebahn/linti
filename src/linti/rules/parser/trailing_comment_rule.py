"""P120 – Trailing comment after code on the same line."""

from linti.lexer.token import Token, TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.linter.noqa import (
    NOQA_BEGIN_RE,
    NOQA_END_RE,
    NOQA_INLINE_RE,
    is_standalone_comment,
)
from linti.rules.Rule import BaseTokenRule, RuleExample, RuleMetadata

_NON_CODE = frozenset({TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.COMMENT})


class TrailingCommentRule(BaseTokenRule):
    """Flags a comment that follows code on the same line.

    TM1 saves such a process without complaint but fails when it runs, so the
    comment has to move onto a line of its own. The lexer only treats ``#`` as
    a comment at the start of a line or after a semicolon, so every trailing
    comment it produces follows a complete statement.
    """

    CONFIG_KEY = "trailing_comment"
    METADATA = RuleMetadata(
        name="Trailing Comment",
        description="Flags trailing comments that follow code on the same line",
        auto_fix=True,
        explanation=(
            "TI only allows a comment on a line of its own. A trailing comment "
            "after code on the same line (`nVar = 1; # note`) is saved by TM1 without an "
            "error, but the process fails when it runs.\n\n"
            "This also applies to suppression comments: a trailing "
            "`# noqa: F220` has no effect, because linti only honours `noqa` "
            "directives on their own line.\n\n"
            "The auto-fix moves the comment onto its own line directly above the "
            "code, with the same indentation, so a moved `# noqa` starts working "
            "for exactly that line. It is left to you when moving could change "
            "meaning: on a continuation line of a multi-line statement, for a "
            "`noqa-begin`/`noqa-end` marker (the region would shift), and for a "
            "`# noqa` on the first code line (it would turn into a "
            "procedure-wide suppression)."
        ),
        config_example="rules:\n  trailing_comment:\n    enabled: true",
        examples=[
            RuleExample(
                code="# Initialise the counter\nnVar = 1;",
                description="Comment on its own line",
                valid=True,
            ),
            RuleExample(
                code="nVar = 1; # Initialise the counter",
                description="Trailing comment fails at runtime in TM1",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "P120"

    def interested_in(self):
        return [TokenType.COMMENT]

    def visit(self, token, window, context: LintContext):
        tokens = window.tokens
        index = window.index
        if is_standalone_comment(tokens, index):
            return []

        is_region = bool(
            NOQA_BEGIN_RE.search(token.value) or NOQA_END_RE.search(token.value)
        )
        is_noqa = is_region or bool(NOQA_INLINE_RE.search(token.value))

        message = (
            "Trailing comment after code on the same line: TM1 saves the process but "
            "fails at runtime. Move the comment to its own line"
        )
        if is_noqa:
            message += " (this noqa has no effect here)"

        return [
            LintIssue(
                message,
                token.line,
                token.column,
                token.position,
                rule_id=self.RULE_ID,
                fix=self._fix(context.source, tokens, index, is_region, is_noqa),
            )
        ]

    @staticmethod
    def _fix(
        source: str | None,
        tokens: list[Token],
        index: int,
        is_region: bool,
        is_noqa: bool,
    ) -> Fix | None:
        """Move the comment onto its own line above the code, if that is safe.

        The text is sliced from *source*: token values cannot rebuild it,
        because string literals are stored unquoted.
        """
        if source is None or is_region:
            # Moving a region marker shifts the region it opens or closes.
            return None

        start = index
        while start > 0 and tokens[start - 1].type != TokenType.NEWLINE:
            start -= 1

        previous_code = next(
            (t for t in reversed(tokens[:start]) if t.type not in _NON_CODE), None
        )
        if previous_code is not None and previous_code.type != TokenType.SEMICOLON:
            # Continuation line: a comment line inside a statement is invalid too.
            return None
        if is_noqa and previous_code is None:
            # Above the first code line, a noqa becomes procedure-wide.
            return None

        line_start = tokens[start].position
        comment_token = tokens[index]
        old_value = source[line_start : comment_token.end_position]
        comment = comment_token.raw_text(source)
        code_part = source[line_start : comment_token.position].rstrip(" \t")
        code = code_part.lstrip(" \t")
        indent = code_part[: len(code_part) - len(code)]
        return Fix(
            position=line_start,
            old_value=old_value,
            new_value=f"{indent}{comment}\n{indent}{code}",
        )
