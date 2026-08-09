"""CLI-level tests for the `lint` command's multi-path behavior."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from linti.cli.main import app

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "clean.ti").write_text("nA = 1;\n")
    (tmp_path / "dirty.ti").write_text("nB=1;\n")  # F220 spacing issue
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_missing_path_still_lints_the_valid_files(project: Path):
    result = runner.invoke(app, ["lint", "clean.ti", "typo.ti"])
    # The bad path is surfaced...
    assert "Path does not exist: typo.ti" in result.stderr
    # ...but the valid file was still discovered and linted (clean -> no issues).
    assert "No issues found in clean.ti" in result.stdout
    # A missing path forces a non-zero exit.
    assert result.exit_code == 1


def test_missing_path_reported_alongside_lint_issues(project: Path):
    result = runner.invoke(app, ["lint", "dirty.ti", "typo.ti"])
    assert "Path does not exist: typo.ti" in result.stderr
    assert "F220" in result.stdout  # the valid file was linted
    assert result.exit_code == 1


def test_summary_breaks_findings_down_by_rule(project: Path):
    result = runner.invoke(app, ["lint", "dirty.ti"])
    # End to end, so the rule name really does resolve against the live registry.
    assert "Issues by rule:" in result.stdout
    assert "F220" in result.stdout
    assert "Whitespace Around Operators" in result.stdout
    assert result.stdout.index("Issues by rule:") < result.stdout.index("Total Issues:")


def test_all_paths_missing_exits_one(project: Path):
    result = runner.invoke(app, ["lint", "nope1.ti", "nope2.ti"])
    assert "Path does not exist: nope1.ti" in result.stderr
    assert "Path does not exist: nope2.ti" in result.stderr
    assert result.exit_code == 1


# --- severity: --fail-on and --severity -------------------------------------


@pytest.fixture
def unparseable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A file whose only finding is P110 (a warning), plus one that is clean."""
    (tmp_path / "broken.ti").write_text("nValue = 1\n")  # missing semicolon
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_warning_only_run_reports_but_exits_zero(unparseable: Path):
    result = runner.invoke(app, ["lint", "broken.ti", "--select", "P110"])
    assert "P110" in result.stdout
    assert "Warnings:" in result.stdout
    assert "--fail-on warning" in result.stdout
    # The whole point: linti's parser falling short must not break a build.
    assert result.exit_code == 0


def test_fail_on_warning_blocks_on_warnings(unparseable: Path):
    result = runner.invoke(
        app, ["lint", "broken.ti", "--select", "P110", "--fail-on", "warning"]
    )
    assert "P110" in result.stdout
    assert result.exit_code == 1


def test_severity_error_hides_warnings(unparseable: Path):
    result = runner.invoke(
        app, ["lint", "broken.ti", "--select", "P110", "--severity", "error"]
    )
    assert "P110" not in result.stdout
    assert "No issues found" in result.stdout
    assert result.exit_code == 0


def test_severity_filter_wins_over_fail_on(unparseable: Path):
    """A finding the user asked not to see must not fail their run either."""
    result = runner.invoke(
        app,
        [
            "lint",
            "broken.ti",
            "--select",
            "P110",
            "--fail-on",
            "warning",
            "--severity",
            "error",
        ],
    )
    assert result.exit_code == 0


def test_severity_rejects_an_unknown_level(unparseable: Path):
    result = runner.invoke(app, ["lint", "broken.ti", "--severity", "critical"])
    assert result.exit_code != 0


def test_fail_on_rejects_an_unknown_level(unparseable: Path):
    result = runner.invoke(app, ["lint", "broken.ti", "--fail-on", "critical"])
    assert result.exit_code != 0


def test_config_severity_override_promotes_e110(unparseable: Path):
    (unparseable / "linti.yaml").write_text(
        "rules:\n  unknown_statement:\n    severity: error\n"
    )
    result = runner.invoke(app, ["lint", "broken.ti", "--select", "P110"])
    assert "P110" in result.stdout
    assert result.exit_code == 1
