"""Linting a set of processes fetched from a TM1 server.

The file-based counterpart is :mod:`linti.cli.file_linter`; this module is the
same shape for a source that has no paths. It reuses that module's
``linter_from_config`` and the reporter wholesale — the only genuinely different
parts are how sources are named and that nothing here can be auto-fixed.
"""

import fnmatch
from typing import Optional

import typer

from linti.cli.file_linter import linter_from_config
from linti.config import Config
from linti.linter.api import lint_process_model
from linti.linter.reporter import (
    FileProcedureIssue,
    ProcedureIssue,
    SourceLabel,
    directory_report_exit_code,
    file_report_exit_code,
    filter_by_severity,
    render_directory_report,
    render_file_report,
)
from linti.provider.tm1 import TM1Provider
from linti.rules.rule_factory import RuleSelection

#: Shown in place of the ``--auto-fix`` hint. Findings on a server process are
#: reported with the same 🔧 marker as anywhere else, so without this the report
#: would advertise a workflow that does not exist yet.
NO_AUTO_FIX_HINT = (
    "Auto-fix is not supported for processes on a TM1 server yet; "
    "the server was not modified."
)


def source_label(profile: str, process_name: Optional[str] = None) -> SourceLabel:
    """How a server-side process is named in a report.

    A URL-ish label rather than a bare name, so a finding is never mistaken for
    one from a file in the working directory.
    """
    root = f"tm1://{profile}"
    return f"{root}/{process_name}" if process_name else root


def select_processes(names: list[str], patterns: list[str]) -> list[str]:
    """Filter *names* by ``fnmatch`` *patterns*, case-insensitively.

    Case-insensitive because TM1 object names are: a user who types
    ``sales.*`` means the same thing as ``Sales.*`` and would be baffled by an
    empty result. No patterns means everything.
    """
    if not patterns:
        return names
    lowered = [pattern.lower() for pattern in patterns]
    return [
        name
        for name in names
        if any(fnmatch.fnmatchcase(name.lower(), pattern) for pattern in lowered)
    ]


def lint_tm1_processes(
    provider: TM1Provider,
    names: list[str],
    profile: str,
    cfg: Config,
    selection: Optional[RuleSelection] = None,
) -> int:
    """Lint every process in *names* and print one report. Returns the exit code.

    A process that cannot be fetched does not abort the run: the failure is
    collected, reported at the end, and forces a non-zero exit. Linting 200
    processes should not be lost because one of them is locked.
    """
    results: list[tuple[str, list[ProcedureIssue]]] = []
    failures: list[str] = []

    for name in names:
        try:
            process = provider.get_process(name)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            failures.append(f"{source_label(profile, name)}: {exc}")
            continue

        # Rules are stateful, so every process gets its own Linter — the same
        # reason lint_files builds one per file.
        results.append(
            (name, lint_process_model(process, linter_from_config(cfg, selection)))
        )

    # Which report to render follows what was actually linted, not what was
    # asked for: with one process fetched and one failed, a single-process
    # report would otherwise claim a clean run for the process that failed.
    if len(results) == 1:
        name, issues = results[0]
        exit_code = _report_single(source_label(profile, name), issues, cfg)
    elif results:
        all_issues: list[FileProcedureIssue] = [
            (source_label(profile, name), proc_name, issue, source_line)
            for name, issues in results
            for proc_name, issue, source_line in issues
        ]
        exit_code = _report_many(source_label(profile), all_issues, cfg)
    else:
        exit_code = 0

    for failure in failures:
        typer.echo(f"Error: {failure}", err=True)
    return max(exit_code, 1) if failures else exit_code


def _report_single(
    label: SourceLabel, issues: list[ProcedureIssue], cfg: Config
) -> int:
    issues = filter_by_severity(issues, cfg.min_severity)
    for line in render_file_report(label, issues, cfg.fail_on, NO_AUTO_FIX_HINT):
        typer.echo(line)
    return file_report_exit_code(issues, cfg.fail_on)


def _report_many(
    label: SourceLabel, issues: list[FileProcedureIssue], cfg: Config
) -> int:
    issues = filter_by_severity(issues, cfg.min_severity)
    for line in render_directory_report(label, issues, cfg.fail_on, NO_AUTO_FIX_HINT):
        typer.echo(line)
    return directory_report_exit_code(issues, cfg.fail_on)
