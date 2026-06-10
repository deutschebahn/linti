"""Issue reporting and formatting for CLI output."""

import re
from pathlib import Path
from shlex import quote

import typer

from linti.linter.lint_issue import LintIssue


# Output formatting helpers (no dependencies)
def _separator(char: str = "=", width: int = 70) -> str:
    """Create a separator line."""
    return char * width


def _section_header(title: str, width: int = 70) -> str:
    """Format a section header with separator."""
    return f"\n{_separator('=', width)}\n{title}\n{_separator('=', width)}\n"


def adjust_line_numbers_in_message(message: str, source_line: int) -> str:
    """
    Adjust all line numbers mentioned in a message.

    Args:
        message: Original message with line numbers
        source_line: Line offset to add

    Returns:
        Message with adjusted line numbers
    """

    def replace_line_num(match: re.Match) -> str:
        line_num = int(match.group(1))
        adjusted = line_num + source_line - 1
        return f"line {adjusted}"

    return re.sub(r"line\s+(\d+)", replace_line_num, message)


def format_issue_for_ti(file_path: Path, issue: LintIssue) -> str:
    """
    Format a linting issue for a TI file.

    Args:
        file_path: Path to the TI file
        issue: LintIssue object

    Returns:
        Formatted issue string
    """
    rule_id_str = f"[{issue.rule_id}] " if issue.rule_id else ""
    return f"{file_path}:{issue.line}:{issue.column} - {rule_id_str}{issue.message}"


def format_issue_for_yaml(
    file_path: Path, proc_name: str, issue: LintIssue, source_line: int
) -> str:
    """
    Format a linting issue for a structured file with procedure context.

    Args:
        file_path: Path to the source file
        proc_name: Name of the procedure (prolog/metadata/data/epilog)
        issue: LintIssue object
        source_line: Line number where the procedure starts in the source file

    Returns:
        Formatted issue string with adjusted line numbers
    """
    adjusted_line = source_line + issue.line - 1
    adjusted_message = adjust_line_numbers_in_message(issue.message, source_line)
    rule_id_str = f"[{issue.rule_id}] " if issue.rule_id else ""
    return f"{file_path}:{adjusted_line}:{issue.column} ({proc_name.capitalize()}Procedure) - {rule_id_str}{adjusted_message}"


def report_issues(file_path: Path, issues: list[LintIssue]) -> int:
    """
    Report linting issues for a single TI file.

    Args:
        file_path: Path to the linted file
        issues: List of LintIssue objects

    Returns:
        Exit code: 1 if issues found, 0 if clean.
    """
    if issues:
        typer.echo(_section_header("LINTING ISSUES"))
        fixable_count = 0
        for issue in issues:
            is_fixable = issue.fix is not None
            if is_fixable:
                fixable_count += 1
            fixable_indicator = " ✓" if is_fixable else ""
            typer.echo(f"{format_issue_for_ti(file_path, issue)}{fixable_indicator}")

        # Summary for single file
        typer.echo("\n" + _separator())
        typer.echo(f"Total Issues: {len(issues)} (Auto-fixable: {fixable_count})")
        if fixable_count > 0:
            typer.echo(f"Run: linti {quote(str(file_path))} --auto-fix")
        typer.echo()
        return 1
    else:
        typer.echo(f"✓ No issues found in {file_path}")
        return 0


def report_yaml_issues(
    file_path: Path, all_issues: list[tuple[str, LintIssue, int]]
) -> int:
    """
    Report linting issues for a YAML file with procedure context.

    Args:
        file_path: Path to the YAML file
        all_issues: List of (proc_name, issue, source_line) tuples

    Returns:
        Exit code: 1 if issues found, 0 if clean.
    """
    if all_issues:
        typer.echo(_section_header("LINTING ISSUES"))
        fixable_count = 0
        for proc_name, issue, source_line in all_issues:
            is_fixable = issue.fix is not None
            if is_fixable:
                fixable_count += 1
            fixable_indicator = " ✓" if is_fixable else ""
            typer.echo(
                f"{format_issue_for_yaml(file_path, proc_name, issue, source_line)}{fixable_indicator}"
            )

        # Summary for single file
        typer.echo("\n" + _separator())
        typer.echo(f"  Total Issues: {len(all_issues)} (Auto-fixable: {fixable_count})")
        if fixable_count > 0:
            typer.echo(f"  Run: linti {quote(str(file_path))} --auto-fix")
        typer.echo()
        return 1
    else:
        typer.echo(f"✓ No issues found in {file_path}")
        return 0


def report_directory_issues(
    directory: Path, all_file_issues: list[tuple[Path, str, LintIssue, int]]
) -> int:
    """
    Report linting issues for all files in a directory.

    Args:
        directory: Path to the directory
        all_file_issues: List of (file_path, proc_name, issue, source_line) tuples

    Returns:
        Exit code: 1 if issues found, 0 if clean.
    """
    if not all_file_issues:
        typer.echo(f"\n✓ No issues found in {directory}")
        return 0

    # Group issues by file
    issues_by_file = {}
    for file_path, proc_name, issue, source_line in all_file_issues:
        if file_path not in issues_by_file:
            issues_by_file[file_path] = []
        issues_by_file[file_path].append((proc_name, issue, source_line))

    # Report issues grouped by file
    typer.echo(_section_header("LINTING ISSUES"))

    total_issues = 0
    total_fixable = 0

    for file_path in sorted(issues_by_file.keys()):
        file_issues = issues_by_file[file_path]
        file_fixable = sum(1 for _, issue, _ in file_issues if issue.fix is not None)

        typer.echo(f"\n  FILE: {file_path}")
        typer.echo(f"  {_separator('-', 50)}")

        for proc_name, issue, source_line in file_issues:
            is_fixable = issue.fix is not None
            fixable_indicator = " ✓" if is_fixable else ""
            typer.echo(
                f"{format_issue_for_yaml(file_path, proc_name, issue, source_line)}{fixable_indicator}"
            )

        typer.echo(f"    Issues: {len(file_issues)} (Fixable: {file_fixable})")
        total_issues += len(file_issues)
        total_fixable += file_fixable

    # Final summary
    typer.echo("\n" + _separator("="))
    typer.echo("SUMMARY")
    typer.echo(_separator("="))
    typer.echo(f"  Total Files:   {len(issues_by_file)}")
    typer.echo(f"  Total Issues:  {total_issues}")
    typer.echo(f"    ├─ Auto-fixable: {total_fixable}")
    typer.echo(f"    └─ Other:       {total_issues - total_fixable}")

    if total_fixable > 0:
        typer.echo(f"\n  Run: linti {quote(str(directory))} --auto-fix")
    typer.echo()

    return 1
