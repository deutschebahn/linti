"""Tests for the ConstantEvaluationIndex (cross-block variable tracking)."""

from linti.linter.api import lint_process_model
from linti.semantic.constant_evaluation import ConstantEvaluationIndex
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.semantic.possible_values import PartialString, PossibleValues
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.parser.ast import Program
from linti.rules.Rule import BaseStatementRule


def _process(prolog=None, metadata=None, data=None, epilog=None, **kwargs):
    def info(code):
        return ProcedureInfo(code=code) if code is not None else None

    return ProcessIR(
        name="test_process",
        prolog=info(prolog),
        metadata=info(metadata),
        data=info(data),
        epilog=info(epilog),
        **kwargs,
    )


def _exact(index, name, block, line):
    """Shorthand: the single fully known value at a point, or None."""
    return index.possible_values_at(name, block, line).exact


# -- literals and folding ---------------------------------------------------


def test_string_literal_is_tracked():
    index = ConstantEvaluationIndex(_process(prolog="sDim = 'Region';"))
    assert _exact(index, "sDim", "prolog", 2) == "Region"


def test_number_literal_is_tracked():
    index = ConstantEvaluationIndex(_process(prolog="nMax = 12;"))
    assert _exact(index, "nMax", "prolog", 2) == 12.0


def test_value_is_not_visible_before_assignment():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;\nsDim = 'Region';"))
    assert _exact(index, "sDim", "prolog", 1) is None


def test_arithmetic_folding():
    index = ConstantEvaluationIndex(
        _process(prolog="nA = 2;\nnB = 3;\nnC = nA * nB + 1;")
    )
    assert _exact(index, "nC", "prolog", 4) == 7.0


def test_string_concatenation_folding():
    index = ConstantEvaluationIndex(
        _process(prolog="sDim = 'Region';\nsFull = sDim | ':' | 'Default';")
    )
    assert _exact(index, "sFull", "prolog", 3) == "Region:Default"


def test_unary_minus_folding():
    index = ConstantEvaluationIndex(_process(prolog="nNeg = -5;"))
    assert _exact(index, "nNeg", "prolog", 2) == -5.0


def test_division_by_zero_is_unknown():
    index = ConstantEvaluationIndex(_process(prolog="nX = 1 / 0;"))
    assert _exact(index, "nX", "prolog", 2) is None


def test_backslash_division_folding():
    index = ConstantEvaluationIndex(_process(prolog="nX = 6 \\ 2;"))
    assert _exact(index, "nX", "prolog", 2) == 3.0


def test_backslash_division_by_zero_is_zero():
    # TI's \ operator defines divide-by-zero as 0, not undefined.
    index = ConstantEvaluationIndex(_process(prolog="nX = 1 \\ 0;"))
    assert _exact(index, "nX", "prolog", 2) == 0.0


def test_reassignment_updates_value():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;\nx = 2;"))
    assert _exact(index, "x", "prolog", 1) == 1.0
    assert _exact(index, "x", "prolog", 3) == 2.0


def test_lookup_is_case_insensitive():
    index = ConstantEvaluationIndex(_process(prolog="sDim = 'Region';"))
    assert _exact(index, "SDIM", "prolog", 2) == "Region"


# -- dynamic values stay unknown ---------------------------------------------


def test_function_call_is_unknown():
    index = ConstantEvaluationIndex(_process(prolog="sDim = CellGetS('c', 'x');"))
    assert _exact(index, "sDim", "prolog", 2) is None


def test_expression_over_unknown_is_unknown():
    index = ConstantEvaluationIndex(
        _process(prolog="sDyn = TimSt(Now, '\\Y');\nsFull = sDyn | ':x';")
    )
    assert _exact(index, "sFull", "prolog", 3) is None


def test_parameter_is_unknown():
    index = ConstantEvaluationIndex(
        _process(prolog="sCopy = pDim;", parameters=["pDim"])
    )
    assert _exact(index, "pDim", "prolog", 1) is None
    assert _exact(index, "sCopy", "prolog", 2) is None


def test_never_assigned_variable_is_unknown():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;"))
    assert _exact(index, "sNope", "prolog", 5) is None


