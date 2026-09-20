"""Input-hardening tests: nesting-depth diagnostic and file-size ceiling."""

import json
from pathlib import Path

import pytest

from linti.linter.api import NESTING_DEPTH_RULE_ID, lint_process_model
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.factory import provider_for_path
from linti.provider.git import GitProvider


def test_deep_nesting_surfaces_p900_diagnostic():
    """An over-nested procedure yields one P900 LintIssue, not a crash."""
    code = "IF(1);" * 300 + "nX = 1;\n" + "ENDIF;" * 300
    process = ProcessIR(name="proc", prolog=ProcedureInfo(code=code))
    linter = Linter(max_nesting_depth=150)

    issues = lint_process_model(process, linter)

    assert len(issues) == 1
    proc_name, issue, _source_line = issues[0]
    assert proc_name == "prolog"
    assert issue.rule_id == NESTING_DEPTH_RULE_ID
    assert "nesting depth" in issue.message.lower()


def test_normal_nesting_produces_no_depth_diagnostic():
    """A shallowly nested procedure lints without a P900 diagnostic."""
    code = "IF(1);\nnX = 1;\nENDIF;\n"
    process = ProcessIR(name="proc", prolog=ProcedureInfo(code=code))
    linter = Linter(max_nesting_depth=150)

    issues = lint_process_model(process, linter)

    assert all(issue.rule_id != NESTING_DEPTH_RULE_ID for _proc, issue, _line in issues)


TI_CODE = "#region Prolog\nnX = 1;\n#endregion\n"


def test_oversized_file_rejected_by_factory(tmp_path: Path):
    ti_path = tmp_path / "big.ti"
    ti_path.write_text("nX = 1;\n" * 1000)

    with pytest.raises(ValueError, match="size limit"):
        provider_for_path(ti_path, max_file_size=100)


def test_normal_sized_file_accepted_by_factory(tmp_path: Path):
    ti_path = tmp_path / "ok.ti"
    ti_path.write_text("nX = 1;\n")

    provider = provider_for_path(ti_path, max_file_size=10 * 1024 * 1024)
    process = provider.get_process("ok")
    assert process.prolog is not None


def test_oversized_linked_ti_rejected_in_git_get_process(tmp_path: Path):
    """The Git-format linked .ti is size-checked when read, not just the JSON."""
    json_path = tmp_path / "proc.json"
    ti_path = tmp_path / "proc.ti"
    json_path.write_text(json.dumps({"Name": "proc", "Code@Code.link": "proc.ti"}))
    ti_path.write_text(TI_CODE * 500)

    # JSON is small enough to construct the provider, but the linked .ti is over
    # the limit — the ceiling must apply at get_process time.
    provider = GitProvider(json_path, max_file_size=200)
    with pytest.raises(ValueError, match="size limit"):
        provider.get_process("proc")


@pytest.mark.parametrize(
    "expression",
    [
        "(" * 1500 + "1" + ")" * 1500,
        "-" * 1500 + "1",
        "Abs(" * 1500 + "1" + ")" * 1500,
    ],
)
def test_expression_nesting_yields_diagnostic(expression):
    process = ProcessIR(name="proc", prolog=ProcedureInfo(f"nX = {expression};"))
    issues = lint_process_model(process, Linter())
    assert [issue.rule_id for _, issue, _ in issues] == [NESTING_DEPTH_RULE_ID]


def test_exponential_string_folding_degrades_to_unknown():
    from linti.semantic.constant_evaluation import ConstantEvaluationIndex

    code = "sData = 'x';\n" + "sData = sData | sData;\n" * 40
    process = ProcessIR(name="proc", prolog=ProcedureInfo(code))
    values = ConstantEvaluationIndex(process).possible_values_at("sData", "prolog", 41)
    assert values.exact is None
    assert not values.complete


def test_partial_string_segment_expansion_is_bounded():
    from linti.semantic.constant_evaluation import ConstantEvaluationIndex

    code = "sData = 'x' | pDynamic;\n" + "sData = sData | sData;\n" * 40
    process = ProcessIR(name="proc", prolog=ProcedureInfo(code))
    values = ConstantEvaluationIndex(process).possible_values_at("sData", "prolog", 41)
    assert not values.values


def test_total_constant_storage_is_bounded(monkeypatch):
    from linti.semantic import constant_evaluation as ce

    monkeypatch.setattr(ce, "MAX_TRACKED_STRING_CHARS", 10)
    code = "sA = '123456';\nsB = sA | '7';\nsC = '8';\n"
    process = ProcessIR(name="proc", prolog=ProcedureInfo(code))
    index = ce.ConstantEvaluationIndex(process)
    assert index.possible_values_at("sA", "prolog", 1).exact == "123456"
    assert not index.possible_values_at("sB", "prolog", 2).complete
    assert not index.possible_values_at("sC", "prolog", 3).complete


def test_constant_evaluation_work_is_bounded(monkeypatch):
    from linti.semantic import constant_evaluation as ce

    monkeypatch.setattr(ce, "MAX_EVALUATION_STEPS", 4)
    process = ProcessIR(name="proc", prolog=ProcedureInfo("nA = 1 + 2 + 3 + 4;"))
    values = ce.ConstantEvaluationIndex(process).possible_values_at("nA", "prolog", 1)
    assert not values.complete
