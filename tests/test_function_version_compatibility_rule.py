"""Tests for C510 FunctionVersionCompatibilityRule."""

from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.rule_factory import create_rules
from linti.rules.semantic.function_version_compatibility_rule import (
    FunctionVersionCompatibilityRule,
)


def _c510_mode(config_dict):
    """The resolved mode of the C510 rule for a full config, or None if absent."""
    _, statement_rules = create_rules(Config.model_validate(config_dict))
    rules = [r for r in statement_rules if r.RULE_ID == "C510"]
    return rules[0].mode if rules else None


def _lint(code: str, mode: str):
    rule = FunctionVersionCompatibilityRule(mode=mode)
    return Linter(statement_rules=[rule]).lint(Lexer(code).tokenize())


def _names(issues):
    # Extract the quoted function name from each message.
    return sorted(msg.message.split("'")[1] for msg in issues)


def test_both_version_functions_never_reported():
    code = "nV = CellGetN('Sales', 'Actual', 'Jan');"
    for mode in ("CompatibleWithV11AndV12", "V11", "V12"):
        assert _lint(code, mode) == []


def test_compatible_mode_reports_any_version_specific_function():
    code = "nA = CubeSaveData('c');\nnB = JsonGet(d, p);\nnC = CellGetN('c', 'e');"
    issues = _lint(code, "CompatibleWithV11AndV12")
    # Both a v11-only and a v12-only function are reported; the shared one is not.
    assert _names(issues) == ["CubeSaveData", "JsonGet"]
    assert all(i.rule_id == "C510" for i in issues)


def test_v11_mode_reports_only_v12_functions():
    code = "nA = CubeSaveData('c');\nnB = JsonGet(d, p);"
    issues = _lint(code, "V11")
    assert _names(issues) == ["JsonGet"]
    assert "not available in v11" in issues[0].message


def test_v12_mode_reports_only_v11_functions():
    code = "nA = CubeSaveData('c');\nnB = JsonGet(d, p);"
    issues = _lint(code, "V12")
    assert _names(issues) == ["CubeSaveData"]
    assert "not supported in PA/TM1 v12" in issues[0].message


def test_matching_is_case_insensitive():
    code = "nA = cubesavedata('c');\nnB = JSONGET(d, p);"
    issues = _lint(code, "CompatibleWithV11AndV12")
    assert len(issues) == 2


def test_only_flags_identifiers_used_as_calls():
    # A bare identifier that merely shares a function name (no call) is ignored.
    code = "JsonGet = 1;\nnX = JsonGet + 2;"
    assert _lint(code, "V11") == []


def test_detects_calls_in_any_context():
    # Assignment RHS, IF condition, and nested arguments all count.
    code = (
        "nA = JsonGet(d, p);\n"
        "IF(GetJobStatus(nJob) = 1);\n"
        "  nB = Foo(JsonSize(d));\n"
        "ENDIF;"
    )
    issues = _lint(code, "V11")
    assert _names(issues) == ["GetJobStatus", "JsonGet", "JsonSize"]


def test_detects_calls_in_while_condition_and_body():
    code = "WHILE(GetJobStatus(nJob) = 1);\n  nB = JsonSize(d);\nEND;"
    issues = _lint(code, "V11")
    assert _names(issues) == ["GetJobStatus", "JsonSize"]


def test_issues_are_reported_in_source_order():
    # The walk sees an IF condition before its body; output must still be
    # ordered by position so reports read top-to-bottom.
    code = "IF(JsonSize(d) = 0);\n  nB = JsonGet(d, p);\nENDIF;\nnC = JwtCreate(x);"
    issues = _lint(code, "V11")
    assert [i.line for i in issues] == sorted(i.line for i in issues)
    assert [i.message.split("'")[1] for i in issues] == [
        "JsonSize",
        "JsonGet",
        "JwtCreate",
    ]


def test_unknown_mode_falls_back_to_strict_default():
    rule = FunctionVersionCompatibilityRule(mode="nonsense")
    assert rule.mode == "compatiblewithv11andv12"


def test_rule_is_disabled_by_default():
    assert FunctionVersionCompatibilityRule.DEFAULT_ENABLED is False


def test_from_config_reads_mode():
    rule = FunctionVersionCompatibilityRule.from_config({"mode": "V12"})[0]
    assert rule.mode == "v12"


def test_both_alias_maps_to_compatible():
    rule = FunctionVersionCompatibilityRule.from_config({"target_version": "both"})[0]
    assert rule.mode == "compatiblewithv11andv12"


# -- parentheses are optional on no-argument calls ---------------------------
# TI lets a no-argument function be called without parentheses, so `SaveDataAll;`
# and `SaveDataAll();` are the same call and must be reported identically.


def test_reports_call_without_parentheses():
    issues = _lint("SaveDataAll;", "V12")
    assert _names(issues) == ["SaveDataAll"]


def test_parenthesised_and_bare_calls_are_equivalent():
    bare = _lint("SaveDataAll;", "V12")
    parens = _lint("SaveDataAll();", "V12")
    assert [i.message for i in bare] == [i.message for i in parens]


def test_reports_bare_call_nested_in_a_block():
    code = "IF(nX = 1);\n  SaveDataAll;\nELSE;\n  ServerShutdown;\nENDIF;"
    issues = _lint(code, "V12")
    assert _names(issues) == ["SaveDataAll", "ServerShutdown"]


def test_bare_call_is_reported_in_compatible_mode_too():
    assert _names(_lint("SaveDataAll;", "CompatibleWithV11AndV12")) == ["SaveDataAll"]


def test_assignment_to_a_function_name_is_not_a_call():
    # Guards the paren-less path against flagging plain variable use.
    assert _lint("SaveDataAll = 1;", "V12") == []
    assert _lint("nX = SaveDataAll + 2;", "V12") == []


# -- top-level target_version inheritance ------------------------------------


def test_inherits_top_level_target_version():
    mode = _c510_mode(
        {
            "target_version": "v12",
            "rules": {"function_version_compatibility": {"enabled": True}},
        }
    )
    assert mode == "v12"


def test_top_level_both_maps_to_compatible():
    mode = _c510_mode(
        {
            "target_version": "both",
            "rules": {"function_version_compatibility": {"enabled": True}},
        }
    )
    assert mode == "compatiblewithv11andv12"


def test_per_rule_mode_overrides_top_level():
    mode = _c510_mode(
        {
            "target_version": "v12",
            "rules": {
                "function_version_compatibility": {"enabled": True, "mode": "V11"}
            },
        }
    )
    assert mode == "v11"


def test_top_level_version_does_not_enable_the_rule():
    # target_version supplies the value but does not opt the rule in.
    assert _c510_mode({"target_version": "v12", "rules": {}}) is None


def test_default_when_neither_set():
    mode = _c510_mode({"rules": {"function_version_compatibility": {"enabled": True}}})
    assert mode == "compatiblewithv11andv12"
