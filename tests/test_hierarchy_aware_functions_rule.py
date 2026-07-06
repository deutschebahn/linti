"""Tests for UseHierarchyAwareFunctionsRule (S410)."""

from linti.lexer.lexer import Lexer
from linti.linter.api import lint_process_model
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules.Rule import BaseRule
from linti.rules.semantic.hierarchy_aware_functions_rule import (
    UseHierarchyAwareFunctionsRule,
)


def _lint(
    code: str,
    mode: str = "enforce",
    context: LintContext = None,
    generic_prefixes=None,
):
    rule = UseHierarchyAwareFunctionsRule(mode=mode, generic_prefixes=generic_prefixes)
    tokens = Lexer(code).tokenize()
    return Linter(rules=[rule]).lint(tokens, context, source=code)


def _lint_process(
    prolog: str,
    mode: str = "consistent",
    generic_prefixes=None,
    name: str = "test_process",
    **sections,
):
    """Run the full S410 pipeline (both visitors + constant propagation index)."""
    rules = UseHierarchyAwareFunctionsRule.from_config(
        {"mode": mode, "generic_prefixes": generic_prefixes or []}
    )
    token_rules = [r for r in rules if isinstance(r, BaseRule)]
    statement_rules = [r for r in rules if not isinstance(r, BaseRule)]
    linter = Linter(rules=token_rules, statement_rules=statement_rules)
    process = ProcessIR(
        name=name,
        prolog=ProcedureInfo(code=prolog),
        **{k: ProcedureInfo(code=v) for k, v in sections.items()},
    )
    return [issue for _, issue, _ in lint_process_model(process, linter)]


# --- enforce mode ---


def test_enforce_flags_standard_dimension_function():
    issues = _lint("nExists = DimensionElementExists('Region', 'EMEA');")
    assert len(issues) == 1
    assert issues[0].rule_id == "S410"
    assert "DimensionElementExists" in issues[0].message
    assert "HierarchyElementExists" in issues[0].message


def test_enforce_flags_rules_function():
    issues = _lint("nIdx = DIMIX('Region', 'EMEA');")
    assert len(issues) == 1
    assert "DIMIX" in issues[0].message
    assert "ElementIndex" in issues[0].message


def test_enforce_allows_hierarchy_aware_function():
    issues = _lint("nExists = HierarchyElementExists('Region', 'Region', 'EMEA');")
    assert issues == []


def test_enforce_ignores_unrelated_functions():
    issues = _lint("nVal = CellGetN('Sales', 'EMEA', '2026');")
    assert issues == []


def test_enforce_is_case_insensitive():
    issues = _lint("nParent = elpar('Region', 'EMEA');")
    assert len(issues) == 1
    assert "ElementParent" in issues[0].message


def test_enforce_flags_every_standard_occurrence():
    code = "DimensionDeleteAllElements('Region');\nnLev = ELLEV('Region', 'EMEA');"
    issues = _lint(code)
    assert len(issues) == 2
    messages = " ".join(i.message for i in issues)
    assert "HierarchyDeleteAllElements" in messages
    assert "ElementLevel" in messages


def test_enforce_ignores_identifier_without_call_parens():
    # A bare identifier that happens to match a function name but is not a call
    # (no following '(') must not be flagged.
    issues = _lint("DIMIX = 1;")
    assert issues == []


# --- consistent mode ---


def test_consistent_allows_only_standard_functions():
    code = "nExists = DimensionElementExists('Region', 'EMEA');\nnIdx = DIMIX('Region', 'EMEA');"
    assert _lint(code, mode="consistent") == []


def test_consistent_allows_only_aware_functions():
    code = (
        "nExists = HierarchyElementExists('Region', 'Region', 'EMEA');\n"
        "nParent = ElementParent('Region', 'Region', 'EMEA');"
    )
    assert _lint(code, mode="consistent") == []


def test_consistent_flags_mixed_styles_once():
    code = (
        "nParent = ElementParent('Region', 'Region', 'EMEA');\n"
        "nIdx = DIMIX('Region', 'EMEA');\n"
        "nLev = ELLEV('Region', 'EMEA');"
    )
    issues = _lint(code, mode="consistent")
    assert len(issues) == 1
    assert issues[0].rule_id == "S410"
    assert "ElementParent" in issues[0].message
    assert "DIMIX" in issues[0].message
    # Suggests the hierarchy-aware replacement for the standard function.
    assert "ElementIndex" in issues[0].message


def test_consistent_detects_mix_across_procedures_in_same_process():
    rule = UseHierarchyAwareFunctionsRule(mode="consistent")
    linter = Linter(rules=[rule])

    prolog_ctx = LintContext(block="prolog", process_name="P")
    epilog_ctx = LintContext(block="epilog", process_name="P")

    prolog_code = "nParent = ElementParent('Region', 'Region', 'EMEA');"
    epilog_code = "nIdx = DIMIX('Region', 'EMEA');"

    prolog_issues = linter.lint(Lexer(prolog_code).tokenize(), prolog_ctx)
    epilog_issues = linter.lint(Lexer(epilog_code).tokenize(), epilog_ctx)

    assert prolog_issues == []
    assert len(epilog_issues) == 1
    assert epilog_issues[0].rule_id == "S410"