# -- assigned cascade level -----------------------------------------------------


def test_never_assigned_variable_reports_unassigned():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;"))
    pv = index.possible_values_at("sNope", "prolog", 5)
    assert not pv.assigned
    assert pv.is_unknown


def test_dynamic_assignment_reports_assigned_but_unknown():
    index = ConstantEvaluationIndex(_process(prolog="sDim = CellGetS('c', 'x');"))
    pv = index.possible_values_at("sDim", "prolog", 2)
    assert pv.assigned
    assert pv.is_unknown
    assert pv.exact is None


def test_variable_is_unassigned_before_its_first_write():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;\nsDim = 'Region';"))
    assert not index.possible_values_at("sDim", "prolog", 1).assigned
    assert index.possible_values_at("sDim", "prolog", 3).assigned


# -- partial string values ----------------------------------------------------


def test_partial_string_keeps_known_fragment():
    index = ConstantEvaluationIndex(_process(prolog="sName = 'prefix_' | pDyn;"))
    pv = index.possible_values_at("sName", "prolog", 2)
    # Not fully known -> exact stays None.
    assert pv.exact is None
    partial = pv.partial
    assert isinstance(partial, PartialString)
    assert partial.known_fragments == ("prefix_",)


def test_partial_string_keeps_fragments_on_both_sides_of_a_gap():
    index = ConstantEvaluationIndex(_process(prolog="sName = 'a_' | pDyn | '_z';"))
    partial = index.possible_values_at("sName", "prolog", 2).partial
    assert isinstance(partial, PartialString)
    assert partial.known_fragments == ("a_", "_z")


def test_partial_string_composes_through_further_concatenation():
    code = "sMid = 'x_' | pDyn;\nsFull = sMid | '_y';"
    index = ConstantEvaluationIndex(_process(prolog=code))
    partial = index.possible_values_at("sFull", "prolog", 3).partial
    assert isinstance(partial, PartialString)
    assert partial.known_fragments == ("x_", "_y")


def test_fully_known_concatenation_is_not_partial():
    index = ConstantEvaluationIndex(_process(prolog="sFull = 'a' | 'b' | 'c';"))
    pv = index.possible_values_at("sFull", "prolog", 2)
    assert pv.exact == "abc"
    assert pv.partial is None


def test_fully_unknown_concatenation_is_not_partial():
    index = ConstantEvaluationIndex(
        _process(prolog="sFull = CellGetS('c', 'x') | pDyn;")
    )
    pv = index.possible_values_at("sFull", "prolog", 2)
    assert pv.exact is None
    assert pv.partial is None


def test_partial_value_visible_across_sections():
    index = ConstantEvaluationIndex(
        _process(prolog="sName = 'p_' | pDyn;", epilog="x = 1;")
    )
    partial = index.possible_values_at("sName", "epilog", 1).partial
    assert isinstance(partial, PartialString)
    assert partial.known_fragments == ("p_",)


# -- conditional and loop invalidation ----------------------------------------


def test_assignment_in_if_branch_is_unknown_after():
    code = "sDim = 'Region';\nIF(pFlag = 1);\n  sDim = 'Other';\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    # Known before the branch assignment, unknown after it.
    assert _exact(index, "sDim", "prolog", 2) == "Region"
    assert _exact(index, "sDim", "prolog", 5) is None


def test_assignment_in_while_is_unknown_from_loop_start():
    code = "n = 1;\nWHILE(n < 5);\n  n = n + 1;\nEND;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    assert _exact(index, "n", "prolog", 1) == 1.0
    # Inside the loop, earlier lines re-execute: unknown from the WHILE on.
    assert _exact(index, "n", "prolog", 2) is None
    assert _exact(index, "n", "prolog", 5) is None


def test_assignment_in_nested_if_inside_while_is_unknown_from_loop_start():
    code = "x = 1;\nWHILE(n < 5);\n  IF(y = 1);\n    x = 2;\n  ENDIF;\nEND;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    assert _exact(index, "x", "prolog", 3) is None


def test_variable_untouched_by_loop_stays_known():
    code = "sDim = 'Region';\nWHILE(n < 5);\n  n = n + 1;\nEND;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    assert _exact(index, "sDim", "prolog", 5) == "Region"


