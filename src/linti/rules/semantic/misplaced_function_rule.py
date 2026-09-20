"""C150: procedure placement of TurboIntegrator function calls."""

from enum import Enum

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    EXPRESSION_CARRYING_STATEMENTS,
    get_node_token,
    iter_function_calls,
    statement_expression,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata


class Placement(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NOT_RECOMMENDED = "not_recommended"


PROCEDURE_SECTIONS = ("prolog", "metadata", "data", "epilog")

# Unlisted functions and missing sections are unrestricted. Match exact names:
# a Direct variant must never inherit restrictions from its non-Direct sibling.
# IBM sources and the reasoning behind each family are in
# docs/function-placement.md (reviewed 2026-09-20).
FUNCTION_PLACEMENTS: dict[str, dict[str, Placement]] = {
    # IBM explicitly excludes Data and Epilog for these two insert functions.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.INVALID,
            "epilog": Placement.INVALID,
        }
        for name in ("dimensionelementinsert", "hierarchyelementinsert")
    },
    # ComponentAdd documents only an Epilog exclusion, not a Data exclusion.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.VALID,
            "epilog": Placement.INVALID,
        }
        for name in ("dimensionelementcomponentadd", "hierarchyelementcomponentadd")
    },
    # Bulk load mode has to stay on for the whole process, so the disable call
    # belongs in the Epilog. Whether it is that section's *last* statement is
    # not checked: the position would need its own section-wide analysis, and
    # bulk load mode only exists on v11.
    "disablebulkloadmode": {
        "prolog": Placement.INVALID,
        "metadata": Placement.INVALID,
        "data": Placement.INVALID,
        "epilog": Placement.VALID,
    },
    # Advisory, not an IBM prohibition: write attributes after the Metadata
    # pass commits newly created elements. Existing elements can be updated
    # in Metadata, so this remains suppressible via report_not_recommended.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.NOT_RECOMMENDED,
            "data": Placement.VALID,
            "epilog": Placement.VALID,
        }
        for name in ("attrputs", "attrputn", "elementattrputs", "elementattrputn")
    },
    # Administrative changes belong in the setup pass. Running them per record
    # (Data) or after the load (Epilog) is not an IBM prohibition, but it
    # rebuilds security objects while the process is still holding them.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.NOT_RECOMMENDED,
            "epilog": Placement.NOT_RECOMMENDED,
        }
        for name in (
            "addclient",
            "deleteclient",
            "addgroup",
            "deletegroup",
            "cellsecuritycubecreate",
            "cellsecuritycubedestroy",
        )
    },
    # Direct edits act on the actual dimension; IBM explicitly describes Data
    # loads with an empty Metadata section. No blanket Metadata warning or
    # Data/Epilog ban is documented. UpdateDirect can follow the direct edits
    # whenever compaction is needed; it is not restricted to Epilog.
    **{
        name: dict.fromkeys(PROCEDURE_SECTIONS, Placement.VALID)
        for name in (
            "dimensionelementinsertdirect",
            "dimensionelementdeletedirect",
            "dimensionelementcomponentadddirect",
            "dimensionelementcomponentdeletedirect",
            "dimensiontopelementinsertdirect",
            "dimensionupdatedirect",
            "hierarchyelementinsertdirect",
            "hierarchyelementdeletedirect",
            "hierarchyelementcomponentadddirect",
            "hierarchyelementcomponentdeletedirect",
            "hierarchytopelementinsertdirect",
            "hierarchyupdatedirect",
        )
    },
    "itemskip": {
        "prolog": Placement.INVALID,
        "metadata": Placement.VALID,
        "data": Placement.VALID,
        "epilog": Placement.INVALID,
    },
}


def _valid_sections(placements: dict[str, Placement]) -> str:
    """Where the function does belong, as a readable list of sections."""
    return ", ".join(
        name.title()
        for name in PROCEDURE_SECTIONS
        if placements.get(name, Placement.VALID) is Placement.VALID
    )


