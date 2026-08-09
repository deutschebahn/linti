"""Rule C510 – Function version compatibility (PA/TM1 v11 vs v12).

Some TurboIntegrator functions exist only in Planning Analytics / TM1 v11 and
are unsupported in v12; others were introduced in v12 and do not exist in v11.
Depending on the deployment target, a developer may need to restrict which
functions their code uses.  This rule reports calls that violate a chosen
compatibility target.

Modes:

* ``CompatibleWithV11AndV12`` – only functions available in *both* versions are
  allowed; any version-specific function is reported.
* ``V11`` – v11 functions are allowed; functions introduced in v12 are reported.
* ``V12`` – v12 functions are allowed; functions removed/unsupported in v12 are
  reported.

Function names come from IBM's PA 3.1 documentation (deprecated features and new
capabilities in the TM1 database).  Matching is case-insensitive.

The rule inspects the AST rather than the token stream because TI makes the
parentheses optional on a no-argument call: ``SaveDataAll;`` and
``SaveDataAll();`` are the same call, and the parser already normalises both to
a ``FunctionCall`` node while leaving a plain variable read (``nX = JsonGet + 2``)
alone.
"""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    EXPRESSION_CARRYING_STATEMENTS,
    UnknownStatement,
    get_node_token,
    iter_function_calls,
    statement_expression,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

#: Functions available in v11 but NOT supported in TM1/PA v12 (deprecated).
V11_ONLY_FUNCTIONS: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "AddInfoCubeRestriction",
        "AllowExternalRequests",
        "AssignClientPassword",
        "AssociateCAMIDToGroup",
        "BatchCellIncrement",
        "BatchUpdateFinish",
        "BatchUpdateFinishWait",
        "BatchUpdateStart",
        "CGAddPromptValues",
        "CGPromptGetNextMember",
        "CGPromptSize",
        "CreateHierarchyByAttribute",
        "CubeDataReservationAcquire",
        "CubeDataReservationGet",
        "CubeDataReservationGetConflicts",
        "CubeDataReservationRelease",
        "CubeDataReservationReleaseAll",
        "CubeGetLogChanges",
        "CubeSaveData",
        "CubeSetConnParams",
        "CubeSetLogChanges",
        "CubeUnload",
        "DisableBulkLoadMode",
        "EnableBatchCellIncrement",
        "EnableBulkLoadMode",
        "ExecuteCommand",
        "ExecuteJavaN",
        "ExecuteJavaS",
        "LockOff",
        "LockOn",
        "RefreshMDXHierarchy",
        "RemoveCAMIDAssociation",
        "RemoveCAMIDAssociationFromGroup",
        "SaveDataAll",
        "ServerShutdown",
        "SetChoreVerboseMessages",
        "SetOdbcUnicodeInterface",
        "SwapAliasWithPrincipalName",
    )
)

#: Functions introduced in TM1/PA v12 that do NOT exist in v11.
V12_ONLY_FUNCTIONS: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # HTTP request functions (ExecuteCommand's v12 replacement family)
        "ExecuteHttpRequest",
        "HttpResponseGetBody",
        "HttpResponseGetHeader",
        "HttpResponseGetStatusCode",
        # JSON functions
        "JsonAdd",
        "JsonCopy",
        "JsonDiff",
        "JsonGet",
        "JsonGetKey",
        "JsonMergePatch",
        "JsonMove",
        "JsonPatch",
        "JsonRemove",
        "JsonReplace",
        "JsonSize",
        "JsonTest",
        "JsonToString",
        "JsonType",
        "JsonValidate",
        "StringToJson",
        # JSON Web Token functions
        "JwtCreate",
        "JwtDecode",
        "JwtVerify",
        # Job control
        "CancelJobs",
        "GetJobStatus",
        # Table handle
        "ReturnTableHandle",
    )
)

# Canonical mode identifiers (compared case-insensitively).
_MODE_COMPATIBLE = "compatiblewithv11andv12"
_MODE_V11 = "v11"
_MODE_V12 = "v12"
_DEFAULT_MODE = _MODE_COMPATIBLE

