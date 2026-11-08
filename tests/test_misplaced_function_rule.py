"""Placement and migration coverage for C150 (and its split-off C151)."""

import pytest
from typer.testing import CliRunner

from linti.cli.file_linter import linter_from_config
from linti.cli.main import app
from linti.config import Config, ItemSkipConfig, LintiConfigWarning, RulesConfig
from linti.lexer.lexer import Lexer
from linti.linter.api import lint_process_model
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Severity
from linti.linter.linter import Linter
from linti.linter.reporter import file_report_exit_code, filter_by_severity
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules import _RULE_REGISTRY
from linti.rules.rule_factory import create_rules
from linti.rules.semantic.discouraged_function_placement_rule import (
    DiscouragedFunctionPlacementRule,
)
from linti.rules.semantic.function_placement import (
    FUNCTION_PLACEMENTS,
    PROCEDURE_SECTIONS,
    Placement,
)
from linti.rules.semantic.item_skip_rule import ItemSkipRule
from linti.rules.semantic.misplaced_function_rule import MisplacedFunctionRule


#: Expected outcome per section: C150 error, C151 warning, or nothing.
INVALID = ("C150", Severity.ERROR, "is not allowed in")
DISCOURAGED = ("C151", Severity.WARNING, "is discouraged")


def _lint(code, block="prolog", rule=None):
    return Linter(statement_rules=[rule or MisplacedFunctionRule()]).lint(
        Lexer(code).tokenize(), LintContext(block=block)
    )


def _lint_both(code, block="prolog"):
    rules = [MisplacedFunctionRule(), DiscouragedFunctionPlacementRule()]
    return Linter(statement_rules=rules).lint(
        Lexer(code).tokenize(), LintContext(block=block)
    )


@pytest.mark.parametrize("casing", [str.lower, str.upper, lambda name: name])
@pytest.mark.parametrize(
    "name,args,expected",
    [
        (
            "DimensionElementInsert",
            "'Product', '', vProduct, 'N'",
            [None, None, INVALID, INVALID],
        ),
        (
            "HierarchyElementInsert",
            "'Product', 'Reporting', '', vProduct, 'N'",
            [None, None, INVALID, INVALID],
        ),
        (
            "DimensionElementComponentAdd",
            "'Product', 'Total', vProduct, 1",
            [None, None, None, INVALID],
        ),
        (
            "HierarchyElementComponentAdd",
            "'Product', 'Reporting', 'Total', vProduct, 1",
            [None, None, None, INVALID],
        ),
        (
            "AttrPutS",
            "vDescription, 'Product', vProduct, 'Description'",
            [None, DISCOURAGED, None, None],
        ),
        (
            "AttrPutN",
            "nValue, 'Product', vProduct, 'Weight'",
            [None, DISCOURAGED, None, None],
        ),
        (
            "ElementAttrPutS",
            "vDescription, 'Product', 'Reporting', vProduct, 'Description'",
            [None, DISCOURAGED, None, None],
        ),
        (
            "ElementAttrPutN",
            "nValue, 'Product', 'Reporting', vProduct, 'Weight'",
            [None, DISCOURAGED, None, None],
        ),
        (
            "DisableBulkLoadMode",
            "",
            [INVALID, INVALID, INVALID, None],
        ),
        *(
            (name, "'Sales'", [None, None, DISCOURAGED, DISCOURAGED])
            for name in (
                "AddClient",
                "DeleteClient",
                "AddGroup",
                "DeleteGroup",
                "CellSecurityCubeCreate",
                "CellSecurityCubeDestroy",
            )
        ),
        ("ItemSkip", "", [INVALID, None, None, INVALID]),
        (
            "AddInfoCubeRestriction",
            "'Sales', 'Version', 'Actual'",
            [None, INVALID, INVALID, INVALID],
        ),
        ("DisableMTQViewConstruct", "", [None, INVALID, INVALID, None]),
        ("EnableMTQViewConstruct", "", [None, DISCOURAGED, DISCOURAGED, None]),
        (
            "SetInputCharacterSet",
            "'TM1CS_UTF8'",
            [None, DISCOURAGED, DISCOURAGED, DISCOURAGED],
        ),
        ("DimensionUpdateDirect", "'d'", [None, DISCOURAGED, DISCOURAGED, None]),
        ("HierarchyUpdateDirect", "'d', 'h'", [None, DISCOURAGED, DISCOURAGED, None]),
        *(
            (name, "'d'", [None, DISCOURAGED, DISCOURAGED, DISCOURAGED])
            for name in (
                "DimensionDeleteAllElements",
                "DimensionDeleteElements",
                "HierarchyDeleteAllElements",
                "HierarchyDeleteElements",
            )
        ),
        *(
            (name, "'x'", [None, DISCOURAGED, DISCOURAGED, None])
            for name in (
                "CubeClearData",
                "ViewZeroOut",
                "CubeProcessFeeders",
                "SecurityRefresh",
                "SaveDataAll",
                "CubeSaveData",
                "CubeCreate",
                "CubeDestroy",
                "DimensionCreate",
                "DimensionDestroy",
                "HierarchyCreate",
                "HierarchyDestroy",
                "ViewCreate",
                "ViewDestroy",
                "ViewCreateByMDX",
                "SubsetCreate",
                "SubsetDestroy",
                "SubsetCreateByMDX",
                "RefreshMdxHierarchy",
                "CubeSetLogChanges",
                "EnableBulkLoadMode",
                "ASCIIDelete",
                "DimensionSortOrder",
                "HierarchySortOrder",
            )
        ),
    ],
)
def test_placement_matrix(name, args, expected, casing):
    for block, outcome in zip(("prolog", "metadata", "data", "epilog"), expected):
        issues = _lint_both(f"{casing(name)}({args});", block)
        if outcome is None:
            assert issues == []
        else:
            rule_id, severity, wording = outcome
            assert len(issues) == 1
            issue = issues[0]
            assert issue.rule_id == rule_id
            assert issue.severity is severity
            assert casing(name) in issue.message
            assert block.title() in issue.message
            assert wording in issue.message