class MisplacedFunctionRule(BaseStatementRule):
    """Report calls in a section they do not belong in."""

    CONFIG_KEY = "misplaced_function"
    METADATA = RuleMetadata(
        name="Misplaced Function",
        description="Detects TI functions used in invalid or not recommended procedure sections",
        explanation=(
            "Checks function calls against the Prolog, Metadata, Data and Epilog "
            "sections. Both a placement IBM documents as invalid and one this "
            "project does not recommend are reported; valid placement produces "
            "no diagnostic.\n\n"
            "- DimensionElementInsert / HierarchyElementInsert: valid in "
            "Prolog/Metadata; invalid in Data/Epilog.\n"
            "- DimensionElementComponentAdd / HierarchyElementComponentAdd: "
            "valid in Prolog/Metadata/Data; invalid in Epilog.\n"
            "- DisableBulkLoadMode: valid in the Epilog; invalid in "
            "Prolog/Metadata/Data, because bulk load mode has to stay on for "
            "the whole process. IBM asks for it in the Epilog's last line; "
            "that position is not checked.\n"
            "- AttrPutS / AttrPutN / ElementAttrPutS / ElementAttrPutN: valid in "
            "Prolog/Data/Epilog; not recommended in Metadata. This is an "
            "advisory recommendation, not an IBM prohibition: write attributes "
            "after newly created elements have been committed.\n"
            "- AddClient / DeleteClient / AddGroup / DeleteGroup / "
            "CellSecurityCubeCreate / CellSecurityCubeDestroy: valid in "
            "Prolog/Metadata; not recommended in Data/Epilog, where "
            "administrative changes run per record or after the load.\n"
            "- Dimension and Hierarchy Direct functions: ElementInsertDirect, "
            "ElementDeleteDirect, ElementComponentAddDirect, "
            "ElementComponentDeleteDirect, TopElementInsertDirect and "
            "UpdateDirect are unrestricted in all four sections. IBM describes "
            "direct edits during Data loads; they do not inherit the "
            "non-Direct functions' restrictions.\n"
            "- ItemSkip: valid in Metadata/Data; invalid in Prolog/Epilog.\n\n"
            "Restrictions are function-specific. ElementDelete, "
            "ElementComponentDelete and TopElementInsert are not automatically "
            "restricted like ElementInsert. See docs/function-placement.md "
            "for the IBM sources and the distinction between documented "
            "restrictions and LinTi recommendations.\n\n"
            "Function matching is case-insensitive. Unknown functions and code "
            "without a known procedure section are not reported. Calls inside "
            "expressions and nested control flow are checked too. Statements the "
            "parser could not read are skipped.\n\n"
            "Findings fail the run like any other error. Two settings narrow "
            "the rule instead of switching it off wholesale:\n"
            "- report_not_recommended: false reports only the documented "
            "restrictions. Use it when the recommendations do not match how "
            "the project loads its data.\n"
            "- allowed_functions lists functions to exempt from the check in "
            "every section, for a placement this project disagrees with.\n\n"
            "rules.misplaced_function.severity reweighs the whole rule, as "
            "everywhere else.\n\n"
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
            "    # Set to false to report only the documented restrictions,\n"
            "    # keeping the recommendations out of the report.\n"
            "    report_not_recommended: true\n"
            "    # Functions to exempt from the placement check entirely.\n"
            "    allowed_functions: []"
        ),
        examples=[
            RuleExample(
                code="DimensionElementInsert('Product', '', vProduct, 'N');",
                description="Metadata: create the element",
            ),
            RuleExample(
                code="AttrPutS(vDescription, 'Product', vProduct, 'Description');",
                description="Data: write the attribute after Metadata completes",
            ),
            RuleExample(
                code="DisableBulkLoadMode();",
                description="Epilog: leave bulk load mode when the process ends",
            ),
            RuleExample(
                code="ItemSkip();",
                description="Prolog: invalid placement",
                valid=False,
            ),
            RuleExample(
                code="DisableBulkLoadMode();",
                description="Data: invalid placement",
                valid=False,
            ),
            RuleExample(
                code="AttrPutS(vDescription, 'Product', vProduct, 'Description');",
                description="Metadata: not recommended placement",
                valid=False,
            ),
        ],
    )

    def __init__(
        self,
        allowed_functions: list[str] | None = None,
        report_not_recommended: bool = True,
    ):
        """
        Args:
            allowed_functions: Functions to exempt from the check in every
                section, for a placement this project disagrees with. Matched
                case-insensitively, like the table itself.
            report_not_recommended: Whether the recommendation level is reported
                at all. ``False`` keeps only invalid placement, so a project can
                drop the advisory findings without losing the errors.
        """
        self._allowed = {name.strip().lower() for name in allowed_functions or []}
        self._report_not_recommended = report_not_recommended

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [
            cls(
                allowed_functions=rule_cfg.get("allowed_functions") or [],
                report_not_recommended=rule_cfg.get("report_not_recommended", True),
            )
        ]

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
        for call in iter_function_calls(statement_expression(statement)):
            func_name = call.name.lower()
            placements = FUNCTION_PLACEMENTS.get(func_name)
            if placements is None or func_name in self._allowed:
                continue
            # A section the table leaves out carries no restriction, so an
            # incomplete entry stays a silent no-op instead of a KeyError.
            placement = placements.get(section, Placement.VALID)
            if placement is Placement.VALID:
                continue
            if placement is Placement.NOT_RECOMMENDED and (
                not self._report_not_recommended
            ):
                continue

            if placement is Placement.INVALID:
                message = (
                    f"Function '{call.name}' is not allowed in the {section.title()} "
                    f"section. Use it in these sections instead: "
                    f"{_valid_sections(placements)}."
                )
            else:
                message = (
                    f"Function '{call.name}' is not recommended in the "
                    f"{section.title()} section. Recommended sections: "
                    f"{_valid_sections(placements)}."
                )

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
