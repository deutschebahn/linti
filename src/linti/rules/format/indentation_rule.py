from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class IndentationRule(BaseRule):
    """
    Enforces indentation for IF/WHILE blocks.

    Indentation is validated per line based on block nesting.
    """

    CONFIG_KEY = "indentation"
    METADATA = RuleMetadata(
        name="Block Indentation",
        description="Enforces indentation for IF/WHILE blocks",
        auto_fix=True,
        explanation=(
            "Enforces consistent indentation for IF and WHILE blocks.\n"
            "The default indentation size is 4 spaces per nesting level. "
            "This can be configured via the `size` parameter."
        ),
        config_example=(
            "rules:\n"
            "  indentation:\n"
            "    enabled: true\n"
            "    size: 4  # number of spaces per indentation level"
        ),
        examples=[
            RuleExample(
                code="IF (nValue > 0);\n    nResult = 10;\nENDIF;",
                description="4-space indent",
                valid=True,
            ),
            RuleExample(
                code="IF (nValue > 0);\nnResult = 10;\nENDIF;",
                description="Missing indentation",
                valid=False,
            ),
        ],
    )

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        size = (
            rule_cfg.get("size", 4)
            if isinstance(rule_cfg, dict)
            else getattr(rule_cfg, "size", 4)
        )
        return [cls(indent_size=size)]

    @property
    def RULE_ID(self) -> str:
        return "F310"

    def __init__(self, indent_size: int = 4):
        self.indent_size = indent_size
        self._current_level = 0

    def reset(self) -> None:
        self._current_level = 0

    def interested_in(self):
        return [TokenType.NEWLINE]

    def visit(self, token, window, context: LintContext):
        issues = []
        line = token.line

        self._update_level_from_line(line, window)

        next_line = line + 1
        next_info = self._next_line_info(next_line, window)
        if not next_info:
            return issues

        indent_token, line_start_token, indent_count = next_info

        if line_start_token.type in (
            TokenType.ENDIF,
            TokenType.END,
            TokenType.ELSE,
            TokenType.ELSEIF,
        ):
            expected_level = max(self._current_level - 1, 0)
        else:
            expected_level = self._current_level

        expected_indent = expected_level * self.indent_size
        if indent_count != expected_indent:
            # Create fix for indentation
            correct_indent = " " * expected_indent
            if indent_token:
                # Replace existing whitespace
                fix = Fix(
                    position=indent_token.position,
                    old_value=indent_token.value,
                    new_value=correct_indent,
                )
            else:
                # Insert whitespace at start of first non-whitespace
                fix = Fix(
                    position=line_start_token.position,
                    old_value="",
                    new_value=correct_indent,
                )

            issue_token = indent_token or line_start_token
            issues.append(
                LintIssue(
                    f"Expected indentation of {expected_indent} spaces",
                    issue_token.line,
                    issue_token.column,
                    issue_token.position,
                    rule_id=self.RULE_ID,
                    fix=fix,
                )
            )

        return issues

    def _update_level_from_line(self, line, window):
        line_start = self._line_start_token(line, window)
        if not line_start:
            return

        if line_start.type in (TokenType.ELSE, TokenType.ELSEIF):
            self._current_level = max(self._current_level - 1, 0)
            self._current_level += 1
            return

        if line_start.type in (TokenType.ENDIF, TokenType.END):
            self._current_level = max(self._current_level - 1, 0)
            return

        if line_start.type in (TokenType.IF, TokenType.WHILE):
            self._current_level += 1

    def _line_start_token(self, line, window):
        offset = 1
        candidate = None
        while True:
            prev = window.previous(offset)
            if prev is None or prev.line != line:
                return candidate
            if prev.type not in (
                TokenType.WHITESPACE,
                TokenType.COMMENT,
                TokenType.NEWLINE,
            ):
                candidate = prev
            offset += 1

    def _next_line_info(self, line, window):
        offset = 1
        indent_token = None

        while True:
            nxt = window.next(offset)
            if nxt is None:
                return None
            if nxt.line < line:
                offset += 1
                continue
            if nxt.line > line:
                return None

            if nxt.type == TokenType.NEWLINE:
                return None

            if nxt.type == TokenType.WHITESPACE:
                indent_token = nxt
                offset += 1
                continue

            if nxt.type == TokenType.COMMENT:
                return None

            indent_count = len(indent_token.value) if indent_token else 0
            return indent_token, nxt, indent_count
