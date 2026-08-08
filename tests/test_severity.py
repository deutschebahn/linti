"""Severity: rule weight, config override, exit codes and the --severity filter."""

from pathlib import Path

import pytest
import typer
import yaml
from typer.testing import CliRunner

from linti.cli.file_linter import (
    lint_process_file,
    report_directory_issues,
    report_issues,
)
from linti.cli.config_loader import load_config
from linti.cli.main import app
from linti.config import Config, LintiConfigWarning
from linti.linter.api import lint_process_model
from linti.linter.lint_issue import DEFAULT_SEVERITY, LintIssue, Severity
from linti.linter.linter import Linter
from linti.linter.reporter import (
    count_warnings,
    directory_report_exit_code,
    file_report_exit_code,
    filter_by_severity,
)
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules.errors.unknown_statement_rule import UnknownStatementRule
from linti.rules.rule_factory import create_rules


def _issue(rule_id: str, severity: Severity) -> LintIssue:
    return LintIssue(
        message=f"{rule_id} finding",
        line=1,
        column=1,
        position=0,
        rule_id=rule_id,
        severity=severity,
    )


def _proc_issues(*severities: Severity) -> list:
    return [("prolog", _issue(f"X{i}", sev), 1) for i, sev in enumerate(severities)]


def _file_issues(*severities: Severity) -> list:
    return [
        (Path("a.ti"), "prolog", _issue(f"X{i}", sev), 1)
        for i, sev in enumerate(severities)
    ]


# --- the scale itself ------------------------------------------------------


def test_error_outranks_warning():
    assert Severity.ERROR.rank > Severity.WARNING.rank
    assert Severity.ERROR.at_least(Severity.WARNING)
    assert not Severity.WARNING.at_least(Severity.ERROR)
    assert Severity.WARNING.at_least(Severity.WARNING)


def test_default_severity_is_error():
    """Every pre-severity rule keeps blocking exactly as it did."""
    assert DEFAULT_SEVERITY is Severity.ERROR
    assert LintIssue("m", 1, 1, 0).severity is Severity.ERROR


# --- exit codes ------------------------------------------------------------


def test_warnings_alone_do_not_fail_the_run():
    issues = _proc_issues(Severity.WARNING, Severity.WARNING)
    assert file_report_exit_code(issues) == 0
    assert directory_report_exit_code(_file_issues(Severity.WARNING)) == 0


def test_a_single_error_fails_the_run():
    issues = _proc_issues(Severity.WARNING, Severity.ERROR)
    assert file_report_exit_code(issues) == 1


def test_strict_makes_warnings_fail():
    issues = _proc_issues(Severity.WARNING)
    assert file_report_exit_code(issues, Severity.WARNING) == 1
    assert (
        directory_report_exit_code(_file_issues(Severity.WARNING), Severity.WARNING)
        == 1
    )


def test_no_issues_exits_zero():
    assert file_report_exit_code([]) == 0
    assert file_report_exit_code([], Severity.WARNING) == 0


# --- the --severity filter -------------------------------------------------


def test_filter_drops_everything_below_the_floor():
    issues = _proc_issues(Severity.WARNING, Severity.ERROR)
    assert len(filter_by_severity(issues, Severity.ERROR)) == 1
    assert len(filter_by_severity(issues, Severity.WARNING)) == 2


def test_filter_handles_directory_tuples():
    """The LintIssue sits at a different index in the four-element tuple."""
    issues = _file_issues(Severity.WARNING, Severity.ERROR)
    kept = filter_by_severity(issues, Severity.ERROR)
    assert [entry[2].severity for entry in kept] == [Severity.ERROR]


def test_filtered_out_findings_cannot_fail_the_run(capsys):
    """What is hidden must not block: filtering happens before the exit code."""
    issues = _proc_issues(Severity.WARNING)
    exit_code = report_issues(
        Path("p.ti"), issues, fail_on=Severity.WARNING, min_severity=Severity.ERROR
    )
    assert exit_code == 0
    assert "No issues found" in capsys.readouterr().out


def test_count_warnings():
    assert count_warnings(_proc_issues(Severity.WARNING, Severity.ERROR)) == 1
    assert count_warnings(_file_issues(Severity.WARNING, Severity.WARNING)) == 2


# --- report rendering ------------------------------------------------------


def test_warning_note_names_the_escape_hatch(capsys):
    report_issues(Path("p.ti"), _proc_issues(Severity.WARNING))
    out = capsys.readouterr().out
    assert "Warnings:" in out
    assert "--fail-on warning" in out
    assert "⚠" in out


