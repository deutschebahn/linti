"""Tests for the ConstantPropagationIndex (cross-block variable tracking)."""

from linti.linter.api import lint_process_model
from linti.linter.constant_propagation import ConstantPropagationIndex
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
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


# -- literals and folding ---------------------------------------------------


def test_string_literal_is_tracked():
    index = ConstantPropagationIndex(_process(prolog="sDim = 'Region';"))
    assert index.value_at("sDim", "prolog", 2) == "Region"


def test_number_literal_is_tracked():
    index = ConstantPropagationIndex(_process(prolog="nMax = 12;"))
    assert index.value_at("nMax", "prolog", 2) == 12.0


def test_value_is_not_visible_before_assignment():
    index = ConstantPropagationIndex(_process(prolog="x = 1;\nsDim = 'Region';"))
    assert index.value_at("sDim", "prolog", 1) is None


def test_arithmetic_folding():
    index = ConstantPropagationIndex(
        _process(prolog="nA = 2;\nnB = 3;\nnC = nA * nB + 1;")
    )
    assert index.value_at("nC", "prolog", 4) == 7.0


def test_string_concatenation_folding():
    index = ConstantPropagationIndex(
        _process(prolog="sDim = 'Region';\nsFull = sDim | ':' | 'Default';")
    )
    assert index.value_at("sFull", "prolog", 3) == "Region:Default"


def test_unary_minus_folding():
    index = ConstantPropagationIndex(_process(prolog="nNeg = -5;"))
    assert index.value_at("nNeg", "prolog", 2) == -5.0


def test_division_by_zero_is_unknown():
    index = ConstantPropagationIndex(_process(prolog="nX = 1 / 0;"))
    assert index.value_at("nX", "prolog", 2) is None


def test_reassignment_updates_value():
    index = ConstantPropagationIndex(_process(prolog="x = 1;\nx = 2;"))
    assert index.value_at("x", "prolog", 1) == 1.0
    assert index.value_at("x", "prolog", 3) == 2.0


def test_lookup_is_case_insensitive():
    index = ConstantPropagationIndex(_process(prolog="sDim = 'Region';"))
    assert index.value_at("SDIM", "prolog", 2) == "Region"


# -- dynamic values stay unknown ---------------------------------------------


def test_function_call_is_unknown():
    index = ConstantPropagationIndex(_process(prolog="sDim = CellGetS('c', 'x');"))
    assert index.value_at("sDim", "prolog", 2) is None


def test_expression_over_unknown_is_unknown():
    index = ConstantPropagationIndex(
        _process(prolog="sDyn = TimSt(Now, '\\Y');\nsFull = sDyn | ':x';")
    )
    assert index.value_at("sFull", "prolog", 3) is None


def test_parameter_is_unknown():
    index = ConstantPropagationIndex(
        _process(prolog="sCopy = pDim;", parameters=["pDim"])
    )
    assert index.value_at("pDim", "prolog", 1) is None
    assert index.value_at("sCopy", "prolog", 2) is None


def test_never_assigned_variable_is_unknown():
    index = ConstantPropagationIndex(_process(prolog="x = 1;"))
    assert index.value_at("sNope", "prolog", 5) is None


# -- conditional and loop invalidation ----------------------------------------


def test_assignment_in_if_branch_is_unknown_after():
    code = "sDim = 'Region';\nIF(pFlag = 1);\n  sDim = 'Other';\nENDIF;"
    index = ConstantPropagationIndex(_process(prolog=code))
    # Known before the branch assignment, unknown after it.
    assert index.value_at("sDim", "prolog", 2) == "Region"
    assert index.value_at("sDim", "prolog", 5) is None


def test_assignment_in_while_is_unknown_from_loop_start():
    code = "n = 1;\nWHILE(n < 5);\n  n = n + 1;\nEND;"
    index = ConstantPropagationIndex(_process(prolog=code))
    assert index.value_at("n", "prolog", 1) == 1.0
    # Inside the loop, earlier lines re-execute: unknown from the WHILE on.
    assert index.value_at("n", "prolog", 2) is None
    assert index.value_at("n", "prolog", 5) is None