def test_bulk_load_disable_is_only_checked_by_section():
    """The Epilog's *last line* is IBM's ask; C150 checks the section only."""
    assert _lint("DisableBulkLoadMode();\nAsciiOutput(sLog, 'done');", "epilog") == []
    assert _lint("EnableBulkLoadMode();", "data") == []


@pytest.mark.parametrize("casing", [str.lower, str.upper, lambda name: name])
@pytest.mark.parametrize(
    "call",
    [
        "DimensionElementInsertDirect('d', '', 'e', 'N');",
        "DimensionElementDeleteDirect('d', 'e');",
        "DimensionElementComponentAddDirect('d', 'total', 'e', 1);",
        "DimensionElementComponentDeleteDirect('d', 'total', 'e');",
        "DimensionTopElementInsertDirect('d', '', 'total');",
        "HierarchyElementInsertDirect('d', 'h', '', 'e', 'N');",
        "HierarchyElementDeleteDirect('d', 'h', 'e');",
        "HierarchyElementComponentAddDirect('d', 'h', 'total', 'e', 1);",
        "HierarchyElementComponentDeleteDirect('d', 'h', 'total', 'e');",
        "HierarchyTopElementInsertDirect('d', 'h', '', 'total');",
    ],
)
def test_reviewed_direct_functions_are_valid_in_every_section(call, casing):
    name, arguments = call.split("(", 1)
    # Ensure an omitted function cannot pass merely because unknown calls are
    # ignored: these are explicitly reviewed members of the placement table.
    assert name.lower() in FUNCTION_PLACEMENTS
    for block in ("prolog", "metadata", "data", "epilog"):
        assert _lint_both(f"{casing(name)}({arguments}", block) == []