# -- cross-section tracking ----------------------------------------------------


def test_prolog_value_is_visible_in_data_and_epilog():
    index = ConstantEvaluationIndex(
        _process(prolog="sDim = 'Region:Default';", data="x = 1;", epilog="y = 2;")
    )
    assert _exact(index, "sDim", "data", 1) == "Region:Default"
    assert _exact(index, "sDim", "epilog", 1) == "Region:Default"


def test_later_section_value_is_not_visible_earlier():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;", epilog="sX = 'e';"))
    assert _exact(index, "sX", "prolog", 99) is None
    assert _exact(index, "sX", "epilog", 2) == "e"


def test_read_before_write_in_data_section_is_unknown():
    # Data runs once per record: at the top of the section the variable
    # still holds the previous record's value, so it must not be trusted.
    index = ConstantEvaluationIndex(_process(prolog="x = 1;", data="y = x;\nx = 2;"))
    assert _exact(index, "x", "data", 1) is None
    # After the in-section assignment it is known again (same every record).
    assert _exact(index, "x", "data", 3) == 2.0


def test_self_increment_in_data_section_is_unknown():
    index = ConstantEvaluationIndex(_process(prolog="n = 0;", data="n = n + 1;"))
    assert _exact(index, "n", "data", 2) is None
    assert _exact(index, "n", "epilog", 1) is None


def test_prolog_value_survives_data_section_that_does_not_assign_it():
    index = ConstantEvaluationIndex(
        _process(prolog="sDim = 'Region';", data="nOther = 1;")
    )
    assert _exact(index, "sDim", "data", 99) == "Region"


def test_data_value_is_visible_in_epilog():
    index = ConstantEvaluationIndex(_process(data="x = 5;"))
    assert _exact(index, "x", "epilog", 1) == 5.0


# -- branch variants (if/elseif/else joins, forall/exists) --------------------


def test_if_else_tracks_both_variants():
    code = "IF(pFlag = 1);\n  sDim = 'Region';\nELSE;\n  sDim = 'Product';\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sDim", "prolog", 6)
    assert isinstance(pv, PossibleValues)
    assert pv.values == frozenset({"Region", "Product"})
    assert pv.complete
    # Not a single scalar -> exact stays None.
    assert pv.exact is None


def test_all_of_and_any_of_over_variants():
    code = "IF(pFlag = 1);\n  sDim = 'Region';\nELSE;\n  sDim = 'Product';\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sDim", "prolog", 6)
    assert pv.all_of(lambda v: v in {"Region", "Product"})
    assert not pv.all_of(lambda v: v == "Region")
    assert pv.any_of(lambda v: v == "Region")
    assert pv.any_of(lambda v: v == "Product")
    assert not pv.any_of(lambda v: v == "Other")


def test_all_of_and_any_of_cover_the_single_value_case():
    """The cascade: a rule reasoning over all values also gets the exact case."""
    index = ConstantEvaluationIndex(_process(prolog="sDim = 'Region';"))
    pv = index.possible_values_at("sDim", "prolog", 2)
    assert pv.exact == "Region"
    assert pv.values == frozenset({"Region"})
    assert pv.all_of(lambda v: v == "Region")
    assert pv.any_of(lambda v: v == "Region")


def test_all_of_and_any_of_never_accept_partial_variants():
    """Arbitrary predicates are only decidable on fully known values."""
    code = "IF(p = 1);\n  sV = 'Dim:Hier';\nELSE;\n  sV = 'Dim:' | pHier;\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 6)
    # The partial variant cannot prove an arbitrary predicate — even one that
    # would hold on any string.
    assert not pv.all_of(lambda v: True)
    assert not pv.any_of(lambda v: isinstance(v, PartialString))
    # The exact variant still counts for the existential question.
    assert pv.any_of(lambda v: v == "Dim:Hier")


# -- substring evidence (all_contain / any_contains) ---------------------------


def test_all_contain_accepts_mixed_exact_and_partial_evidence():
    code = "IF(p = 1);\n  sV = 'Dim:Hier';\nELSE;\n  sV = 'Dim:' | pHier;\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 6)
    # Exact variant contains ':', partial variant proves it via a fragment.
    assert pv.all_contain(":")
    assert pv.any_contains(":")


