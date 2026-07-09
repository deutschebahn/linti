"""Rule S420 – Function version compatibility (PA/TM1 v11 vs v12).

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
"""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata

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

#: Per mode, the message template for a (v11-only, v12-only) function.
#: ``None`` means that family is allowed in the mode and yields no finding.
#: ``{name}`` is filled with the call's original casing.
_MESSAGES: dict[str, tuple[str | None, str | None]] = {
    _MODE_COMPATIBLE: (
        "'{name}' is only available in PA/TM1 v11 (unsupported in v12); "
        "avoid it for code that must run on both versions",
        "'{name}' is only available in PA/TM1 v12 (does not exist in v11); "
        "avoid it for code that must run on both versions",
    ),
    _MODE_V11: (
        None,
        "'{name}' was introduced in PA/TM1 v12 and is not available in v11",
    ),
    _MODE_V12: (
        "'{name}' is not supported in PA/TM1 v12 (deprecated in v11)",
        None,
    ),
}


class FunctionVersionCompatibilityRule(BaseRule):
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
            "Matching is case-insensitive. The target version is normally set "
            "once via the top-level `target_version` (v11 | v12 | both) so other "
            "version-aware rules can share it; the per-rule `mode` overrides it "
            "when present."
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
                code="nValue = CellGetN('Sales', 'Actual', 'Jan');",
                description="A function available in both versions is always allowed",
                valid=True,
            ),
        ],
    )

    def __init__(self, mode: str = _DEFAULT_MODE) -> None:
        self.mode = _MODE_ALIASES.get(str(mode).lower(), _DEFAULT_MODE)

    @property
    def RULE_ID(self) -> str:
        return "S420"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        # Precedence: explicit per-rule `mode` > top-level `target_version` >
        # the rule's own default. Unset values are None/absent and skipped.
        mode = rule_cfg.get("mode") or rule_cfg.get("target_version") or _DEFAULT_MODE
        return [cls(mode=mode)]

    def interested_in(self):
        return [TokenType.IDENTIFIER]

    def visit(self, token, window, context: LintContext):
        # Only an identifier immediately followed by '(' is a function call.
        nxt = window.next_non_ws()
        if nxt is None or nxt.type != TokenType.LPAREN:
            return []

        key = token.value.lower()
        v11_template, v12_template = _MESSAGES[self.mode]
        if key in V11_ONLY_FUNCTIONS:
            template = v11_template
        elif key in V12_ONLY_FUNCTIONS:
            template = v12_template
        else:
            template = None
        if template is None:
            return []

        return [
            LintIssue(
                rule_id=self.RULE_ID,
                message=template.format(name=token.value),
                line=token.line,
                column=token.column,
                position=token.position,
            )
        ]