@pytest.mark.parametrize(
    "call",
    [
        "DimensionElementDelete('d', 'e');",
        "HierarchyElementDelete('d', 'h', 'e');",
        "DimensionElementComponentDelete('d', 'total', 'e');",
        "HierarchyElementComponentDelete('d', 'h', 'total', 'e');",
        "DimensionTopElementInsert('d', '', 'total');",
        "HierarchyTopElementInsert('d', 'h', '', 'total');",
        "ElementAttrInsert('d', 'h', '', 'a', 'N');",
        "n = ElementAttrN('d', 'h', 'e', 'a');",
        "s = ElementAttrS('d', 'h', 'e', 'a');",
        # Reviewed against IBM: no section restriction documented.
        "AssignClientToGroup('c', 'g');",
        "RemoveClientFromGroup('c', 'g');",
        "SetElementGroupsSecurity('d', 'e', 'g', 'READ');",
        "ProcessBreak;",
        "s = GetProcessErrorFilename;",
    ],
)
def test_related_names_do_not_inherit_restrictions(call):
    for block in ("prolog", "metadata", "data", "epilog"):
        assert _lint_both(call, block) == []


@pytest.mark.parametrize("name", ["AttrPutN", "ElementAttrPutN", "ElementAttrPutS"])
def test_attribute_recommendations_honor_configuration(name):
    arguments = "1, 'd', 'e', 'a'" if name == "AttrPutN" else "1, 'd', 'h', 'e', 'a'"
    call = f"{name}({arguments});"

    def lint(rules):
        linter = linter_from_config(Config(rules=rules), select="C15")
        return linter.lint(Lexer(call).tokenize(), LintContext(block="metadata"))

    assert [issue.rule_id for issue in lint({})] == ["C151"]
    assert lint({"discouraged_function_placement": {"allowed_functions": [name]}}) == []
    # Legacy C150 allowlist is the fallback while C151 has no list of its own.
    assert lint({"misplaced_function": {"allowed_functions": [name.upper()]}}) == []


def test_hierarchy_load_uses_metadata_then_data():
    process = ProcessIR(
        name="hierarchy_load",
        metadata=ProcedureInfo(
            code="HierarchyElementInsert('Product', 'Reporting', '', vProduct, 'N');"
        ),
        data=ProcedureInfo(
            code="ElementAttrPutN(nWeight, 'Product', 'Reporting', vProduct, 'Weight');"
        ),
    )
    assert (
        lint_process_model(process, linter_from_config(Config(), select="C150")) == []
    )


def test_direct_load_can_create_and_populate_elements_in_data():
    code = (
        "HierarchyElementInsertDirect('Product', 'Reporting', '', vProduct, 'N');\n"
        "HierarchyElementComponentAddDirect('Product', 'Reporting', 'Total', vProduct, 1);\n"
        "ElementAttrPutN(nWeight, 'Product', 'Reporting', vProduct, 'Weight');"
    )
    assert _lint(code, "data") == []
    issues = _lint_both(code.replace("Direct(", "("), "data")
    assert len(issues) == 1
    assert "HierarchyElementInsert" in issues[0].message
    assert issues[0].severity is Severity.ERROR


@pytest.mark.parametrize("block", [None, "", "unknown"])
def test_no_known_section(block):
    assert _lint_both("ItemSkip(); AttrPutS('x', 'd', 'e', 'a');", block) == []


def test_unknown_functions_and_non_calls_are_ignored():
    assert (
        _lint("SomeFunction(); n = ItemSkip + 1; s = 'ItemSkip()'; # ItemSkip();") == []
    )


def test_messages_and_location():
    issue = _lint("\n    iTeMsKiP;", "EPILOG")[0]
    assert (issue.line, issue.column, issue.position) == (2, 5, 5)
    assert (
        issue.message
        == "iTeMsKiP is not allowed in Epilog. Use it in Metadata or Data."
    )
    issue = _lint("DimensionElementInsert('d', '', 'e', 'N');", "data")[0]
    assert issue.message == (
        "DimensionElementInsert is not allowed in Data. Use it in Prolog or Metadata."
    )
    issue = _lint_both("AttrPutS('x', 'd', 'e', 'a');", "metadata")[0]
    assert issue.message == (
        "AttrPutS in Metadata is discouraged. Consider writing attributes in Data."
    )
    issue = _lint_both("AddGroup('g');", "epilog")[0]
    assert issue.message == (
        "AddGroup in Epilog is discouraged. Consider using it in Prolog or Metadata."
    )


