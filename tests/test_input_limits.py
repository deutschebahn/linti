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
