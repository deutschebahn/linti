"""CLI-level tests for the `lint` command's multi-path behavior."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from linti.cli.main import app
from linti.config import LintiConfigWarning

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


# --- rule selection: --extend-select and --exclude-rule / --ignore ----------


def test_ignore_drops_the_only_finding(project: Path):
    """dirty.ti's F220 is the whole report; ignoring it leaves a clean run."""
    result = runner.invoke(app, ["lint", "dirty.ti", "--ignore", "F220"])
    assert "F220" not in result.stdout
    assert "No issues found" in result.stdout
    assert result.exit_code == 0


def test_exclude_rule_is_the_same_option_as_ignore(project: Path):
    result = runner.invoke(app, ["lint", "dirty.ti", "--exclude-rule", "F2"])
    assert "F220" not in result.stdout
    assert result.exit_code == 0


def test_ignore_wins_over_select(project: Path):
    result = runner.invoke(
        app, ["lint", "dirty.ti", "--select", "F", "--ignore", "F220"]
    )
    assert "F220" not in result.stdout
    assert result.exit_code == 0


def test_extend_select_adds_an_opt_in_rule(project: Path):
    """D110 is off by default; --extend-select switches it on for this run."""
    without = runner.invoke(app, ["lint", "dirty.ti"])
    assert "D110" not in without.stdout

    result = runner.invoke(app, ["lint", "dirty.ti", "--extend-select", "D110"])
    assert "D110" in result.stdout
    # The default set is untouched — the file's F220 is still reported.
    assert "F220" in result.stdout


def test_ignoring_the_nesting_depth_pseudo_rule_warns_and_lints_on(project: Path):
    """P900 cannot be excluded; the run says so and carries on regardless."""
    with pytest.warns(LintiConfigWarning, match="P900 has no effect"):
        result = runner.invoke(app, ["lint", "dirty.ti", "--ignore", "P900"])

    # Refusing the exclusion must not cost the run its normal findings.
    assert "F220" in result.stdout
    assert result.exit_code == 1


def test_ignoring_the_deprecated_nesting_depth_id_warns_too(project: Path):
    with pytest.warns(LintiConfigWarning) as recorded:
        runner.invoke(app, ["lint", "dirty.ti", "--ignore", "S900"])

    messages = [str(warning.message) for warning in recorded]
    assert any("S900 is deprecated" in message for message in messages)
    assert any("P900 has no effect" in message for message in messages)


def test_a_mistyped_rule_id_warns(project: Path):
    # The warning names the canonical flag, whichever alias was typed.
    with pytest.warns(LintiConfigWarning, match="--exclude-rule F22O matches no rule"):
        result = runner.invoke(app, ["lint", "dirty.ti", "--ignore", "F22O"])

    # Inert, so the rule the user meant to silence is still reported.
    assert "F220" in result.stdout


def test_selector_warnings_are_emitted_once_per_run_not_once_per_file(project: Path):
    """The project fixture has two files; the warning must not double up."""
    with pytest.warns(LintiConfigWarning) as recorded:
        runner.invoke(app, ["lint", ".", "--ignore", "P900,F22O"])

    messages = [str(warning.message) for warning in recorded]
    assert sum("P900 has no effect" in message for message in messages) == 1
    assert sum("F22O matches no rule" in message for message in messages) == 1