@pytest.mark.parametrize(
    "code",
    [
        "n = ItemSkip();",
        "IF(ItemSkip() = 1); n = 1; ENDIF;",
        "WHILE(ItemSkip() = 1); n = 1; END;",
        "SomeFunction(ItemSkip());",
        "IF(n = 1); WHILE(n = 2); ItemSkip; END; ELSE; ItemSkip(); ENDIF;",
    ],
)
def test_calls_in_expressions_and_nested_control_flow(code):
    issues = _lint(code)
    assert len(issues) == code.count("ItemSkip")
    assert all(issue.severity is Severity.ERROR for issue in issues)


def _process():
    return ProcessIR(
        name="placement",
        prolog=ProcedureInfo(code="ItemSkip();"),
        metadata=ProcedureInfo(code="AttrPutS('x', 'd', 'e', 'a');"),
        data=ProcedureInfo(code="DimensionElementInsert('d', '', 'e', 'N');"),
        epilog=ProcedureInfo(code="ItemSkip;"),
    )


def test_only_invalid_placements_block_the_run():
    """C150 errors fail the run; C151 recommendations are warnings that do not."""
    linter = linter_from_config(Config(), select="C15")
    issues = lint_process_model(_process(), linter)
    assert sorted((issue.rule_id, issue.severity) for _, issue, _ in issues) == [
        ("C150", Severity.ERROR)
    ] * 3 + [("C151", Severity.WARNING)]
    assert len(filter_by_severity(issues, Severity.ERROR)) == 3
    assert file_report_exit_code(issues) == 1
    only_recommendation = ProcessIR(
        name="advice", metadata=ProcedureInfo(code="AttrPutS('x', 'd', 'e', 'a');")
    )
    issues = lint_process_model(only_recommendation, linter)
    assert [issue.rule_id for _, issue, _ in issues] == ["C151"]
    assert file_report_exit_code(issues) == 0


@pytest.mark.parametrize(
    "select,expected",
    [("C150", {"C150"}), ("C151", {"C151"}), ("C15", {"C150", "C151"})],
)
def test_select_reaches_each_placement_rule(select, expected):
    issues = lint_process_model(_process(), linter_from_config(Config(), select=select))
    assert {issue.rule_id for _, issue, _ in issues} == expected


def test_placement_table_covers_every_section():
    """The table is this rule's extension point — a gap must not reach visit()."""
    for name, placements in FUNCTION_PLACEMENTS.items():
        assert set(placements) == set(PROCEDURE_SECTIONS), name


def test_section_missing_from_the_table_is_unrestricted(monkeypatch):
    monkeypatch.setitem(FUNCTION_PLACEMENTS, "cellputs", {"data": Placement.INVALID})
    assert _lint("CellPutS('v', 'c', 'e');", "prolog") == []
    issue = _lint("CellPutS('v', 'c', 'e');", "data")[0]
    assert "Prolog, Metadata or Epilog" in issue.message


def test_legacy_report_not_recommended_false_disables_c151():
    cfg = Config(rules={"misplaced_function": {"report_not_recommended": False}})
    assert not cfg.rules.discouraged_function_placement.enabled
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C150"))
    assert {issue.rule_id for _, issue, _ in issues} == {"C150"}
    _, rules = create_rules(cfg)
    assert not any(type(rule) is DiscouragedFunctionPlacementRule for rule in rules)
    # An explicit --select still runs the rule, like any disabled rule.
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C151"))
    assert {issue.rule_id for _, issue, _ in issues} == {"C151"}


def test_explicit_c151_enabled_wins_over_legacy_switch():
    cfg = Config(
        rules={
            "misplaced_function": {"report_not_recommended": False},
            "discouraged_function_placement": {"enabled": True},
        }
    )
    _, rules = create_rules(cfg)
    assert any(type(rule) is DiscouragedFunctionPlacementRule for rule in rules)


def test_legacy_switch_warns_when_loaded_from_file(tmp_path):
    path = tmp_path / "linti.yaml"
    path.write_text(
        "rules:\n  misplaced_function:\n    report_not_recommended: false\n"
    )
    with pytest.warns(LintiConfigWarning, match="report_not_recommended.*C151"):
        cfg = Config.load_from_file(path)
    assert not cfg.rules.discouraged_function_placement.enabled


