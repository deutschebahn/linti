from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    ExpressionStatement,
    FunctionCall,
    get_node_token,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class ItemSkipRule(BaseStatementRule):
    """
    Enforces that ItemSkip() is only allowed in Metadata and Data blocks.

    ItemSkip() is used to skip processing of the current record, which only makes sense
    in Metadata and Data sections. Using it in Prolog or Epilog has no effect and indicates
    a logic error.
    """

    CONFIG_KEY = "item_skip"
    DEFAULT_ENABLED = False
    DEPRECATED_IDS = ["S120"]
    METADATA = RuleMetadata(
        name="ItemSkip Block Usage",
        description="Enforces that ItemSkip() is only used in metadata or data sections",
        auto_fix=False,
        deprecated_by="C150",
        explanation=(
            "Deprecated: use Misplaced Function (C150), configured via "
            "rules.misplaced_function. This rule remains available with its "
            "original ItemSkip-only behavior, but is disabled by default and "
            "is skipped with a warning whenever C150 is active, so the same "
            "ItemSkip is never reported twice. Selecting C130 (or its alias "
            "S120) explicitly still runs it.\n\n"
            "Enforces that ItemSkip() is only used in metadata or data sections "
            "of TM1 TI processes.\n\n"
            "TM1 TI processes have four execution blocks:\n"
            "- Prolog: Executes once before processing records\n"
            "- Metadata: Processes dimension metadata records\n"
            "- Data: Processes cube data records\n"
            "- Epilog: Executes once after all records\n\n"
            "ItemSkip() skips the current record, which only makes sense in Metadata "
            "and Data sections. Using it in Prolog or Epilog is a logic error."
        ),
        config_example=(
            "rules:\n"
            "  item_skip:\n"
            "    # Deprecated: prefer rules.misplaced_function (C150), which\n"
            "    # takes precedence whenever both rules are active.\n"
            "    enabled: true"
        ),
        examples=[
            RuleExample(
                code="# In Metadata/Data section\nIF (nValue = 0);\n    ItemSkip();\nENDIF;",
                description="ItemSkip in Metadata/Data",
                valid=True,
            ),
            RuleExample(
                code="# In Prolog section\nItemSkip();",
                description="ItemSkip in Prolog",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "C130"

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context: LintContext):
        """Check if an ExpressionStatement is an ItemSkip() call in a forbidden block."""
        expr = statement.expression
        if not (isinstance(expr, FunctionCall) and expr.name.lower() == "itemskip"):
            return []

        if context.block not in ["prolog", "epilog"]:
            return []

        token = get_node_token(expr)
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )

        return [
            LintIssue(
                message=f"ItemSkip() is not allowed in {context.block} section. Use it only in metadata or data sections",
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]