def test_all_contain_fails_when_a_partial_variant_lacks_evidence():
    code = "IF(p = 1);\n  sV = 'Dim:Hier';\nELSE;\n  sV = 'x_' | pDyn;\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 6)
    # The gap in 'x_' | pDyn *might* contain ':' — a maybe is not evidence.
    assert not pv.all_contain(":")
    assert pv.any_contains(":")  # the exact variant proves the existential


def test_any_contains_needs_definite_evidence():
    code = "IF(p = 1);\n  sV = 'ab';\nELSE;\n  sV = 'x_' | pDyn;\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 6)
    assert not pv.any_contains(":")


def test_all_contain_requires_complete_variants():
    code = "IF(p = 1);\n  sV = 'a where b';\nELSE;\n  sV = CellGetS('c', 'x');\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 6)
    # The dynamic branch may hold anything — no universal guarantee.
    assert not pv.all_contain(" where ")
    assert pv.any_contains(" where ")


def test_all_contain_over_where_clause_variants():
    code = (
        "IF(p = 1);\n"
        "  sSql = 'SELECT * FROM t WHERE x = 1';\n"
        "ELSE;\n"
        "  sSql = 'SELECT * FROM t WHERE y = ' | pVal;\n"
        "ENDIF;"
    )
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sSql", "prolog", 6)
    assert pv.all_contain(" WHERE ")


def test_number_variant_is_never_substring_evidence():
    code = "IF(p = 1);\n  v = 'a:b';\nELSE;\n  v = 12;\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("v", "prolog", 6)
    assert not pv.all_contain(":")
    assert pv.any_contains(":")


def test_no_else_keeps_pre_value_as_variant():
    code = "sDim = 'Default';\nIF(pFlag = 1);\n  sDim = 'Region';\nENDIF;"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sDim", "prolog", 5)
    assert pv.values == frozenset({"Default", "Region"})
    assert pv.complete
    # Before the IF the pre-value is still the single known value.
    assert _exact(index, "sDim", "prolog", 1) == "Default"


def test_dynamic_branch_keeps_exists_but_not_forall():
    code = (
        "IF(pFlag = 1);\n"
        "  sDim = 'Region';\n"
        "ELSE;\n"
        "  sDim = CellGetS('c', 'x');\n"
        "ENDIF;"
    )
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sDim", "prolog", 6)
    assert not pv.complete
    assert pv.any_of(lambda v: v == "Region")  # exists still holds
    assert not pv.all_of(lambda v: v == "Region")  # forall cannot
    assert pv.exact is None


def test_elseif_chain_enumerates_all_variants():
    code = (
        "IF(a = 1);\n"
        "  sV = 'x';\n"
        "ELSEIF(a = 2);\n"
        "  sV = 'y';\n"
        "ELSE;\n"
        "  sV = 'z';\n"
        "ENDIF;"
    )
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sV", "prolog", 8)
    assert pv.values == frozenset({"x", "y", "z"})
    assert pv.complete


def test_variants_fold_through_expression():
    code = "IF(a = 1);\n  sV = 'A';\nELSE;\n  sV = 'B';\nENDIF;\nsFull = sV | '_x';"
    index = ConstantEvaluationIndex(_process(prolog=code))
    pv = index.possible_values_at("sFull", "prolog", 7)
    assert pv.values == frozenset({"A_x", "B_x"})
    assert pv.complete
    assert pv.all_of(lambda v: v.endswith("_x"))


def test_too_many_variants_degrade_to_unknown():
    code = (
        "IF(a = 1);\n"
        "  sV = 'x';\n"
        "ELSEIF(a = 2);\n"
        "  sV = 'y';\n"
        "ELSE;\n"
        "  sV = 'z';\n"
        "ENDIF;"
    )
    index = ConstantEvaluationIndex(_process(prolog=code), max_values_per_variable=2)
    pv = index.possible_values_at("sV", "prolog", 8)
    assert pv.is_unknown
    assert pv.exact is None