def test_c151_does_not_inherit_c150_severity():
    cfg = Config(rules={"misplaced_function": {"severity": "error"}})
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C15"))
    severities = {issue.rule_id: issue.severity for _, issue, _ in issues}
    assert severities == {"C150": Severity.ERROR, "C151": Severity.WARNING}


def test_allowed_functions_exempts_a_function_in_every_section():
    cfg = Config(
        rules={"misplaced_function": {"allowed_functions": ["ItemSkip", "attrputs"]}}
    )
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C15"))
    assert len(issues) == 1
    assert "DimensionElementInsert" in issues[0][1].message


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_severity_override_reweighs_the_whole_rule(severity):
    cfg = Config(rules={"misplaced_function": {"severity": severity}})
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C150"))
    assert len(issues) == 3
    assert all(issue.severity is Severity(severity) for _, issue, _ in issues)


def test_config_disable_and_select_override(tmp_path):
    path = tmp_path / "linti.yaml"
    path.write_text("rules:\n  misplaced_function:\n    enabled: false\n")
    cfg = Config.load_from_file(path)
    assert not cfg.rules.misplaced_function.enabled
    assert all(rule.RULE_ID != "C150" for rule in create_rules(cfg)[1])
    _, selected = create_rules(cfg, select="C150")
    assert len(selected) == 1
    assert type(selected[0]) is MisplacedFunctionRule


def test_old_and_new_config_remain_independent():
    cfg = Config(
        rules={
            "item_skip": {"enabled": True, "severity": "warning"},
            "misplaced_function": {"enabled": False, "severity": "error"},
        }
    )
    with pytest.warns(LintiConfigWarning, match="C130.*deprecated.*C150"):
        _, rules = create_rules(cfg)
    assert any(type(rule) is ItemSkipRule for rule in rules)
    assert not any(type(rule) is MisplacedFunctionRule for rule in rules)
    legacy = next(rule for rule in rules if type(rule) is ItemSkipRule)
    assert _lint("ItemSkip();", rule=legacy)[0].severity is Severity.WARNING
    assert _lint("AttrPutS('x', 'd', 'e', 'a');", "metadata", legacy) == []
    assert cfg.rules.item_skip is not cfg.rules.misplaced_function
    assert "item_skip" in cfg.rules.model_dump()


def test_enabled_legacy_rule_defers_to_its_successor():
    """The config an upgrading project already has must not double-report."""
    cfg = Config(rules={"item_skip": {"enabled": True}})
    with pytest.warns(LintiConfigWarning, match="C130.*deprecated.*C150 is active"):
        _, rules = create_rules(cfg)
    assert not any(type(rule) is ItemSkipRule for rule in rules)
    issues = lint_process_model(_process(), Linter(statement_rules=rules))
    assert {issue.rule_id for _, issue, _ in issues} >= {"C150"}
    assert "C130" not in {issue.rule_id for _, issue, _ in issues}


@pytest.mark.parametrize("select", ["C1", "C130,C150"])
def test_select_reaching_both_rules_runs_only_the_successor(select):
    with pytest.warns(LintiConfigWarning, match="C150 is active"):
        _, rules = create_rules(Config(), select=select)
    types = {type(rule) for rule in rules}
    assert MisplacedFunctionRule in types
    assert ItemSkipRule not in types


def test_default_run_uses_only_replacement_without_duplicate_findings():
    _, rules = create_rules(Config())
    assert any(type(rule) is MisplacedFunctionRule for rule in rules)
    assert not any(type(rule) is ItemSkipRule for rule in rules)
    issues = lint_process_model(_process(), Linter(statement_rules=rules))
    assert not any(issue.rule_id == "C130" for _, issue, _ in issues)
    assert sum(issue.rule_id == "C150" for _, issue, _ in issues) == 3
    assert sum(issue.rule_id == "C151" for _, issue, _ in issues) == 1


