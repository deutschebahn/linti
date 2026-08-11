"""Issue formatting and reporting

This module provides pure functions for formatting lint issues into strings
and collecting summary statistics.

All issues are represented as ``ProcedureIssue`` tuples regardless of the
source file format — the provider layer normalises everything.
"""

import re
from pathlib import Path
from shlex import quote
from typing import Optional, Union

from linti.linter.lint_issue import LintIssue, Severity

#: What a report names as the source of a finding. A ``Path`` for a file on
#: disk; a plain string for a source that never was one, such as
#: ``tm1://prod/SalesLoad`` for a process fetched from a server.
SourceLabel = Union[Path, str]

# Canonical issue type returned by the API layer.
ProcedureIssue = tuple[str, LintIssue, int]
FileProcedureIssue = tuple[SourceLabel, str, LintIssue, int]

#: Marker prefixed to a finding that does not block the run.
WARNING_INDICATOR = " ⚠️"


def filter_by_severity(issues: list, floor: Severity) -> list:
    """Drop findings below *floor*.

    Applied once, before anything is rendered or counted, so what is shown and
    what decides the exit code never diverge: a finding the user asked not to
    see cannot silently fail their build. Works for both ``ProcedureIssue`` and
    ``FileProcedureIssue`` tuples — the ``LintIssue`` is the second-to-last
    element in each.
    """
    return [entry for entry in issues if entry[-2].severity.at_least(floor)]


def separator(char: str = "=", width: int = 70) -> str:
    """Return a horizontal separator line."""
    return char * width


def adjust_line_numbers_in_message(message: str, source_line: int) -> str:
    """Adjust all ``line N`` references in *message* by *source_line* offset."""

    def _replace(match: re.Match) -> str:
        return f"line {int(match.group(1)) + source_line - 1}"

    return re.sub(r"line\s+(\d+)", _replace, message)