#: Accepted spellings (case-insensitive) mapped to a canonical mode. Covers both
#: the rule's own ``mode`` values and the top-level ``target_version`` vocabulary
#: (``both`` == run on v11 and v12), so either config path resolves the same way.
_MODE_ALIASES = {
    _MODE_COMPATIBLE: _MODE_COMPATIBLE,
    "both": _MODE_COMPATIBLE,
    _MODE_V11: _MODE_V11,
    _MODE_V12: _MODE_V12,
}

# The two version-specific function families.
_V11_ONLY = "v11-only"
_V12_ONLY = "v12-only"

#: The functions making up each family. A function in neither exists in both
#: versions and is never reported.
_FUNCTIONS_BY_FAMILY: dict[str, frozenset[str]] = {
    _V11_ONLY: V11_ONLY_FUNCTIONS,
    _V12_ONLY: V12_ONLY_FUNCTIONS,
}

#: How each mode phrases a finding, keyed by (mode, family). A pair that is
#: absent means the mode allows that family — there is no "allowed" sentinel to
#: check. ``{name}`` is filled with the call's original casing.
_MESSAGES: dict[tuple[str, str], str] = {
    (_MODE_COMPATIBLE, _V11_ONLY): (
        "'{name}' is only available in PA/TM1 v11 (unsupported in v12); "
        "avoid it for code that must run on both versions"
    ),
    (_MODE_COMPATIBLE, _V12_ONLY): (
        "'{name}' is only available in PA/TM1 v12 (does not exist in v11); "
        "avoid it for code that must run on both versions"
    ),
    (_MODE_V11, _V12_ONLY): (
        "'{name}' was introduced in PA/TM1 v12 and is not available in v11"
    ),
    (_MODE_V12, _V11_ONLY): (
        "'{name}' is not supported in PA/TM1 v12 (deprecated in v11)"
    ),
}


def _templates_for_mode(mode: str) -> dict[str, str]:
    """Flatten the (mode, family) spec above into a name -> message map.

    Built once per rule instance so each visited call costs a single lookup.
    A function the mode allows — because it exists in both versions, or because
    its family is not reported in this mode — is simply absent from the result.
    """
    templates: dict[str, str] = {}
    for family, names in _FUNCTIONS_BY_FAMILY.items():
        template = _MESSAGES.get((mode, family))
        if template is None:
            continue  # this mode allows the whole family
        templates.update(dict.fromkeys(names, template))
    return templates