def test_python_legacy_classes_keep_original_scope_and_config():
    rule = ItemSkipRule()
    assert rule.CONFIG_KEY == "item_skip"
    assert rule.RULE_ID == "C130"
    assert _lint("AttrPutS('x', 'd', 'e', 'a');", "metadata", rule) == []
    assert _lint("ItemSkip();", rule=rule)[0].rule_id == "C130"
    cfg = RulesConfig(item_skip=ItemSkipConfig(enabled=True))
    assert cfg.item_skip.enabled
    assert _RULE_REGISTRY.count(ItemSkipRule) == 1
    assert _RULE_REGISTRY.count(MisplacedFunctionRule) == 1


@pytest.mark.parametrize("rule_id", ["C130", "S120"])
def test_deprecated_id_selects_legacy_rule(rule_id):
    with pytest.warns(LintiConfigWarning):
        _, rules = create_rules(Config(), select=rule_id)
    assert len(rules) == 1
    assert type(rules[0]) is ItemSkipRule


def test_selecting_legacy_rule_warns_once():
    with pytest.warns(LintiConfigWarning, match="C130.*deprecated.*C150") as caught:
        create_rules(Config(), select="C130")
    assert len(caught) == 1


def test_noqa_suppresses_each_placement_rule_separately():
    assert _lint_both("# noqa: C150\nItemSkip();") == []
    # The recommendation moved to C151: the old suppression no longer covers it.
    code = "# noqa: C150\nAttrPutS('x', 'd', 'e', 'a');"
    assert [issue.rule_id for issue in _lint_both(code, "metadata")] == ["C151"]
    code = "# noqa: C151\nAttrPutS('x', 'd', 'e', 'a');"
    assert _lint_both(code, "metadata") == []


@pytest.mark.parametrize("rule_id", ["C130", "S120"])
def test_legacy_noqa_does_not_suppress_new_rule(rule_id):
    code = f"# noqa: {rule_id}\nItemSkip();"
    with pytest.warns(LintiConfigWarning):
        assert len(_lint(code)) == 1
    with pytest.warns(LintiConfigWarning):
        assert _lint(code, rule=ItemSkipRule()) == []


def test_explain_documents_both_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", "C150"])
    assert result.exit_code == 0
    assert "Invalid Function Placement" in result.output
    assert "misplaced_function" in result.output
    with pytest.warns(LintiConfigWarning, match="C130.*deprecated.*C150"):
        result = CliRunner().invoke(app, ["explain", "C130"])
    assert result.exit_code == 0
    assert "ItemSkip Block Usage" in result.output
    assert "Deprecated: use C150" in result.output


def test_legacy_switch_survives_a_dump_round_trip():
    cfg = Config(rules={"misplaced_function": {"report_not_recommended": False}})
    again = Config.model_validate(cfg.model_dump(by_alias=True))
    _, rules = create_rules(again)
    assert not any(type(rule) is DiscouragedFunctionPlacementRule for rule in rules)


def test_allowlist_fallback_survives_a_dump_round_trip():
    cfg = Config(rules={"misplaced_function": {"allowed_functions": ["AttrPutS"]}})
    again = Config.model_validate(cfg.model_dump(by_alias=True))
    linter = linter_from_config(again, select="C151")
    code = "AttrPutS('x', 'd', 'e', 'a');"
    assert linter.lint(Lexer(code).tokenize(), LintContext(block="metadata")) == []


def test_legacy_settings_changed_after_construction_are_honoured():
    cfg = Config()
    cfg.rules.misplaced_function.report_not_recommended = False
    _, rules = create_rules(cfg)
    assert not any(type(rule) is DiscouragedFunctionPlacementRule for rule in rules)
    cfg = Config()
    cfg.rules.misplaced_function.allowed_functions = ["AttrPutS"]
    linter = linter_from_config(cfg, select="C151")
    code = "AttrPutS('x', 'd', 'e', 'a');"
    assert linter.lint(Lexer(code).tokenize(), LintContext(block="metadata")) == []


def test_legacy_switch_turned_back_on_after_construction_enables_c151():
    cfg = Config(rules={"misplaced_function": {"report_not_recommended": False}})
    cfg.rules.misplaced_function.report_not_recommended = True
    _, rules = create_rules(cfg)
    assert any(type(rule) is DiscouragedFunctionPlacementRule for rule in rules)