def test_assignment_in_nested_if_inside_while_is_unknown_from_loop_start():
    code = "x = 1;\nWHILE(n < 5);\n  IF(y = 1);\n    x = 2;\n  ENDIF;\nEND;"
    index = ConstantPropagationIndex(_process(prolog=code))
    assert index.value_at("x", "prolog", 3) is None


def test_variable_untouched_by_loop_stays_known():
    code = "sDim = 'Region';\nWHILE(n < 5);\n  n = n + 1;\nEND;"
    index = ConstantPropagationIndex(_process(prolog=code))
    assert index.value_at("sDim", "prolog", 5) == "Region"


# -- cross-section tracking ----------------------------------------------------


def test_prolog_value_is_visible_in_data_and_epilog():
    index = ConstantPropagationIndex(
        _process(prolog="sDim = 'Region:Default';", data="x = 1;", epilog="y = 2;")
    )
    assert index.value_at("sDim", "data", 1) == "Region:Default"
    assert index.value_at("sDim", "epilog", 1) == "Region:Default"


def test_later_section_value_is_not_visible_earlier():
    index = ConstantPropagationIndex(_process(prolog="x = 1;", epilog="sX = 'e';"))
    assert index.value_at("sX", "prolog", 99) is None
    assert index.value_at("sX", "epilog", 2) == "e"


def test_read_before_write_in_data_section_is_unknown():
    # Data runs once per record: at the top of the section the variable
    # still holds the previous record's value, so it must not be trusted.
    index = ConstantPropagationIndex(_process(prolog="x = 1;", data="y = x;\nx = 2;"))
    assert index.value_at("x", "data", 1) is None
    # After the in-section assignment it is known again (same every record).
    assert index.value_at("x", "data", 3) == 2.0


def test_self_increment_in_data_section_is_unknown():
    index = ConstantPropagationIndex(_process(prolog="n = 0;", data="n = n + 1;"))
    assert index.value_at("n", "data", 2) is None
    assert index.value_at("n", "epilog", 1) is None


def test_prolog_value_survives_data_section_that_does_not_assign_it():
    index = ConstantPropagationIndex(
        _process(prolog="sDim = 'Region';", data="nOther = 1;")
    )
    assert index.value_at("sDim", "data", 99) == "Region"


# -- laziness and integration ---------------------------------------------------


def test_index_builds_lazily():
    index = ConstantPropagationIndex(_process(prolog="x = 1;"))
    assert index._events is None
    index.value_at("x", "prolog", 2)
    assert index._events is not None


def test_invalid_block_name_returns_none():
    index = ConstantPropagationIndex(_process(prolog="x = 1;"))
    assert index.value_at("x", "nosuchblock", 2) is None


def test_context_without_index_returns_none():
    ctx = LintContext(block="prolog")
    assert ctx.constant_value("x", 1) is None


def test_lint_pipeline_exposes_constants_to_rules():
    """Rules reach cross-section values through context.constant_value()."""
    seen = {}

    class _CaptureRule(BaseStatementRule):
        CONFIG_KEY = ""  # not registered in the global rule registry

        @property
        def RULE_ID(self):
            return "T999"

        def interested_in(self):
            return [Program]

        def visit(self, statement, context):
            seen[context.block] = context.constant_value("sDim", 1)
            return []

    process = _process(prolog="sDim = 'Region:Default';", data="x = 1;")
    linter = Linter(rules=[], statement_rules=[_CaptureRule()])
    lint_process_model(process, linter)

    assert seen["data"] == "Region:Default"


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
            context.constant_value("sDim", 1)
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

    index = ConstantPropagationIndex(
        _process(prolog="x = 1;", metadata="y = 2;", data="z = 3;", epilog="w = 4;")
    )
    index.value_at("x", "epilog", 1)
    index.value_at("y", "epilog", 1)  # second query must not re-parse

    assert counts["n"] == 4