def test_possible_values_unknown_when_never_assigned():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;"))
    assert index.possible_values_at("sNope", "prolog", 5).is_unknown


def test_context_possible_values_without_index_is_unassigned():
    ctx = LintContext(block="prolog")
    pv = ctx.possible_values("x", 1)
    assert pv.is_unknown
    assert not pv.assigned
    assert pv.exact is None


# -- laziness and integration ---------------------------------------------------


def test_index_builds_lazily():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;"))
    assert index._events is None
    index.possible_values_at("x", "prolog", 2)
    assert index._events is not None


def test_invalid_block_name_reports_unassigned():
    index = ConstantEvaluationIndex(_process(prolog="x = 1;"))
    pv = index.possible_values_at("x", "nosuchblock", 2)
    assert pv.exact is None
    assert not pv.assigned


def test_lint_pipeline_exposes_constants_to_rules():
    """Rules reach cross-section values through context.possible_values()."""
    seen = {}

    class _CaptureRule(BaseStatementRule):
        CONFIG_KEY = ""  # not registered in the global rule registry

        @property
        def RULE_ID(self):
            return "T999"

        def interested_in(self):
            return [Program]

        def visit(self, statement, context):
            seen[context.block] = context.possible_values("sDim", 1).exact
            return []

    process = _process(prolog="sDim = 'Region:Default';", data="x = 1;")
    linter = Linter(rules=[], statement_rules=[_CaptureRule()])
    lint_process_model(process, linter)

    assert seen["data"] == "Region:Default"


def test_lint_pipeline_exposes_variants_to_rules():
    """Rules reach branch variants through context.possible_values()."""
    seen = {}

    class _VariantRule(BaseStatementRule):
        CONFIG_KEY = ""

        @property
        def RULE_ID(self):
            return "T997"

        def interested_in(self):
            return [Program]

        def visit(self, statement, context):
            pv = context.possible_values("sDim", 99)
            seen["all"] = pv.all_of(lambda v: v in {"Region", "Product"})
            seen["values"] = pv.values
            return []

    code = "IF(pFlag = 1);\n  sDim = 'Region';\nELSE;\n  sDim = 'Product';\nENDIF;"
    process = _process(prolog=code)
    linter = Linter(rules=[], statement_rules=[_VariantRule()])
    lint_process_model(process, linter)

    assert seen["values"] == frozenset({"Region", "Product"})
    assert seen["all"] is True


# -- shared parse cache (each section lexed/parsed at most once) --------------


def _count_parses(monkeypatch):
    """Return a dict whose ``n`` counts ``Parser.parse()`` invocations."""
    import linti.parser.parser as parser_module

    counts = {"n": 0}
    original = parser_module.Parser.parse

    def counting_parse(self):
        counts["n"] += 1
        return original(self)

    monkeypatch.setattr(parser_module.Parser, "parse", counting_parse)
    return counts


def test_lint_run_parses_each_section_once_even_with_index(monkeypatch):
    """A rule querying the index must not trigger a second parse pass."""
    counts = _count_parses(monkeypatch)

    class _QueryRule(BaseStatementRule):
        CONFIG_KEY = ""

        @property
        def RULE_ID(self):
            return "T998"

        def interested_in(self):
            return [Program]

        def visit(self, statement, context):
            # Force the index to build during the metadata pass.
            context.possible_values("sDim", 1)
            return []

    process = _process(
        prolog="sDim = 'Region';",
        metadata="a = 1;",
        data="b = 2;",
        epilog="c = 3;",
    )
    linter = Linter(rules=[], statement_rules=[_QueryRule()])
    lint_process_model(process, linter)

    # Four sections, each parsed exactly once.
    assert counts["n"] == 4


def test_index_without_shared_cache_parses_each_section_once(monkeypatch):
    """A stand-alone index still parses every section a single time."""
    counts = _count_parses(monkeypatch)

    index = ConstantEvaluationIndex(
        _process(prolog="x = 1;", metadata="y = 2;", data="z = 3;", epilog="w = 4;")
    )
    index.possible_values_at("x", "epilog", 1)
    index.possible_values_at("y", "epilog", 1)  # second query must not re-parse

    assert counts["n"] == 4