def _lint_c151(code, block, variables=None):
    rules = [MisplacedFunctionRule(), DiscouragedFunctionPlacementRule()]
    context = LintContext(block=block, variables=variables)
    return [
        i.rule_id
        for i in Linter(statement_rules=rules).lint(Lexer(code).tokenize(), context)
    ]


PER_RECORD_CALLS = [
    "SubsetCreate(vDim, 'tmp');",
    "DimensionSortOrder(sDim, 'ByName', 'Ascending', 'ByName', 'Ascending');",
    "DimensionUpdateDirect('Product');",
    "DimensionDeleteAllElements('Product');",
]


@pytest.mark.parametrize("call", PER_RECORD_CALLS)
@pytest.mark.parametrize("block", ["metadata", "data"])
def test_per_record_operations_under_a_data_source_condition_are_not_reported(
    call, block
):
    guarded = f"IF(v1 @= 'Header');\n    {call}\nELSE;\n    {call}\nENDIF;"
    assert _lint_c151(guarded, block, variables=["v1"]) == []
    assert _lint_c151(call, block, variables=["v1"]) == ["C151"]


@pytest.mark.parametrize(
    "prefix,condition",
    [
        ("", "pMode = 1"),  # parameter
        ("", "1 = 1"),  # constant
        ("", "sTarget @= 'Sales'"),  # not assigned in Metadata/Data
        ("cFlag = 1;\n", "cFlag = 1"),  # assigned here, but provably constant
    ],
)
def test_condition_that_is_the_same_on_every_record_does_not_exempt(prefix, condition):
    code = f"{prefix}IF({condition});\n    ViewZeroOut('Sales', 'Zero');\nENDIF;"
    process = ProcessIR(
        name="p",
        variables=["v1"],
        datasource_type="ASCII",
        data=ProcedureInfo(code=code),
    )
    linter = linter_from_config(Config(), select="C151")
    assert [i.rule_id for _, i, _ in lint_process_model(process, linter)] == ["C151"]


def test_record_counter_in_condition_exempts():
    code = (
        "nRecord = nRecord + 1;\n"
        "IF(nRecord = 1);\n    ViewZeroOut('Sales', 'Zero');\nENDIF;"
    )
    assert _lint_c151(code, "data") == []


def test_outer_record_condition_exempts_nested_constant_if():
    code = (
        "IF(v1 @= 'Header');\n    IF(pMode = 1);\n"
        "        ViewZeroOut('Sales', 'Zero');\n    ENDIF;\nENDIF;"
    )
    assert _lint_c151(code, "data", variables=["v1"]) == []


def test_counter_assigned_in_metadata_counts_in_data():
    process = ProcessIR(
        name="p",
        variables=["v1"],
        datasource_type="ASCII",
        metadata=ProcedureInfo(code="nRecord = nRecord + 1;"),
        data=ProcedureInfo(
            code="IF(nRecord = 1);\n    ViewZeroOut('Sales', 'Zero');\nENDIF;"
        ),
    )
    linter = linter_from_config(Config(), select="C151")
    assert [i.rule_id for _, i, _ in lint_process_model(process, linter)] == []


def test_per_record_operation_in_the_if_condition_or_a_bare_loop_is_reported():
    in_condition = "IF(SubsetCreatebyMDX('tmp', sMDX, vDim, 1) = 0);\nENDIF;"
    in_loop = "WHILE(i < 3);\n    ViewZeroOut('Sales', 'Zero');\n    i = i + 1;\nEND;"
    assert _lint_c151(in_condition, "data", variables=["vDim"]) == ["C151"]
    assert _lint_c151(in_loop, "data", variables=["vDim"]) == ["C151"]


@pytest.mark.parametrize(
    "call,block",
    [
        ("AttrPutS('x', 'Product', vEl, 'Caption');", "metadata"),
        ("AddGroup(vGroup);", "data"),
        ("EnableMTQViewConstruct();", "data"),
        ("DimensionDeleteAllElements('Product');", "epilog"),
    ],
)
def test_other_discouraged_placements_are_reported_inside_an_if(call, block):
    guarded = f"IF(v1 @= 'Header');\n    {call}\nENDIF;"
    assert _lint_c151(guarded, block, variables=["v1"]) == ["C151"]
