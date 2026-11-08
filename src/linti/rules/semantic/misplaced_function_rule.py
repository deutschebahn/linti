"""C150: TurboIntegrator function calls in a section IBM documents as invalid."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import EXPRESSION_CARRYING_STATEMENTS, get_node_token
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.rules.semantic.function_placement import (
    PROCEDURE_SECTIONS,
    Placement,
    iter_placements,
    join_or,
    valid_sections,
)


class MisplacedFunctionRule(BaseStatementRule):
    """Report calls in a section they are not allowed in."""

    CONFIG_KEY = "misplaced_function"
    METADATA = RuleMetadata(
        name="Invalid Function Placement",
        description="Detects TI functions used in a procedure section where they are not allowed",
        explanation=(
            "Checks function calls against the Prolog, Metadata, Data and Epilog "
            "sections and reports a placement the IBM function reference "
            "documents as invalid. Valid placement produces no diagnostic.\n\n"
            "- DimensionElementInsert / HierarchyElementInsert: valid in "
            "Prolog/Metadata; invalid in Data/Epilog.\n"
            "- DimensionElementComponentAdd / HierarchyElementComponentAdd: "
            "valid in Prolog/Metadata/Data; invalid in Epilog.\n"
            "- DisableBulkLoadMode: valid in the Epilog; invalid in "
            "Prolog/Metadata/Data, because bulk load mode has to stay on for "
            "the whole process. IBM asks for it in the Epilog's last line; "
            "that position is not checked.\n"
            '- AddInfoCubeRestriction: valid in the Prolog only (IBM: "must be '
            'placed in the Prolog").\n'
            "- DisableMTQViewConstruct: invalid in Metadata/Data. IBM wants it "
            "in the Prolog, where it is the only place it has an effect, or, "
            "after EnableMTQViewConstruct, on the Epilog's last line; that "
            "position is not checked.\n"
            "- Dimension and Hierarchy Direct functions: ElementInsertDirect, "
            "ElementDeleteDirect, ElementComponentAddDirect, "
            "ElementComponentDeleteDirect and TopElementInsertDirect are "
            "unrestricted in all four sections. IBM describes "
            "direct edits during Data loads; they do not inherit the "
            "non-Direct functions' restrictions.\n"
            "- ItemSkip: valid in Metadata/Data; invalid in Prolog/Epilog.\n\n"
            "Restrictions are function-specific. ElementDelete, "
            "ElementComponentDelete and TopElementInsert are not automatically "
            "restricted like ElementInsert. See docs/function-placement.md "
            "for the IBM sources.\n\n"
            "Placements that are only discouraged (for example attribute writes "
            "in Metadata, security changes in Data/Epilog, once-per-process "
            "operations in Metadata/Data) are reported as warnings by "
            "Discouraged Function Placement (C151), which shares this rule's "
            "placement table. `--select C15` runs both. Before C151 existed, "
            "this rule reported those recommendations as errors; a "
            "`# noqa: C150` no longer suppresses them, use `# noqa: C151`.\n\n"
            "Function matching is case-insensitive. Unknown functions and code "
            "without a known procedure section are not reported. Calls inside "
            "expressions and nested control flow are checked too. Statements the "
            "parser could not read are skipped.\n\n"
            "allowed_functions lists functions to exempt from the check in "
            "every section, for a placement this project disagrees with. "
            "C151 falls back to this list when it sets none of its own.\n\n"
            "Supersedes ItemSkip Block Usage (C130), which is disabled by "
            "default and skipped with a warning whenever this rule is active, so "
            "the same ItemSkip is never reported twice. Selecting C130 (or its "
            "alias S120) explicitly still runs the legacy ItemSkip-only rule with "
            "its own rules.item_skip settings."
        ),
        config_example=(
            "rules:\n"
            "  misplaced_function:\n"
            "    enabled: true\n"
            "    # Functions to exempt from the placement check entirely.\n"
            "    allowed_functions: []"
        ),
        examples=[
            RuleExample(
                code="DimensionElementInsert('Product', '', vProduct, 'N');",
                description="Metadata: create the element",
                procedure="metadata",
            ),
            RuleExample(
                code="DimensionElementInsertDirect('Product', '', vProduct, 'N');",
                description="Data: the Direct variant has no section restriction",
                procedure="data",
            ),
            RuleExample(
                code="DisableBulkLoadMode();",
                description="Epilog: leave bulk load mode when the process ends",
                procedure="epilog",
            ),
            RuleExample(
                code="ItemSkip();",
                description="Prolog: invalid placement",
                valid=False,
            ),
            RuleExample(
                code="DimensionElementInsert('Product', '', vProduct, 'N');",
                description="Data: invalid placement",
                valid=False,
                procedure="data",
            ),
            RuleExample(
                code="DisableBulkLoadMode();",
                description="Data: invalid placement",
                valid=False,
                procedure="data",
            ),
            RuleExample(
                code="AddInfoCubeRestriction('Sales', 'Version', 'Actual');",
                description="Metadata: IBM requires the Prolog",
                valid=False,
                procedure="metadata",
            ),
        ],
    )

    def __init__(self, allowed_functions: list[str] | None = None):
        """
        Args:
            allowed_functions: Functions to exempt from the check in every
                section, for a placement this project disagrees with. Matched
                case-insensitively, like the table itself.
        """
        self._allowed = {name.strip().lower() for name in allowed_functions or []}

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [cls(allowed_functions=rule_cfg.get("allowed_functions") or [])]

    @property
    def RULE_ID(self) -> str:
        return "C150"

    def interested_in(self):
        return list(EXPRESSION_CARRYING_STATEMENTS)

    def visit(self, statement, context: LintContext):
        section = (context.block or "").lower()
        if section not in PROCEDURE_SECTIONS:
            return []

        issues = []
        for call, placements in iter_placements(
            statement, section, Placement.INVALID, self._allowed
        ):
            message = f"{call.name} is not allowed in {section.title()}."
            valid = valid_sections(placements)
            if valid:
                message += f" Use it in {join_or(valid)}."
            token = get_node_token(call)
            issues.append(
                LintIssue(
                    message=message,
                    line=token.line if token else 0,
                    column=token.column if token else 0,
                    position=token.position if token else 0,
                    rule_id=self.RULE_ID,
                )
            )
        return issues
