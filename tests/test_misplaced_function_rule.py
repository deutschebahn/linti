"""Placement, severity policy and migration coverage for C150."""

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
from linti.rules.semantic.item_skip_rule import ItemSkipRule
from linti.rules.semantic.misplaced_function_rule import (
    FUNCTION_PLACEMENTS,
    PROCEDURE_SECTIONS,
    MisplacedFunctionRule,
    Placement,
)


#: What the two reported placements say, since both carry the same severity.
INVALID = "is not allowed"
NOT_RECOMMENDED = "is not recommended"


def _lint(code, block="prolog", rule=None):
    return Linter(statement_rules=[rule or MisplacedFunctionRule()]).lint(
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
            [None, NOT_RECOMMENDED, None, None],
        ),
        (
            "AttrPutN",
            "nValue, 'Product', vProduct, 'Weight'",
            [None, NOT_RECOMMENDED, None, None],
        ),
        (
            "ElementAttrPutS",
            "vDescription, 'Product', 'Reporting', vProduct, 'Description'",
            [None, NOT_RECOMMENDED, None, None],
        ),
        (
            "ElementAttrPutN",
            "nValue, 'Product', 'Reporting', vProduct, 'Weight'",
            [None, NOT_RECOMMENDED, None, None],
        ),
        (
            "DisableBulkLoadMode",
            "",
            [INVALID, INVALID, INVALID, None],
        ),
        *(
            (name, "'Sales'", [None, None, NOT_RECOMMENDED, NOT_RECOMMENDED])
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
    ],
)
def test_placement_matrix(name, args, expected, casing):
    for block, wording in zip(("prolog", "metadata", "data", "epilog"), expected):
        issues = _lint(f"{casing(name)}({args});", block)
        if wording is None:
            assert issues == []
        else:
            assert len(issues) == 1
            issue = issues[0]
            assert issue.rule_id == "C150"
            # Both reported placements block the run; only the wording differs.
            assert issue.severity is Severity.ERROR
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
        "DimensionUpdateDirect('d');",
        "HierarchyElementInsertDirect('d', 'h', '', 'e', 'N');",
        "HierarchyElementDeleteDirect('d', 'h', 'e');",
        "HierarchyElementComponentAddDirect('d', 'h', 'total', 'e', 1);",
        "HierarchyElementComponentDeleteDirect('d', 'h', 'total', 'e');",
        "HierarchyTopElementInsertDirect('d', 'h', '', 'total');",
        "HierarchyUpdateDirect('d', 'h');",
    ],
)
def test_reviewed_direct_functions_are_valid_in_every_section(call, casing):
    name, arguments = call.split("(", 1)
    # Ensure an omitted function cannot pass merely because unknown calls are
    # ignored: these are explicitly reviewed members of the placement table.
    assert name.lower() in FUNCTION_PLACEMENTS
    for block in ("prolog", "metadata", "data", "epilog"):
        assert _lint(f"{casing(name)}({arguments}", block) == []


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
    ],
)
def test_related_names_do_not_inherit_restrictions(call):
    for block in ("prolog", "metadata", "data", "epilog"):
        assert _lint(call, block) == []


@pytest.mark.parametrize("name", ["AttrPutN", "ElementAttrPutN", "ElementAttrPutS"])
def test_attribute_recommendations_honor_configuration(name):
    arguments = "1, 'd', 'e', 'a'" if name == "AttrPutN" else "1, 'd', 'h', 'e', 'a'"
    call = f"{name}({arguments});"
    assert len(_lint(call, "metadata")) == 1
    for settings in (
        {"report_not_recommended": False},
        {"allowed_functions": [name.upper()]},
    ):
        cfg = Config(rules={"misplaced_function": settings})
        linter = linter_from_config(cfg, select="C150")
        assert linter.lint(Lexer(call).tokenize(), LintContext(block="metadata")) == []


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
    issues = _lint(code.replace("Direct(", "("), "data")
    assert len(issues) == 1
    assert "HierarchyElementInsert" in issues[0].message
    assert issues[0].severity is Severity.ERROR


