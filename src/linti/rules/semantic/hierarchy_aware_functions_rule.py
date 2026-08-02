"""Rule C410 – Use hierarchy-aware functions.

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
from linti.parser.ast import (
    Assignment,
    BinaryExpression,
    ExpressionStatement,
    FunctionCall,
    Identifier,
    IfStatement,
    String,
    WhileStatement,
    get_node_token,
    iter_expression_nodes,
    statement_expression,
)
from linti.rules.generic_process import is_generic_process
from linti.rules.Rule import BaseTokenRule, BaseStatementRule, RuleExample, RuleMetadata

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


class UseHierarchyAwareFunctionsRule(BaseTokenRule):
    """Enforces consistent usage of hierarchy-aware functions."""

    CONFIG_KEY = "use_hierarchy_aware_functions"
    DEPRECATED_IDS = ["S410"]
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
            "Independently of the mode, a standard function whose dimension "
            "argument provably addresses a hierarchy ('Dimension:Hierarchy') is "
            "reported — whether the colon comes from a string literal, a literal "
            "concatenation (sDim | ':' | sHier), or a variable with a statically "
            "known branch variant that contains a colon (a single reachable path "
            "already addresses a hierarchy there, even if other branches don't). "
            "In enforce mode the call is already reported by name, so this extra "
            "check adds signal in consistent mode. Unknown/dynamic values are "
            "never reported.\n\n"
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
            RuleExample(
                code="nExists = DimensionElementExists('Region:Detail', 'EMEA');",
                description=(
                    "dimension argument addresses a hierarchy; use "
                    "HierarchyElementExists with an explicit hierarchy"
                ),
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
        return "C410"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        mode = rule_cfg.get("mode", "consistent")
        generic_prefixes = rule_cfg.get("generic_prefixes", [])
        # The colon-argument check is an AST/value-based companion sharing this
        # rule's id, config and enabled flag (see _HierarchyColonArgumentRule).
        return [
            cls(mode=mode, generic_prefixes=generic_prefixes),
            _HierarchyColonArgumentRule(mode=mode, generic_prefixes=generic_prefixes),
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


class _HierarchyColonArgumentRule(BaseStatementRule):
    """C410 companion: a standard hierarchy function fed a ``Dimension:Hierarchy``.

    A standard (non hierarchy-aware) function expects a plain dimension name; a
    colon-bearing value belongs in a hierarchy-aware function with an explicit
    hierarchy argument.  The colon is reported only when it is provably present
    on at least one reachable path (string literal, literal concatenation, or a
    variable with a statically known branch variant that contains one), so
    unknown/dynamic values never produce a finding.

    This class is intentionally not registered (empty ``CONFIG_KEY``); it is
    created by :meth:`UseHierarchyAwareFunctionsRule.from_config`, sharing C410's
    id, config and enabled flag.  It stays silent when the effective mode is
    ``enforce`` (generic processes included), because there the standard call is
    already reported by name.
    """

    CONFIG_KEY = ""

    def __init__(
        self, mode: str = "consistent", generic_prefixes: Optional[list[str]] = None
    ) -> None:
        self.mode = mode.lower()
        self._generic_prefixes: list[str] = generic_prefixes or []

    @property
    def RULE_ID(self) -> str:
        return "C410"

    def interested_in(self):
        return [Assignment, ExpressionStatement, IfStatement, WhileStatement]

    def visit(self, statement, context: LintContext):
        # In enforce mode (and for generic processes) the standard function is
        # already reported by name — avoid a duplicate finding.
        if is_generic_process(context.process_name, self._generic_prefixes):
            return []
        if self.mode != "consistent":
            return []

        expr = statement_expression(statement)
        if expr is None:
            return []

        issues: list[LintIssue] = []
        for node in iter_expression_nodes(expr):
            if not isinstance(node, FunctionCall):
                continue
            aware = LEGACY_TO_AWARE.get(node.name.lower())
            if aware is None:
                continue
            arg = node.args[0] if node.args else None
            if arg is None or not self._addresses_hierarchy(arg, context):
                continue

            token = get_node_token(node)
            line, column, position = (
                (token.line, token.column, token.position) if token else (0, 0, 0)
            )
            issues.append(
                LintIssue(
                    rule_id=self.RULE_ID,
                    message=(
                        f"'{node.name}' addresses a hierarchy "
                        "('Dimension:Hierarchy') in its dimension argument; use "
                        f"'{aware}' with an explicit hierarchy instead"
                    ),
                    line=line,
                    column=column,
                    position=position,
                )
            )
        return issues

    def _addresses_hierarchy(self, arg, context: LintContext) -> bool:
        # A literal colon anywhere in the argument expression is certain to be
        # present — covers 'Dim:Hier' and sDim | ':' | sHier.
        for node in iter_expression_nodes(arg):
            if isinstance(node, String) and ":" in node.value:
                return True
        return self._provably_contains_colon(arg, context)

    def _provably_contains_colon(self, node, context: LintContext) -> bool:
        """True when *node* is provably known to contain a colon on at least
        one reachable path.

        Covers a bare variable with a statically known branch variant that
        contains one, and a ``|`` concatenation where at least one operand
        alone is provably known to — concatenating anything else around a
        colon-bearing part can't remove it, so the check recurses through the
        chain rather than needing the whole expression to fold to one known
        value. A single call site reached with a colon-bearing value on any
        path is already addressing a hierarchy there, regardless of what
        other branches pass instead.
        """
        if isinstance(node, Identifier):
            token = get_node_token(node)
            line = token.line if token else 0
            return context.possible_values(node.name, line).any_contains(":")
        if isinstance(node, BinaryExpression) and node.operator.type is TokenType.PIPE:
            return self._provably_contains_colon(
                node.left, context
            ) or self._provably_contains_colon(node.right, context)
        return False
