"""Rule S410 – Use hierarchy-aware functions.

TM1 exposes two families of element/hierarchy functions:

* **Hierarchy-aware** functions take an explicit hierarchy argument
  (``HierarchyElementExists``, ``ElementParent``, …).
* **Standard / same-named** functions implicitly operate on the dimension's
  default (principal) hierarchy (``DimensionElementExists``, ``ELPAR``, …).

Mixing both styles makes hierarchy behaviour ambiguous and hard to maintain.
This rule supports two modes:

* ``enforce`` – only hierarchy-aware functions are allowed; any standard
  function is reported with its hierarchy-aware replacement.
* ``consistent`` – either style may be used, but mixing both within the same
  file is reported.
"""

from typing import Optional

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.rules.generic_process import is_generic_process
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata

#: Maps a standard/legacy function (lower-cased) to its hierarchy-aware
#: replacement (canonical casing).  Covers TI functions and Rules functions
#: that are also valid in TI.
LEGACY_TO_AWARE: dict[str, str] = {
    # DimensionElement* -> HierarchyElement*
    "dimensionelementinsert": "HierarchyElementInsert",
    "dimensionelementinsertdirect": "HierarchyElementInsertDirect",
    "dimensionelementdelete": "HierarchyElementDelete",
    "dimensionelementdeletedirect": "HierarchyElementDeleteDirect",
    "dimensionelementcomponentadd": "HierarchyElementComponentAdd",
    "dimensionelementcomponentadddirect": "HierarchyElementComponentAddDirect",
    "dimensionelementcomponentdelete": "HierarchyElementComponentDelete",
    "dimensionelementcomponentdeletedirect": "HierarchyElementComponentDeleteDirect",
    "dimensionelementexists": "HierarchyElementExists",
    "dimensionelementprincipalname": "HierarchyElementPrincipalName",
    "dimensionsortorder": "HierarchySortOrder",
    "dimensiontopelementinsert": "HierarchyTopElementInsert",
    "dimensiontopelementinsertdirect": "HierarchyTopElementInsertDirect",
    # Special case
    "dimensiondeleteallelements": "HierarchyDeleteAllElements",
    # Rules functions valid in TI
    "ellev": "ElementLevel",
    "elpar": "ElementParent",
    "elparn": "ElementParentCount",
    "elcomp": "ElementComponent",
    "elcompn": "ElementComponentCount",
    "eliscomp": "ElementIsComponent",
    "elispar": "ElementIsParent",
    "elisanc": "ElementIsAncestor",
    "elweight": "ElementWeight",
    "dimix": "ElementIndex",
}

#: Lower-cased names of all hierarchy-aware functions (the replacement column).
AWARE_FUNCTIONS: frozenset[str] = frozenset(
    name.lower() for name in LEGACY_TO_AWARE.values()
)

_STANDARD = "standard"
_AWARE = "aware"

# Sentinel distinct from any real (or ``None``) process name, so the very first
# visit always initialises the per-file consistency state.
_UNSET = object()


