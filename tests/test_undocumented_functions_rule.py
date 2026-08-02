"""Tests for DoNotUseUndocumentedFunctionsRule (C430)."""

from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.rule_factory import create_rules
from linti.rules.semantic.undocumented_functions_rule import (
    DoNotUseUndocumentedFunctionsRule,
)


def _lint(code: str, allowed_functions=None):
    rule = DoNotUseUndocumentedFunctionsRule(allowed_functions=allowed_functions)
    return Linter(statement_rules=[rule]).lint(Lexer(code).tokenize())


def _names(issues):
    # Extract the quoted function name from each message.
    return sorted(issue.message.split("'")[1] for issue in issues)


def _c430_rules(config_dict=None):
    _, statement_rules = create_rules(Config.model_validate(config_dict or {}))
    return [r for r in statement_rules if r.RULE_ID == "C430"]


class TestReporting:
    def test_undocumented_call_is_reported(self):
        code = "DimensionElementInsertByAlias('Product', '', 'Alias', 'N');"
        issues = _lint(code)
        assert len(issues) == 1
        assert issues[0].rule_id == "C430"

    def test_message_names_the_function(self):
        issues = _lint("DataSpread('Sales', 'Actual');")
        assert "'DataSpread'" in issues[0].message
        assert "undocumented" in issues[0].message.lower()

    def test_message_keeps_the_original_casing(self):
        issues = _lint("dimensionelementinsertbyalias('Product', '', 'A', 'N');")
        assert "'dimensionelementinsertbyalias'" in issues[0].message

    def test_matching_is_case_insensitive(self):
        assert len(_lint("LOCKON();")) == 1
        assert len(_lint("lockon();")) == 1

    def test_call_without_parentheses_is_reported(self):
        issues = _lint("LockOn;")
        assert _names(issues) == ["LockOn"]

    def test_documented_functions_are_allowed(self):
        code = "nValue = CellGetN('Sales', 'Actual', 'Jan');"
        assert _lint(code) == []

    def test_identifier_used_as_a_value_is_not_a_call(self):
        assert _lint("nX = IsNull + 2;") == []
        assert _lint("Hex = 1;") == []

    def test_issue_position_points_at_the_call(self):
        code = "sTemp = 'x';\nnResult = Hex(255);"
        issues = _lint(code)
        assert len(issues) == 1
        assert issues[0].line == 2
        assert issues[0].column == 11


class TestCallSites:
    def test_call_in_assignment_right_hand_side(self):
        assert _names(_lint("nTime = MilliTime();")) == ["MilliTime"]

    def test_call_in_if_condition(self):
        code = "IF(IsNull(sValue) = 1);\n  nX = 1;\nENDIF;"
        assert _names(_lint(code)) == ["IsNull"]

    def test_call_in_while_condition(self):
        code = "WHILE(Hex(nIndex) @<> 'FF');\n  nIndex = nIndex + 1;\nEND;"
        assert _names(_lint(code)) == ["Hex"]

    def test_call_nested_in_arguments(self):
        code = "sResult = SubSt(Hex(nValue), 1, 2);"
        assert _names(_lint(code)) == ["Hex"]

    def test_call_inside_an_if_body(self):
        code = "IF(nFlag = 1);\n  LockOn('Sales');\nENDIF;"
        assert _names(_lint(code)) == ["LockOn"]

    def test_several_calls_are_reported_in_source_order(self):
        code = "LockOn('Sales');\nnTime = MilliTime();\nLockOff('Sales');"
        issues = _lint(code)
        assert [issue.line for issue in issues] == [1, 2, 3]
        assert _names(issues) == ["LockOff", "LockOn", "MilliTime"]

    def test_call_in_an_unparseable_statement_is_recovered(self):
        # Missing closing paren: the parser cannot read this statement, but the
        # undocumented call inside it is still worth reporting.
        code = "nX = (LockOn('Sales');"
        assert _names(_lint(code)) == ["LockOn"]


class TestAllowedFunctions:
    def test_allowed_function_is_not_reported(self):
        code = "DimensionElementInsertByAlias('Product', '', 'Alias', 'N');"
        assert _lint(code, allowed_functions=["DimensionElementInsertByAlias"]) == []

    def test_allowed_function_matching_is_case_insensitive(self):
        assert _lint("LockOn;", allowed_functions=["lockon"]) == []

    def test_other_undocumented_functions_still_report(self):
        code = "LockOn('Sales');\nnTime = MilliTime();"
        issues = _lint(code, allowed_functions=["LockOn"])
        assert _names(issues) == ["MilliTime"]

    def test_unknown_name_in_allowed_functions_is_harmless(self):
        assert _names(_lint("LockOn;", allowed_functions=["NotAFunction"])) == [
            "LockOn"
        ]


class TestConfiguration:
    def test_rule_is_enabled_by_default(self):
        assert len(_c430_rules()) == 1

    def test_rule_can_be_disabled(self):
        cfg = {"rules": {"do_not_use_undocumented_functions": {"enabled": False}}}
        assert _c430_rules(cfg) == []

    def test_allowed_functions_from_config(self):
        cfg = {
            "rules": {
                "do_not_use_undocumented_functions": {
                    "allowed_functions": ["LockOn", "LockOff"]
                }
            }
        }
        rule = _c430_rules(cfg)[0]
        assert rule.allowed_functions == frozenset({"lockon", "lockoff"})
        assert "lockon" not in rule._reported
        assert "millitime" in rule._reported

    def test_from_config_without_allowed_functions(self):
        rule = DoNotUseUndocumentedFunctionsRule.from_config({"enabled": True})[0]
        assert rule.allowed_functions == frozenset()
