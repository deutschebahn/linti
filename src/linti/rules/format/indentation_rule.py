"""F310 – Block indentation."""

from linti.cst.lines import CONTINUATION_STYLES, HANGING
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.parser.ast import Program
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class IndentationRule(BaseStatementRule):
    """
    Enforces indentation for IF/WHILE blocks and for continuation lines.

    Indentation is validated per physical line against the concrete syntax
    tree, so a line that *continues* a statement is judged as a continuation
    rather than as a badly indented statement of its own.
    """

    CONFIG_KEY = "indentation"
    METADATA = RuleMetadata(
        name="Block Indentation",
        description="Enforces indentation for IF/WHILE blocks and wrapped lines",
        auto_fix=True,
        explanation=(
            "Enforces consistent indentation for IF and WHILE blocks.\n"
            "The default indentation size is 4 spaces per nesting level. "
            "This can be configured via the `size` parameter.\n\n"
            "A line that continues a statement started earlier — a wrapped "
            "argument list, a multi-line condition — is indented in the "
            "*hanging* style: one level deeper per open parenthesis, and the "
            "line that closes a parenthesis returns to the level of the line "
            "that opened it. Set `continuation_style` to `aligned` to line "
            "wrapped content up under the opening parenthesis instead, or to "
            "`ignore` to leave hand-formatted continuation lines alone.\n\n"
            "Lines inside a multi-line string literal are never touched: their "
            "indentation is part of the string's value."
        ),
        config_example=(
            "rules:\n"
            "  indentation:\n"
            "    enabled: true\n"
            "    size: 4  # number of spaces per indentation level\n"
            "    continuation_style: hanging  # hanging | aligned | ignore"
        ),
        examples=[
            RuleExample(
                code="IF (nValue > 0);\n    nResult = 10;\nENDIF;",
                description="4-space indent",
                valid=True,
            ),
            RuleExample(
                code="sValue = CellGetS(\n    'Cube',\n    'Element'\n);",
                description="Wrapped argument list (hanging indent)",
                valid=True,
            ),
            RuleExample(
                code="IF (nValue > 0);\nnResult = 10;\nENDIF;",
                description="Missing indentation",
                valid=False,
            ),
            RuleExample(
                code="sValue = CellGetS( 'Cube',\n           'Element' );",
                description="Wrapped line not at the hanging indent",
                valid=False,
            ),
        ],
    )

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        def setting(name, default):
            if isinstance(rule_cfg, dict):
                return rule_cfg.get(name, default)
            return getattr(rule_cfg, name, default)

        return [
            cls(
                indent_size=setting("size", 4),
                continuation_style=setting("continuation_style", HANGING),
            )
        ]

    @property
    def RULE_ID(self) -> str:
        return "F310"

    def __init__(self, indent_size: int = 4, continuation_style: str = HANGING):
        self.indent_size = indent_size
        self.continuation_style = (
            continuation_style if continuation_style in CONTINUATION_STYLES else HANGING
        )

    def interested_in(self):
        # One visit per program: indentation is a property of physical lines,
        # not of any single statement, and the line model already knows which
        # statement each line belongs to.
        return [Program]

    def visit(self, statement, context: LintContext):
        lines = context.lines
        if lines is None:
            return []

        issues = []
        for info in lines:
            expected = lines.expected_indent(
                info.line, self.indent_size, self.continuation_style
            )
            if expected is None or expected == info.indent_width:
                continue
            issues.append(self._issue(info, expected))

        return issues

    def _issue(self, info, expected: int) -> LintIssue:
        correct_indent = " " * expected

        if info.indent_token is not None:
            fix = Fix(
                position=info.indent_token.position,
                old_value=info.indent_token.value,
                new_value=correct_indent,
            )
            anchor = info.indent_token
        else:
            # Nothing to replace — insert the indent before the first token.
            fix = Fix(
                position=info.first_token.position,
                old_value="",
                new_value=correct_indent,
            )
            anchor = info.first_token

        what = "continuation " if info.is_continuation else ""
        return LintIssue(
            f"Expected {what}indentation of {expected} spaces",
            anchor.line,
            anchor.column,
            anchor.position,
            rule_id=self.RULE_ID,
            fix=fix,
        )
