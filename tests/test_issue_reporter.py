from pathlib import Path

from linti.cli.issue_reporter import (
    format_issue_for_yaml,
    report_directory_issues,
    report_issues,
    report_yaml_issues,
)
from linti.linter.lint_issue import Fix, LintIssue


def test_report_issues_prints_auto_fix_summary_and_command(capsys):
    file_path = Path("process.ti")
    issues = [
        LintIssue(
            message="fixable",
            line=1,
            column=1,
            position=0,
            rule_id="F110",
            fix=Fix(position=0, old_value="if", new_value="IF"),
        ),
        LintIssue(
            message="not-fixable",
            line=2,
            column=1,
            position=10,
            rule_id="N110",
        ),
    ]

    exit_code = report_issues(file_path, issues)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Total Issues: 2 (Auto-fixable: 1)" in out
    assert "Run: linti process.ti --auto-fix" in out


def test_report_yaml_issues_prints_auto_fix_summary_and_command(capsys):
    file_path = Path("process.yaml")
    issues = [
        (
            "prolog",
            LintIssue(
                message="fixable",
                line=1,
                column=1,
                position=0,
                rule_id="F310",
                fix=Fix(position=0, old_value=" ", new_value="    "),
            ),
            4,
        ),
        (
            "metadata",
            LintIssue(
                message="not-fixable",
                line=1,
                column=1,
                position=5,
                rule_id="S120",
            ),
            15,
        ),
    ]

    exit_code = report_yaml_issues(file_path, issues)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Total Issues: 2 (Auto-fixable: 1)" in out
    assert "Run: linti process.yaml --auto-fix" in out


def test_report_directory_issues_prints_auto_fix_summary_and_command(capsys):
    directory = Path("example")
    issues = [
        (
            Path("example/p1.yaml"),
            "prolog",
            LintIssue(
                message="fixable",
                line=1,
                column=1,
                position=0,
                rule_id="F110",
                fix=Fix(position=0, old_value="if", new_value="IF"),
            ),
            4,
        ),
        (
            Path("example/p2.yaml"),
            "prolog",
            LintIssue(
                message="not-fixable",
                line=1,
                column=1,
                position=0,
                rule_id="N110",
            ),
            4,
        ),
    ]

    exit_code = report_directory_issues(directory, issues)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Total Issues:  2" in out
    assert "Auto-fixable: 1" in out
    assert "Run: linti example --auto-fix" in out


def test_format_issue_for_yaml_path_before_line_for_vscode_links():
    """path:line:col must come first so VS Code terminal creates a clickable link."""
    issue = LintIssue(message="test msg", line=3, column=5, position=0, rule_id="S210")
    result = format_issue_for_yaml(Path("proc.yaml"), "prolog", issue, source_line=10)

    # File path and line number must be adjacent (path:line:col) for VS Code link detection.
    # The procedure label comes AFTER, not between path and line number.
    assert result.startswith("proc.yaml:12:5")
    assert "(PrologProcedure)" in result
    assert result.index("proc.yaml:12:5") < result.index("(PrologProcedure)")