def format_issue(
    file_path: SourceLabel, proc_name: str, issue: LintIssue, source_line: int
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
    file_path: SourceLabel,
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


def count_warnings(issues: list) -> int:
    """How many findings carry ``Severity.WARNING``."""
    return sum(1 for entry in issues if entry[-2].severity is Severity.WARNING)


#: One row of the per-rule breakdown: ``(rule_id, total, fixable)``.
RuleTally = tuple[str, int, int]

#: Stand-in ID for a finding that carries none, so the row still has a label.
UNKNOWN_RULE_ID = "-"


def count_by_rule(issues: list) -> list[RuleTally]:
    """Per-rule totals, least frequent first.

    Ascending on purpose: the breakdown is printed above the totals, so the
    rule worth acting on first ends up closest to the bottom of the terminal.
    Ties fall back to the canonical group order, keeping the output stable
    between runs. Works for both ``ProcedureIssue`` and ``FileProcedureIssue``
    tuples — like the other counters here, the ``LintIssue`` is ``entry[-2]``.
    """
    from linti.rules.rule_ids import group_sort_key

    totals: dict[str, int] = {}
    fixables: dict[str, int] = {}
    for entry in issues:
        issue = entry[-2]
        rule_id = issue.rule_id or UNKNOWN_RULE_ID
        totals[rule_id] = totals.get(rule_id, 0) + 1
        fixables[rule_id] = fixables.get(rule_id, 0) + (issue.fix is not None)

    return sorted(
        ((rule_id, total, fixables[rule_id]) for rule_id, total in totals.items()),
        key=lambda tally: (tally[1], group_sort_key(tally[0])),
    )


def _rule_breakdown(issues: list, indent: str) -> list[str]:
    """The ``Issues by rule:`` block, or nothing when there is nothing to show."""
    from linti.rules.rule_ids import rule_name

    tallies = count_by_rule(issues)
    if not tallies:
        return []

    id_width = max(len(rule_id) for rule_id, _, _ in tallies)
    count_width = max(len(str(total)) for _, total, _ in tallies)
    fixable_texts = {
        rule_id: f"({fixable} fixable)" if fixable else ""
        for rule_id, _, fixable in tallies
    }
    # Zero when no rule contributed a fixable issue — the column then collapses
    # entirely rather than padding every row against an empty header.
    fixable_width = max(len(text) for text in fixable_texts.values())

    lines = [f"{indent}Issues by rule:"]
    for rule_id, total, _ in tallies:
        columns = [f"{rule_id:<{id_width}}", f"{total:>{count_width}}"]
        if fixable_width:
            columns.append(f"{fixable_texts[rule_id]:<{fixable_width}}")
        columns.append(rule_name(rule_id))
        lines.append(f"{indent}  {'  '.join(columns)}".rstrip())
    return lines


def _warning_note(warnings_count: int, fail_on: Severity) -> list[str]:
    """Summary line naming the non-blocking findings, or nothing when there are none.

    Deliberately prominent. A finding that never fails a build is a finding
    nobody acts on, so the count has to stay in view — otherwise the honest
    default (P110/P900 do not break CI) just turns into silence.
    """
    if not warnings_count or fail_on is not Severity.ERROR:
        return []
    return [
        f"  Warnings:      {warnings_count} "
        f"(warnings don't fail the run by default; to fail on them, "
        f"pass --fail-on warning)"
    ]


def _indicators(issue: LintIssue) -> str:
    """Trailing markers for one issue line: auto-fixable and/or non-blocking."""
    marks = ""
    if issue.fix is not None:
        marks += " 🔧"
    if issue.severity is Severity.WARNING:
        marks += WARNING_INDICATOR
    return marks


def _fix_hint(fix_command: Optional[str], target: SourceLabel) -> list[str]:
    """The closing line about auto-fixing, for a report that has fixable issues.

    *fix_command* left unset means "the standard file workflow applies", which
    is the only case that existed before sources other than files did. A source
    that cannot be auto-fixed passes its own line instead, and an empty string
    suppresses the hint entirely.
    """
    if fix_command is None:
        return [f"Run: linti {quote(str(target))} --auto-fix"]
    return [fix_command] if fix_command else []


def render_file_report(
    file_path: SourceLabel,
    issues: list[ProcedureIssue],
    fail_on: Severity = Severity.ERROR,
    fix_command: Optional[str] = None,
) -> list[str]:
    """Build output lines for a single-source report.

    *fix_command* overrides the closing ``Run: linti … --auto-fix`` hint; see
    :func:`_fix_hint`.
    """
    if not issues:
        return [f"✓ No issues found in {file_path}"]

    total, fixable_count = summary(issues)
    lines = [f"\n{separator()}\nLINTING ISSUES\n{separator()}\n"]
    for proc_name, issue, source_line in issues:
        lines.append(
            f"{format_issue(file_path, proc_name, issue, source_line)}"
            f"{_indicators(issue)}"
        )

    lines.append(f"\n{separator()}")
    # Breakdown first, totals last: in a terminal the closing lines are the
    # ones left on screen, so the run's verdict has to come after the detail.
    lines.extend(_rule_breakdown(issues, ""))
    lines.append("")
    lines.append(f"Total Issues: {total} (Auto-fixable: {fixable_count})")
    lines.extend(_warning_note(count_warnings(issues), fail_on))
    if fixable_count > 0:
        lines.extend(_fix_hint(fix_command, file_path))
    lines.append("")
    return lines


def render_directory_report(
    directory: SourceLabel,
    all_file_issues: list[FileProcedureIssue],
    fail_on: Severity = Severity.ERROR,
    fix_command: Optional[str] = None,
) -> list[str]:
    """Build output lines for a multi-source report.

    *fix_command* overrides the closing ``Run: linti … --auto-fix`` hint; see
    :func:`_fix_hint`.
    """
    if not all_file_issues:
        return [f"\n✓ No issues found in {directory}"]

    issues_by_file: dict[SourceLabel, list[ProcedureIssue]] = {}
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
            lines.append(
                f"{format_issue(file_path, proc_name, issue, source_line)}"
                f"{_indicators(issue)}"
            )

        lines.append(f"    Issues: {len(file_issues)} (Fixable: {file_fixable})")
        total_issues += len(file_issues)
        total_fixable += file_fixable

    lines.append(f"\n{separator()}")
    lines.append("SUMMARY")
    lines.append(separator())
    # See render_file_report: detail above, totals below.
    lines.extend(_rule_breakdown(all_file_issues, "  "))
    lines.append("")
    lines.append(f"  Total Files:   {len(issues_by_file)}")
    lines.append(f"  Total Issues:  {total_issues}")
    lines.append(f"    ├─ Auto-fixable: {total_fixable}")
    lines.append(f"    └─ Other:       {total_issues - total_fixable}")
    lines.extend(_warning_note(count_warnings(all_file_issues), fail_on))

    if total_fixable > 0:
        lines.extend(f"\n  {line}" for line in _fix_hint(fix_command, directory))
    lines.append("")
    return lines


def _exit_code(issues: list, fail_on: Severity) -> int:
    """1 when any finding reaches *fail_on*, else 0."""
    return 1 if any(entry[-2].severity.at_least(fail_on) for entry in issues) else 0


def file_report_exit_code(
    issues: list[ProcedureIssue], fail_on: Severity = Severity.ERROR
) -> int:
    """Return standard exit code for single-file report."""
    return _exit_code(issues, fail_on)


def directory_report_exit_code(
    all_file_issues: list[FileProcedureIssue], fail_on: Severity = Severity.ERROR
) -> int:
    """Return standard exit code for directory report."""
    return _exit_code(all_file_issues, fail_on)