class FunctionVersionCompatibilityRule(BaseStatementRule):
    """Reports function calls incompatible with a target PA/TM1 version."""

    CONFIG_KEY = "function_version_compatibility"
    # Opt-in: the compatibility target depends on the deployment strategy, so
    # the rule stays silent until a user enables it and picks a mode.
    DEFAULT_ENABLED = False
    METADATA = RuleMetadata(
        name="Function Version Compatibility",
        description=(
            "Reports TurboIntegrator functions incompatible with a target "
            "Planning Analytics / TM1 version (v11, v12, or both)"
        ),
        auto_fix=False,
        explanation=(
            "Some TI functions exist only in PA/TM1 v11 and are unsupported in "
            "v12; others were introduced in v12 and do not exist in v11. This "
            "rule reports calls that break a chosen compatibility target.\n\n"
            "Modes:\n"
            "- CompatibleWithV11AndV12: only functions available in both "
            "versions are allowed; any version-specific function is reported.\n"
            "- V11: v11 functions are allowed; functions introduced in v12 are "
            "reported.\n"
            "- V12: v12 functions are allowed; functions removed or unsupported "
            "in v12 are reported.\n\n"
            "Matching is case-insensitive, and calls are found wherever they "
            "appear — including inside IF/WHILE conditions and nested arguments. "
            "Because TI makes the parentheses optional on a no-argument call, "
            "`SaveDataAll;` is reported just like `SaveDataAll();`.\n\n"
            "The target version is normally set once via the top-level "
            "`target_version` (v11 | v12 | both) so other version-aware rules can "
            "share it; the per-rule `mode` overrides it when present."
        ),
        config_example=(
            "# Project-wide target, shared by version-aware rules:\n"
            "target_version: both  # v11 | v12 | both\n"
            "rules:\n"
            "  function_version_compatibility:\n"
            "    enabled: true\n"
            "    # Optional per-rule override of target_version:\n"
            "    # mode: CompatibleWithV11AndV12  # | V11 | V12"
        ),
        examples=[
            RuleExample(
                code="nStatus = GetJobStatus(nJobId);",
                description="V11 mode: GetJobStatus was introduced in v12",
                valid=False,
            ),
            RuleExample(
                code="CubeSaveData('Sales');",
                description="V12 mode: CubeSaveData is not supported in v12",
                valid=False,
            ),
            RuleExample(
                code="SaveDataAll;",
                description=(
                    "V12 mode: reported without parentheses too — TI makes them "
                    "optional on a no-argument call"
                ),
                valid=False,
            ),
            RuleExample(
                code="nValue = CellGetN('Sales', 'Actual', 'Jan');",
                description="A function available in both versions is always allowed",
                valid=True,
            ),
        ],
    )

    def __init__(self, mode: str = _DEFAULT_MODE) -> None:
        self.mode = _MODE_ALIASES.get(str(mode).lower(), _DEFAULT_MODE)
        self._templates = _templates_for_mode(self.mode)

    @property
    def RULE_ID(self) -> str:
        return "C510"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        # Precedence: explicit per-rule `mode` > top-level `target_version` >
        # the rule's own default. Unset values are None/absent and skipped.
        mode = rule_cfg.get("mode") or rule_cfg.get("target_version") or _DEFAULT_MODE
        return [cls(mode=mode)]

    def interested_in(self):
        # Every statement that can carry a call — the linter's walk recurses into
        # IF/WHILE bodies, so nested statements arrive here too and only the
        # expression *within* each statement still needs traversing. Statements
        # the parser could not read are covered separately (see _visit_unknown);
        # an incompatible call is worth reporting even in broken code, since the
        # whole point of the rule is to catch it before the target server does.
        return [*EXPRESSION_CARRYING_STATEMENTS, UnknownStatement]

    def visit(self, statement, context: LintContext):
        if isinstance(statement, UnknownStatement):
            return self._visit_unknown(statement)

        expr = statement_expression(statement)
        if expr is None:
            return []

        issues = []
        for call in iter_function_calls(expr):
            template = self._templates.get(call.name.lower())
            if template is None:
                continue
            issues.append(self._issue(template, call.name, get_node_token(call)))
        return issues

    def _visit_unknown(self, statement) -> list:
        """Best-effort scan of a statement the parser could not read.

        No AST exists here, so the token stream is matched by name: an
        identifier is reported when it is directly followed by ``(``, or when it
        stands alone as the statement (TI makes the parentheses optional on a
        no-argument call). P110 already reports the statement itself as
        unparseable; this only recovers the version finding hiding inside it.
        """
        tokens = [
            tok
            for tok in statement.tokens
            if tok.type not in (TokenType.WHITESPACE, TokenType.NEWLINE)
        ]
        issues = []
        for index, token in enumerate(tokens):
            if token.type != TokenType.IDENTIFIER:
                continue
            template = self._templates.get(token.value.lower())
            if template is None:
                continue
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            # Anything else (an operator, '=', a comma) means the name is being
            # used as a value, not called — skip it rather than guess.
            if following is not None and following.type not in (
                TokenType.LPAREN,
                TokenType.SEMICOLON,
            ):
                continue
            issues.append(self._issue(template, token.value, token))
        return issues

    def _issue(self, template: str, name: str, token) -> LintIssue:
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )
        return LintIssue(
            rule_id=self.RULE_ID,
            message=template.format(name=name),
            line=line,
            column=column,
            position=position,
        )
