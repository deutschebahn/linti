from pathlib import Path

from linti.cli.file_linter import report_directory_issues, report_issues
from linti.linter.lint_issue import Fix, LintIssue
from linti.linter.reporter import (
    count_by_rule,
    directory_report_exit_code,
    file_report_exit_code,
    format_issue,
    render_directory_report,
    render_file_report,
)


def _issue(rule_id: str, fixable: bool = False, line: int = 1) -> LintIssue:
    """A minimal finding for the aggregation tests."""
    return LintIssue(
        message="msg",
        line=line,
        column=1,
        position=0,
        rule_id=rule_id,
        fix=Fix(position=0, old_value="if", new_value="IF") if fixable else None,
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
                rule_id="C130",
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
    issue = LintIssue(message="test msg", line=3, column=5, position=0, rule_id="C210")
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


def test_count_by_rule_orders_ascending_by_count_then_group():
    issues = [
        ("prolog", _issue("F110", fixable=True), 1),
        ("prolog", _issue("F110"), 1),
        ("prolog", _issue("F110", fixable=True), 1),
        ("prolog", _issue("F310"), 1),
        ("prolog", _issue("F310"), 1),
        ("prolog", _issue("N110"), 1),
        ("prolog", _issue(""), 1),
    ]

    # Ascending, so the rule worth acting on first lands closest to the totals.
    # N110 precedes the unlabelled bucket because "-" has no known group.
    assert count_by_rule(issues) == [
        ("N110", 1, 0),
        ("-", 1, 0),
        ("F310", 2, 0),
        ("F110", 3, 2),
    ]


def test_count_by_rule_sums_across_files():
    issues = [
        (Path("example/p1.yaml"), "prolog", _issue("F110", fixable=True), 1),
        (Path("example/p2.yaml"), "prolog", _issue("F110"), 1),
        (Path("example/p2.yaml"), "epilog", _issue("N110"), 1),
    ]

    assert count_by_rule(issues) == [("N110", 1, 0), ("F110", 2, 1)]


def test_render_file_report_lists_issues_by_rule_before_the_totals():
    issues = [
        ("prolog", _issue("F110", fixable=True), 1),
        ("prolog", _issue("F110", fixable=True), 1),
        ("prolog", _issue("N110"), 1),
    ]

    report = "\n".join(render_file_report(Path("process.ti"), issues))

    assert "Issues by rule:" in report
    assert "F110  2  (2 fixable)  Keyword Casing" in report
    # Blank fixable column, padded so the name column stays aligned.
    assert "N110  1               Variable Prefix Naming" in report
    # The verdict has to be the last thing left on screen.
    assert report.index("Issues by rule:") < report.index("Total Issues:")


def test_render_directory_report_lists_issues_by_rule_before_the_totals():
    issues = [
        (Path("example/p1.yaml"), "prolog", _issue("F110", fixable=True), 1),
        (Path("example/p2.yaml"), "prolog", _issue("F110", fixable=True), 1),
        (Path("example/p2.yaml"), "prolog", _issue("N110"), 1),
    ]

    report = "\n".join(render_directory_report(Path("example"), issues))

    assert "Issues by rule:" in report
    assert "F110  2  (2 fixable)  Keyword Casing" in report
    assert report.index("Issues by rule:") < report.index("Total Files:")
    assert report.index("Total Issues:") < report.index("Run: linti")


def test_rule_breakdown_drops_the_fixable_column_when_nothing_is_fixable():
    issues = [("prolog", _issue("N110"), 1), ("prolog", _issue("C110"), 1)]

    report = "\n".join(render_file_report(Path("process.ti"), issues))

    assert "fixable)" not in report
    assert "N110  1  Variable Prefix Naming" in report


def test_rule_breakdown_absent_when_there_are_no_issues():
    assert render_file_report(Path("process.ti"), []) == [
        "✓ No issues found in process.ti"
    ]
    assert "Issues by rule:" not in "\n".join(render_directory_report(Path("x"), []))