class UseHierarchyAwareFunctionsRule(BaseRule):
    """Enforces consistent usage of hierarchy-aware functions."""

    CONFIG_KEY = "use_hierarchy_aware_functions"
    METADATA = RuleMetadata(
        name="Use Hierarchy-Aware Functions",
        description=(
            "Enforces hierarchy-aware functions, or at least consistent usage of "
            "hierarchy-aware vs. standard hierarchy functions"
        ),
        auto_fix=False,
        explanation=(
            "TM1 offers hierarchy-aware functions (e.g. HierarchyElementExists, "
            "ElementParent) that take an explicit hierarchy, alongside standard "
            "functions (e.g. DimensionElementExists, ELPAR) that implicitly use a "
            "dimension's default hierarchy.\n\n"
            "Modes:\n"
            "- enforce: only hierarchy-aware functions are allowed; standard "
            "functions are reported with their hierarchy-aware replacement.\n"
            "- consistent: either style is allowed, but mixing both within the "
            "same file is reported.\n\n"
            "Generic processes (whose names start with a configured "
            "``generic_prefixes`` entry) are always held to the stricter "
            "``enforce`` mode, regardless of the base ``mode``.\n\n"
            "Covers both TI functions and Rules functions that are valid in TI."
        ),
        config_example=(
            "# Generic processes (top-level setting) are always enforced\n"
            "generic_prefixes:\n"
            "  - '}core.'\n"
            "rules:\n"
            "  use_hierarchy_aware_functions:\n"
            "    enabled: true\n"
            "    # base mode: 'enforce' or 'consistent'\n"
            "    mode: consistent"
        ),
        examples=[
            RuleExample(
                code="nExists = HierarchyElementExists('Region', 'Region', 'EMEA');",
                description="hierarchy-aware function (valid in any mode)",
                valid=True,
            ),
            RuleExample(
                code="nExists = DimensionElementExists('Region', 'EMEA');",
                description="enforce mode: standard function (use HierarchyElementExists)",
                valid=False,
            ),
            RuleExample(
                code=(
                    "nParent = ElementParent('Region', 'Region', 'EMEA');\n"
                    "nIndex = DIMIX('Region', 'EMEA');"
                ),
                description="consistent mode: mixes hierarchy-aware and standard styles",
                valid=False,
            ),
        ],
    )

    def __init__(
        self, mode: str = "consistent", generic_prefixes: Optional[list[str]] = None
    ) -> None:
        self.mode = mode.lower()
        self._generic_prefixes: list[str] = generic_prefixes or []
        self._reset_file_state()

    @property
    def RULE_ID(self) -> str:
        return "S410"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [
            cls(
                mode=rule_cfg.get("mode", "consistent"),
                generic_prefixes=rule_cfg.get("generic_prefixes", []),
            )
        ]

    def _reset_file_state(self) -> None:
        # Consistency tracking spans the whole file (all procedures). It is keyed
        # on the process name in visit() rather than cleared by reset(), because
        # reset() runs once per procedure while a "file" is one process with
        # several procedures.
        self._current_process = _UNSET
        self._first_standard: Optional[object] = None
        self._first_aware: Optional[object] = None
        self._mix_reported = False

    def interested_in(self):
        return [TokenType.IDENTIFIER]

    def visit(self, token, window, context: LintContext):
        # Only treat an identifier as a function call when followed by '('.
        nxt = window.next_non_ws()
        if nxt is None or nxt.type != TokenType.LPAREN:
            return []

        key = token.value.lower()
        if self._effective_mode(context) == "enforce":
            return self._visit_enforce(key, token)
        return self._visit_consistent(key, token, context)

    def _effective_mode(self, context: LintContext) -> str:
        """Resolve the mode for the current process.

        Generic processes are always held to ``enforce``; everything else uses
        the configured base ``mode``.
        """
        if is_generic_process(context.process_name, self._generic_prefixes):
            return "enforce"
        return self.mode

    def _visit_enforce(self, key: str, token) -> list[LintIssue]:
        aware = LEGACY_TO_AWARE.get(key)
        if aware is None:
            return []
        return [
            LintIssue(
                rule_id=self.RULE_ID,
                message=(
                    f"'{token.value}' is not hierarchy-aware; use '{aware}' instead"
                ),
                line=token.line,
                column=token.column,
                position=token.position,
            )
        ]

    def _visit_consistent(
        self, key: str, token, context: LintContext
    ) -> list[LintIssue]:
        if context.process_name != self._current_process:
            self._reset_file_state()
            self._current_process = context.process_name

        if key in LEGACY_TO_AWARE:
            style = _STANDARD
        elif key in AWARE_FUNCTIONS:
            style = _AWARE
        else:
            return []

        if style == _STANDARD and self._first_standard is None:
            self._first_standard = token
        elif style == _AWARE and self._first_aware is None:
            self._first_aware = token

        if (
            self._mix_reported
            or self._first_standard is None
            or self._first_aware is None
        ):
            return []

        self._mix_reported = True
        standard_name = self._first_standard.value
        aware_name = self._first_aware.value
        suggestion = LEGACY_TO_AWARE.get(standard_name.lower())
        hint = (
            f" (e.g. replace '{standard_name}' with '{suggestion}')"
            if suggestion
            else ""
        )
        return [
            LintIssue(
                rule_id=self.RULE_ID,
                message=(
                    "File mixes hierarchy-aware and standard hierarchy functions: "
                    f"'{standard_name}' and '{aware_name}'; use one style"
                    f" consistently{hint}"
                ),
                line=token.line,
                column=token.column,
                position=token.position,
            )
        ]
