"""Issue formatting and reporting

This module provides pure functions for formatting lint issues into strings
and collecting summary statistics.

All issues are represented as ``ProcedureIssue`` tuples regardless of the
source file format — the provider layer normalises everything.
"""

import re
from pathlib import Path
from shlex import quote

from linti.linter.lint_issue import LintIssue

# Canonical issue type returned by the API layer.
ProcedureIssue = tuple[str, LintIssue, int]
FileProcedureIssue = tuple[Path, str, LintIssue, int]


def separator(char: str = "=", width: int = 70) -> str:
    """Return a horizontal separator line."""
    return char * width


def adjust_line_numbers_in_message(message: str, source_line: int) -> str:
    """Adjust all ``line N`` references in *message* by *source_line* offset."""

    def _replace(match: re.Match) -> str:
        return f"line {int(match.group(1)) + source_line - 1}"

    return re.sub(r"line\s+(\d+)", _replace, message)


def format_issue(
    file_path: Path, proc_name: str, issue: LintIssue, source_line: int
) -> str:
    """Format a single issue with adjusted line numbers and procedure context."""
    adjusted_line = source_line + issue.line - 1
    adjusted_message = adjust_line_numbers_in_message(issue.message, source_line)
    rule_id_str = f"[{issue.rule_id}] " if issue.rule_id else ""
    return (
        f"{file_path}:{adjusted_line}:{issue.column} "
        f"({proc_name.capitalize()}Procedure) - {rule_id_str}{adjusted_message}"
    )


def collect_report(
    all_issues: list[ProcedureIssue],
    file_path: Path,
) -> list[str]:
    """Format all issues for one file. Returns list of formatted lines."""
    return [
        format_issue(file_path, proc_name, issue, source_line)
        for proc_name, issue, source_line in all_issues
    ]


def summary(issues: list[ProcedureIssue]) -> tuple[int, int]:
    """Return (total, fixable) counts."""
    total = len(issues)
    fixable = sum(1 for _, issue, _ in issues if issue.fix is not None)
    return total, fixable


def render_file_report(file_path: Path, issues: list[ProcedureIssue]) -> list[str]:
    """Build output lines for a single-file report."""
    if not issues:
        return [f"✓ No issues found in {file_path}"]

    total, fixable_count = summary(issues)
    lines = [f"\n{separator()}\nLINTING ISSUES\n{separator()}\n"]
    for proc_name, issue, source_line in issues:
        indicator = " ✓" if issue.fix is not None else ""
        lines.append(
            f"{format_issue(file_path, proc_name, issue, source_line)}{indicator}"
        )

    lines.append(f"\n{separator()}")
    lines.append(f"Total Issues: {total} (Auto-fixable: {fixable_count})")
    if fixable_count > 0:
        lines.append(f"Run: linti {quote(str(file_path))} --auto-fix")
    lines.append("")
    return lines


def render_directory_report(
    directory: Path, all_file_issues: list[FileProcedureIssue]
) -> list[str]:
    """Build output lines for a multi-file directory report."""
    if not all_file_issues:
        return [f"\n✓ No issues found in {directory}"]

    issues_by_file: dict[Path, list[ProcedureIssue]] = {}
    for file_path, proc_name, issue, source_line in all_file_issues:
        issues_by_file.setdefault(file_path, []).append((proc_name, issue, source_line))

    lines = [f"\n{separator()}\nLINTING ISSUES\n{separator()}\n"]
    total_issues = 0
    total_fixable = 0

    for file_path in sorted(issues_by_file):
        file_issues = issues_by_file[file_path]
        file_fixable = sum(1 for _, issue, _ in file_issues if issue.fix is not None)

        lines.append(f"\n  FILE: {file_path}")
        lines.append(f"  {separator('-', 50)}")

        for proc_name, issue, source_line in file_issues:
            indicator = " ✓" if issue.fix is not None else ""
            lines.append(
                f"{format_issue(file_path, proc_name, issue, source_line)}{indicator}"
            )

        lines.append(f"    Issues: {len(file_issues)} (Fixable: {file_fixable})")
        total_issues += len(file_issues)
        total_fixable += file_fixable

    lines.append(f"\n{separator()}")
    lines.append("SUMMARY")
    lines.append(separator())
    lines.append(f"  Total Files:   {len(issues_by_file)}")
    lines.append(f"  Total Issues:  {total_issues}")
    lines.append(f"    ├─ Auto-fixable: {total_fixable}")
    lines.append(f"    └─ Other:       {total_issues - total_fixable}")

    if total_fixable > 0:
        lines.append(f"\n  Run: linti {quote(str(directory))} --auto-fix")
    lines.append("")
    return lines


def file_report_exit_code(issues: list[ProcedureIssue]) -> int:
    """Return standard exit code for single-file report."""
    return 1 if issues else 0


def directory_report_exit_code(all_file_issues: list[FileProcedureIssue]) -> int:
    """Return standard exit code for directory report."""
    return 1 if all_file_issues else 0
