from pathlib import Path

from linti.cli.file_linter import report_directory_issues, report_issues
from linti.linter.lint_issue import Fix, LintIssue
from linti.linter.reporter import (
    directory_report_exit_code,
    file_report_exit_code,
    format_issue,
    render_directory_report,
    render_file_report,
)


def test_report_issues_prints_auto_fix_summary_and_command(capsys):
    file_path = Path("process.ti")
    issues = [
        (
            "prolog",
            LintIssue(
                message="fixable",
                line=1,
                column=1,
                position=0,
                rule_id="F110",
                fix=Fix(position=0, old_value="if", new_value="IF"),
            ),
            1,
        ),
        (
            "prolog",
            LintIssue(
                message="not-fixable",
                line=2,
                column=1,
                position=10,
                rule_id="N110",
            ),
            1,
        ),
    ]

    exit_code = report_issues(file_path, issues)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Total Issues: 2 (Auto-fixable: 1)" in out
    assert "Run: linti process.ti --auto-fix" in out


def test_report_issues_with_procedure_context(capsys):
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

    exit_code = report_issues(file_path, issues)

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


def test_format_issue_path_before_line_for_vscode_links():
    """path:line:col must come first so VS Code terminal creates a clickable link."""
    issue = LintIssue(message="test msg", line=3, column=5, position=0, rule_id="S210")
    result = format_issue(Path("proc.yaml"), "prolog", issue, source_line=10)

    # File path and line number must be adjacent (path:line:col) for VS Code link detection.
    # The procedure label comes AFTER, not between path and line number.
    assert result.startswith("proc.yaml:12:5")
    assert "(PrologProcedure)" in result
    assert result.index("proc.yaml:12:5") < result.index("(PrologProcedure)")


def test_render_file_report_is_cli_independent_and_contains_summary():
    file_path = Path("process.ti")
    issues = [
        (
            "prolog",
            LintIssue(
                message="fixable",
                line=1,
                column=1,
                position=0,
                rule_id="F110",
                fix=Fix(position=0, old_value="if", new_value="IF"),
            ),
            1,
        ),
        (
            "prolog",
            LintIssue(
                message="not-fixable",
                line=2,
                column=1,
                position=10,
                rule_id="N110",
            ),
            1,
        ),
    ]

    lines = render_file_report(file_path, issues)
    report = "\n".join(lines)

    assert "LINTING ISSUES" in report
    assert "Total Issues: 2 (Auto-fixable: 1)" in report
    assert "Run: linti process.ti --auto-fix" in report
    assert file_report_exit_code(issues) == 1
    assert file_report_exit_code([]) == 0


def test_render_directory_report_is_cli_independent_and_contains_summary():
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

    lines = render_directory_report(directory, issues)
    report = "\n".join(lines)

    assert "LINTING ISSUES" in report
    assert "Total Files:   2" in report
    assert "Total Issues:  2" in report
    assert "Auto-fixable: 1" in report
    assert "Run: linti example --auto-fix" in report
    assert directory_report_exit_code(issues) == 1
    assert directory_report_exit_code([]) == 0