def test_warning_note_is_suppressed_when_warnings_block(capsys):
    """With --fail-on warning they *do* block, so the reassurance would lie."""
    report_issues(
        Path("p.ti"), _proc_issues(Severity.WARNING), fail_on=Severity.WARNING
    )
    assert "not failing the run" not in capsys.readouterr().out


def test_directory_report_shows_warning_note(capsys):
    report_directory_issues(Path("procs"), _file_issues(Severity.WARNING))
    assert "Warnings:" in capsys.readouterr().out


# --- rule metadata and config override ------------------------------------


def test_e110_is_a_warning_by_default():
    assert UnknownStatementRule.METADATA.severity is Severity.WARNING
    assert UnknownStatementRule().severity is Severity.WARNING


def test_rules_are_errors_unless_they_say_otherwise():
    token_rules, statement_rules = create_rules(Config(), select="F110")
    assert token_rules or statement_rules
    for rule in [*token_rules, *statement_rules]:
        assert rule.severity is Severity.ERROR


def test_config_promotes_a_warning_to_an_error():
    cfg = Config.model_validate({"rules": {"unknown_statement": {"severity": "error"}}})
    _, statement_rules = create_rules(cfg, select="E110")
    assert statement_rules
    assert all(rule.severity is Severity.ERROR for rule in statement_rules)


def test_config_demotes_an_error_to_a_warning():
    """Works through a typed rule config too, not just the extra="allow" path."""
    cfg = Config.model_validate({"rules": {"keyword_casing": {"severity": "warning"}}})
    token_rules, _ = create_rules(cfg, select="F110")
    assert token_rules
    assert all(rule.severity is Severity.WARNING for rule in token_rules)


def test_override_reaches_every_instance_of_a_fan_out_rule():
    """One `whitespace` config key fans out into the whole F22x-F27x group."""
    cfg = Config.model_validate({"rules": {"whitespace": {"severity": "warning"}}})
    token_rules, statement_rules = create_rules(cfg, select="F2")
    instances = [*token_rules, *statement_rules]
    assert len(instances) > 1
    assert all(rule.severity is Severity.WARNING for rule in instances)


def test_invalid_severity_warns_and_keeps_the_default():
    with pytest.warns(LintiConfigWarning, match="Invalid severity 'loud'"):
        cfg = Config.model_validate(
            {"rules": {"unknown_statement": {"severity": "loud"}}}
        )
    _, statement_rules = create_rules(cfg, select="E110")
    assert all(rule.severity is Severity.WARNING for rule in statement_rules)


def test_invalid_severity_on_a_typed_rule_config_does_not_raise():
    """A typo must cost that rule its override, not abort the whole run."""
    with pytest.warns(LintiConfigWarning, match="Invalid severity 'warn'"):
        cfg = Config.model_validate({"rules": {"keyword_casing": {"severity": "warn"}}})
    assert cfg.rules.keyword_casing.severity is None
    token_rules, _ = create_rules(cfg, select="F110")
    assert all(rule.severity is Severity.ERROR for rule in token_rules)


def test_invalid_severity_leaves_the_rest_of_the_rule_config_intact():
    with pytest.warns(LintiConfigWarning):
        cfg = Config.model_validate(
            {"rules": {"keyword_casing": {"severity": "warn", "style": "lowercase"}}}
        )
    assert cfg.rules.keyword_casing.style == "lowercase"


# --- end to end through the linter ----------------------------------------


def _process(code: str) -> ProcessIR:
    return ProcessIR(name="p", prolog=ProcedureInfo(code=code))


def test_e110_issues_are_stamped_as_warnings():
    token_rules, statement_rules = create_rules(Config(), select="E110")
    linter = Linter(rules=token_rules, statement_rules=statement_rules)
    issues = lint_process_model(_process("nValue = 1\n"), linter)
    assert issues
    assert all(issue.severity is Severity.WARNING for _, issue, _ in issues)
    assert file_report_exit_code(issues) == 0


def test_e110_promoted_by_config_blocks_the_run():
    cfg = Config.model_validate({"rules": {"unknown_statement": {"severity": "error"}}})
    token_rules, statement_rules = create_rules(cfg, select="E110")
    linter = Linter(rules=token_rules, statement_rules=statement_rules)
    issues = lint_process_model(_process("nValue = 1\n"), linter)
    assert issues
    assert file_report_exit_code(issues) == 1


# --- S900, the parser-level pseudo rule -----------------------------------