def test_default_mode_is_consistent():
    # No explicit mode: a single standard function must not be flagged
    # (consistent mode only reports mixing).
    rule = UseHierarchyAwareFunctionsRule()
    assert rule.mode == "consistent"
    tokens = Lexer("nIdx = DIMIX('Region', 'EMEA');").tokenize()
    assert Linter(rules=[rule]).lint(tokens) == []


# --- generic processes are always enforced ---


def test_generic_process_is_enforced_even_in_consistent_mode():
    code = "nIdx = DIMIX('Region', 'EMEA');"
    ctx = LintContext(block="prolog", process_name="}core.Build")
    issues = _lint(code, mode="consistent", context=ctx, generic_prefixes=["}core."])
    assert len(issues) == 1
    assert "ElementIndex" in issues[0].message


def test_non_generic_process_uses_base_consistent_mode():
    # Same prefixes configured, but this process is not generic -> consistent,
    # so a lone standard function is allowed.
    code = "nIdx = DIMIX('Region', 'EMEA');"
    ctx = LintContext(block="prolog", process_name="Load.Sales")
    issues = _lint(code, mode="consistent", context=ctx, generic_prefixes=["}core."])
    assert issues == []


def test_generic_matching_is_case_insensitive():
    code = "nIdx = DIMIX('Region', 'EMEA');"
    ctx = LintContext(block="prolog", process_name="}CORE.Build")
    issues = _lint(code, mode="consistent", context=ctx, generic_prefixes=["}core."])
    assert len(issues) == 1


def test_consistent_state_resets_between_processes():
    rule = UseHierarchyAwareFunctionsRule(mode="consistent")
    linter = Linter(rules=[rule])

    # Process A uses only aware functions; process B (different name) uses only
    # standard functions. Reusing the same rule instance must not report a mix.
    a_ctx = LintContext(block="prolog", process_name="A")
    b_ctx = LintContext(block="prolog", process_name="B")

    a_issues = linter.lint(
        Lexer("nParent = ElementParent('R', 'R', 'E');").tokenize(), a_ctx
    )
    b_issues = linter.lint(Lexer("nIdx = DIMIX('R', 'E');").tokenize(), b_ctx)

    assert a_issues == []
    assert b_issues == []


# --- colon-in-dimension-argument check (consistent mode) ---


def _assert_colon_issue(issues, aware="HierarchyElementExists"):
    assert len(issues) == 1
    assert issues[0].rule_id == "S410"
    assert "addresses a hierarchy" in issues[0].message
    assert aware in issues[0].message


def test_consistent_flags_string_literal_with_colon():
    issues = _lint_process("nX = DimensionElementExists('Region:Detail', 'EMEA');")
    _assert_colon_issue(issues)


def test_consistent_flags_variable_with_known_colon_value():
    code = "sDim = 'Region:Detail';\nnX = DimensionElementExists(sDim, 'EMEA');"
    _assert_colon_issue(_lint_process(code))


def test_consistent_flags_colon_value_assigned_in_earlier_section():
    issues = _lint_process(
        "sDim = 'Region:Detail';",
        epilog="nX = DimensionElementExists(sDim, 'EMEA');",
    )
    _assert_colon_issue(issues)


def test_consistent_flags_literal_concatenation_argument():
    issues = _lint_process("nX = DimensionElementExists(sDim | ':' | sHier, 'EMEA');")
    _assert_colon_issue(issues)


def test_consistent_flags_colon_in_if_condition():
    code = "IF(DimensionElementExists('D:H', 'e') = 0);\n  nX = 1;\nENDIF;"
    _assert_colon_issue(_lint_process(code))


def test_consistent_flags_when_all_branch_variants_have_colon():
    code = (
        "IF(pFlag = 1);\n  sDim = 'A:1';\nELSE;\n  sDim = 'B:2';\nENDIF;\n"
        "nX = DimensionElementExists(sDim, 'e');"
    )
    _assert_colon_issue(_lint_process(code))


def test_consistent_ignores_when_a_branch_variant_has_no_colon():
    code = (
        "IF(pFlag = 1);\n  sDim = 'A:1';\nELSE;\n  sDim = 'B';\nENDIF;\n"
        "nX = DimensionElementExists(sDim, 'e');"
    )
    assert _lint_process(code) == []


def test_consistent_ignores_variable_without_colon():
    code = "sDim = 'Region';\nnX = DimensionElementExists(sDim, 'EMEA');"
    assert _lint_process(code) == []


def test_consistent_ignores_unknown_value():
    code = "sDim = CellGetS('c', 'x');\nnX = DimensionElementExists(sDim, 'EMEA');"
    assert _lint_process(code) == []


def test_consistent_ignores_colon_in_non_dimension_argument():
    # The colon is in the element (second) argument, not the dimension.
    issues = _lint_process("nX = DimensionElementExists('Region', 'a:b');")
    assert issues == []


def test_enforce_reports_colon_call_by_name_without_duplicate():
    # In enforce mode the standard function is flagged by name only (no second
    # colon-specific finding on the same call).
    issues = _lint_process(
        "nX = DimensionElementExists('Region:Detail', 'EMEA');", mode="enforce"
    )
    assert len(issues) == 1
    assert "not hierarchy-aware" in issues[0].message


def test_generic_process_reports_colon_call_by_name_only():
    issues = _lint_process(
        "nX = DimensionElementExists('Region:Detail', 'EMEA');",
        mode="consistent",
        generic_prefixes=["}core."],
        name="}core.load",
    )
    assert len(issues) == 1
    assert "not hierarchy-aware" in issues[0].message
