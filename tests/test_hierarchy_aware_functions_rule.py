"""Tests for UseHierarchyAwareFunctionsRule (S410)."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
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
