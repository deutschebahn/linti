"""F330 – Maximum line length."""

from linti.cst.layout import Reflow, reflow_target
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.parser.ast import Program
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

DEFAULT_LIMIT = 120


class MaxLineLengthRule(BaseStatementRule):
    """Flags lines longer than the configured limit and rewraps them."""

    CONFIG_KEY = "max_line_length"
    METADATA = RuleMetadata(
        name="Maximum Line Length",
        description="Limits how long a physical line may be",
        auto_fix=True,
        explanation=(
            "Flags any physical line longer than `limit` characters "
            "(120 by default).\n\n"
            "The fix rewraps the statement across several lines, breaking at "
            "the commas of an argument list or before the operators of a long "
            "condition, and indenting the result in the hanging style F310 "
            "enforces.\n\n"
            "Some long lines cannot be broken — a single long string literal, "
            "or a statement containing a comment that would change meaning if "
            "it moved. Those are reported without a fix."
        ),
        config_example=(
            "rules:\n  max_line_length:\n    enabled: true\n    limit: 120"
        ),
        examples=[
            RuleExample(
                code="sValue = CellGetS(\n    'Cube',\n    'Element'\n);",
                description="Wrapped at the argument boundaries",
                valid=True,
            ),
            RuleExample(
                code="IF(\n    nA = 1\n    & nB = 2\n);",
                description="Wrapped before each operator",
                valid=True,
            ),
            RuleExample(
                code="sValue = CellGetS( 'Cube', 'AAAA', 'BBBB', 'CCCC', 'DDDD' );",
                description="Single line over the limit",
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
                limit=setting("limit", DEFAULT_LIMIT),
                indent_size=setting("indent_size", 4),
            )
        ]

    @property
    def RULE_ID(self) -> str:
        return "F330"

    def __init__(self, limit: int = DEFAULT_LIMIT, indent_size: int = 4):
        self.limit = limit
        self.indent_size = indent_size

    def interested_in(self):
        # Line length is a property of the file, not of any one statement, so
        # one visit per program is both enough and exactly right.
        return [Program]

    def visit(self, statement, context: LintContext):
        if context.source is None:
            return []

        issues = []
        reflow = self._reflow(context)
        # One fix per construct: two long lines in the same wrapped call would
        # otherwise propose two overlapping rewrites of the same span.
        fixed_spans: set[tuple[int, int]] = set()

        for number, text in enumerate(context.source.split("\n"), start=1):
            if len(text) <= self.limit:
                continue
            issues.append(self._issue(number, text, context, reflow, fixed_spans))

        return issues

    def _reflow(self, context: LintContext):
        if context.tokens is None:
            return None
        return Reflow(
            context.tokens,
            context.source,
            limit=self.limit,
            indent_size=self.indent_size,
        )

    def _issue(self, number, text, context, reflow, fixed_spans) -> LintIssue:
        return LintIssue(
            f"Line exceeds {self.limit} characters ({len(text)})",
            number,
            self.limit + 1,
            self._line_offset(context.source, number),
            rule_id=self.RULE_ID,
            fix=self._fix(number, context, reflow, fixed_spans),
        )

    def _fix(self, number, context, reflow, fixed_spans):
        """Rewrap the construct owning line *number*, or None if we cannot."""
        lines = context.lines
        if lines is None or reflow is None:
            return None

        info = lines.get(number)
        if info is None or info.first_token is None:
            return None  # a long comment or a line inside a string literal

        node = context.cst.covering_node(self._token_index(context, info.first_token))
        target = reflow_target(node)
        if target is None:
            return None

        span = target.span(context.tokens)
        if span is None or span in fixed_spans:
            return None

        indent = lines.expected_indent(
            self._first_line_of(target, context), self.indent_size
        )
        if indent is None:
            indent = info.indent_width

        rendered = reflow.render(target, indent)
        if rendered is None:
            return None

        fixed_spans.add(span)
        return Fix(
            position=span[0],
            old_value=context.source[span[0] : span[1]],
            new_value=rendered,
        )

    @staticmethod
    def _first_line_of(node, context) -> int:
        return context.tokens[node.start].line

    @staticmethod
    def _token_index(context, token) -> int:
        for index, candidate in enumerate(context.tokens):
            if candidate is token:
                return index
        return 0

    @staticmethod
    def _line_offset(source: str, number: int) -> int:
        offset = 0
        for _ in range(number - 1):
            offset = source.index("\n", offset) + 1
        return offset