@pytest.mark.parametrize("block", [None, "", "unknown"])
def test_no_known_section(block):
    assert _lint("ItemSkip(); AttrPutS('x', 'd', 'e', 'a');", block) == []


def test_unknown_functions_and_non_calls_are_ignored():
    assert (
        _lint("SomeFunction(); n = ItemSkip + 1; s = 'ItemSkip()'; # ItemSkip();") == []
    )


def test_recommendations_and_location():
    issue = _lint("\n    iTeMsKiP;", "EPILOG")[0]
    assert (issue.line, issue.column, issue.position) == (2, 5, 5)
    assert "Metadata, Data" in issue.message
    issue = _lint("AttrPutS('x', 'd', 'e', 'a');", "metadata")[0]
    assert "Recommended sections: Prolog, Data, Epilog" in issue.message


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


def test_every_finding_blocks_the_run():
    """Recommendations fail the run too — `report_not_recommended` is the way out."""
    linter = linter_from_config(Config(), select="C150")
    issues = lint_process_model(_process(), linter)
    assert [issue.severity for _, issue, _ in issues] == [Severity.ERROR] * 4
    assert len(filter_by_severity(issues, Severity.ERROR)) == 4
    assert file_report_exit_code(issues) == 1


def test_placement_table_covers_every_section():
    """The table is this rule's extension point — a gap must not reach visit()."""
    for name, placements in FUNCTION_PLACEMENTS.items():
        assert set(placements) == set(PROCEDURE_SECTIONS), name


def test_section_missing_from_the_table_is_unrestricted(monkeypatch):
    monkeypatch.setitem(FUNCTION_PLACEMENTS, "cellputs", {"data": Placement.INVALID})
    assert _lint("CellPutS('v', 'c', 'e');", "prolog") == []
    issue = _lint("CellPutS('v', 'c', 'e');", "data")[0]
    assert "Prolog, Metadata, Epilog" in issue.message


def test_report_not_recommended_false_keeps_documented_restrictions():
    cfg = Config(rules={"misplaced_function": {"report_not_recommended": False}})
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C150"))
    assert [issue.severity for _, issue, _ in issues] == [Severity.ERROR] * 3
    assert all("not recommended" not in issue.message for _, issue, _ in issues)


def test_allowed_functions_exempts_a_function_in_every_section():
    cfg = Config(
        rules={"misplaced_function": {"allowed_functions": ["ItemSkip", "attrputs"]}}
    )
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C150"))
    assert len(issues) == 1
    assert "DimensionElementInsert" in issues[0][1].message


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_severity_override_reweighs_the_whole_rule(severity):
    cfg = Config(rules={"misplaced_function": {"severity": severity}})
    issues = lint_process_model(_process(), linter_from_config(cfg, select="C150"))
    assert len(issues) == 4
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
    assert {issue.rule_id for _, issue, _ in issues} == {"C150"}


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
    assert sum(issue.rule_id == "C150" for _, issue, _ in issues) == 4


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


def test_new_noqa_suppresses_replacement():
    assert _lint("AttrPutS('x', 'd', 'e', 'a'); # noqa: C150", "metadata") == []


@pytest.mark.parametrize("rule_id", ["C130", "S120"])
def test_legacy_noqa_does_not_suppress_new_rule(rule_id):
    code = f"ItemSkip(); # noqa: {rule_id}"
    with pytest.warns(LintiConfigWarning):
        assert len(_lint(code)) == 1
    with pytest.warns(LintiConfigWarning):
        assert _lint(code, rule=ItemSkipRule()) == []


def test_explain_documents_both_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["explain", "C150"])
    assert result.exit_code == 0
    assert "Misplaced Function" in result.output
    assert "misplaced_function" in result.output
    with pytest.warns(LintiConfigWarning, match="C130.*deprecated.*C150"):
        result = CliRunner().invoke(app, ["explain", "C130"])
    assert result.exit_code == 0
    assert "ItemSkip Block Usage" in result.output
    assert "Deprecated: use C150" in result.output