def _deeply_nested(depth: int) -> str:
    return "IF(1=1);\n" * depth + "nX = 1;\n" + "ENDIF;\n" * depth


def test_s900_is_a_warning_by_default():
    linter = Linter(max_nesting_depth=5)
    issues = lint_process_model(_process(_deeply_nested(10)), linter)
    assert [issue.rule_id for _, issue, _ in issues] == ["S900"]
    assert issues[0][1].severity is Severity.WARNING
    assert file_report_exit_code(issues) == 0


def test_s900_severity_is_configurable():
    linter = Linter(max_nesting_depth=5, nesting_depth_severity=Severity.ERROR)
    issues = lint_process_model(_process(_deeply_nested(10)), linter)
    assert file_report_exit_code(issues) == 1


def test_s900_can_be_switched_off():
    linter = Linter(max_nesting_depth=5, nesting_depth_enabled=False)
    assert lint_process_model(_process(_deeply_nested(10)), linter) == []


def test_nesting_depth_config_reaches_the_linter(tmp_path):
    """rules.nesting_depth is a real config key, not just a Linter kwarg."""
    (tmp_path / "linti.yaml").write_text(
        yaml.safe_dump(
            {"rules": {"nesting_depth": {"severity": "error", "enabled": False}}}
        )
    )
    cfg = load_config(tmp_path, tmp_path / "linti.yaml")
    assert cfg.rules.nesting_depth.severity is Severity.ERROR
    assert cfg.rules.nesting_depth.enabled is False


# --- linti explain ---------------------------------------------------------


def _explain(tmp_path: Path, monkeypatch, rules: dict, *args: str):
    (tmp_path / "linti.yaml").write_text(yaml.safe_dump({"rules": rules}))
    monkeypatch.chdir(tmp_path)
    return CliRunner().invoke(app, ["explain", *args])


def test_explain_reports_the_effective_severity(tmp_path, monkeypatch):
    """Promoting E110 must not leave explain promising it never fails a run."""
    result = _explain(
        tmp_path, monkeypatch, {"unknown_statement": {"severity": "error"}}, "E110"
    )
    assert result.exit_code == 0
    assert "does not fail the run" not in result.stdout
    assert "Error" in result.stdout
    assert "linti.yaml" in result.stdout


def test_explain_shows_the_default_severity_without_config(tmp_path, monkeypatch):
    result = _explain(tmp_path, monkeypatch, {}, "E110")
    assert "does not fail the run" in result.stdout
    assert "set by linti.yaml" not in result.stdout


def test_explain_marks_a_demoted_rule(tmp_path, monkeypatch):
    result = _explain(
        tmp_path, monkeypatch, {"keyword_casing": {"severity": "warning"}}, "F110"
    )
    assert "does not fail the run" in result.stdout
    assert "linti.yaml" in result.stdout


def test_explain_list_marks_overridden_rules(tmp_path, monkeypatch):
    result = _explain(
        tmp_path, monkeypatch, {"keyword_casing": {"severity": "warning"}}
    )
    assert result.exit_code == 0
    assert "severity overridden by linti.yaml" in result.stdout


# --- API entry point -------------------------------------------------------


def test_lint_process_file_honours_its_own_config(tmp_path, monkeypatch):
    """The exit path must use the config it just loaded, not the defaults."""
    (tmp_path / "p.ti").write_text("nB=1;\n")  # F220 spacing issue
    (tmp_path / "linti.yaml").write_text(
        yaml.safe_dump({"rules": {"whitespace": {"severity": "warning"}}})
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(typer.Exit) as excinfo:
        lint_process_file(tmp_path / "p.ti")
    assert excinfo.value.exit_code == 0


# --- top-level config ------------------------------------------------------


def test_fail_on_and_min_severity_default_to_report_everything_block_errors():
    cfg = Config()
    assert cfg.fail_on is Severity.ERROR
    assert cfg.min_severity is Severity.WARNING


def test_yaml_spells_the_filter_severity(tmp_path):
    """The config key matches the flag: `severity:` for `--severity`."""
    (tmp_path / "linti.yaml").write_text(
        yaml.safe_dump({"fail_on": "warning", "severity": "error"})
    )
    cfg = load_config(tmp_path, tmp_path / "linti.yaml")
    assert cfg.fail_on is Severity.WARNING
    assert cfg.min_severity is Severity.ERROR


def test_config_is_still_constructible_under_the_internal_name():
    assert Config(min_severity=Severity.ERROR).min_severity is Severity.ERROR
