"""File linting operations for process files and directories."""

from pathlib import Path
from typing import Optional

import typer

from linti.cli.config_loader import load_config
from linti.cli.file_discovery import display_path
from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.api import lint_process
from linti.linter.fixer import auto_fix_process
from linti.linter.linter import Linter
from linti.linter.lint_issue import Severity
from linti.linter.reporter import (
    FileProcedureIssue,
    ProcedureIssue,
    directory_report_exit_code,
    file_report_exit_code,
    filter_by_severity,
    render_directory_report,
    render_file_report,
)
from linti.model.process_ir import ProcessIR, extract_procedures
from linti.parser.ast import UnknownStatement
from linti.parser.parser import Parser
from linti.provider.base import require_single_process_name
from linti.provider.factory import provider_for_path
from linti.rules.rule_factory import create_rules


def auto_fix_file(file_path: Path, linter: Linter) -> dict[str, int]:
    """Auto-fix a process file in place via its provider.

    Works for any supported file format (.ti, .yaml, .yml).

    Returns:
        Dict mapping procedure names to number of fixes applied.
    """
    provider = provider_for_path(file_path)
    process_name = require_single_process_name(provider)
    process = provider.get_process(process_name)

    fixes_by_proc = auto_fix_process(process, linter)
    if fixes_by_proc:
        provider.save_process(process)

    return fixes_by_proc


def linter_from_config(cfg: Config, select: Optional[str] = None) -> Linter:
    """Build a Linter carrying every config-driven limit and severity."""
    token_rules, statement_rules = create_rules(cfg, select=select)
    nesting = cfg.rules.nesting_depth
    return Linter(
        rules=token_rules,
        statement_rules=statement_rules,
        max_nesting_depth=cfg.max_nesting_depth,
        max_file_size=cfg.max_file_size,
        max_values_per_variable=cfg.max_values_per_variable,
        nesting_depth_enabled=nesting.enabled,
        nesting_depth_severity=nesting.severity or Severity.WARNING,
    )


def report_issues(
    file_path: Path,
    issues: list[ProcedureIssue],
    fail_on: Severity = Severity.ERROR,
    min_severity: Severity = Severity.WARNING,
) -> int:
    """Report issues for a single file. Returns exit code."""
    issues = filter_by_severity(issues, min_severity)
    for line in render_file_report(file_path, issues, fail_on):
        typer.echo(line)
    return file_report_exit_code(issues, fail_on)


def report_directory_issues(
    directory: Path,
    all_file_issues: list[FileProcedureIssue],
    fail_on: Severity = Severity.ERROR,
    min_severity: Severity = Severity.WARNING,
) -> int:
    """Report issues for a directory of files. Returns exit code."""
    all_file_issues = filter_by_severity(all_file_issues, min_severity)
    for line in render_directory_report(directory, all_file_issues, fail_on):
        typer.echo(line)
    return directory_report_exit_code(all_file_issues, fail_on)


def _print_debug(process: ProcessIR, show_tokens: bool, show_ast: bool) -> None:
    """Print token/AST debug output for all procedures in *process*."""
    if not (show_tokens or show_ast):
        return

    for proc_name, proc_info in extract_procedures(process).items():
        tokens = Lexer(proc_info.code).tokenize()

        if show_tokens:
            typer.echo(f"\nTokens ({proc_name}):")
            for token in tokens:
                if token.type.name not in ["WHITESPACE", "NEWLINE"]:
                    typer.echo(f"{token.type.name:15} {token.value!r}")

        if show_ast:
            ast = Parser(tokens).parse()
            typer.echo(f"\nAST ({proc_name}):")
            typer.echo(f"Program with {len(ast.statements)} statements:")
            for i, stmt in enumerate(ast.statements, 1):
                name = stmt.__class__.__name__
                if isinstance(stmt, UnknownStatement):
                    typer.echo(f"  {i}. {name} (error: {stmt.error_message})", err=True)
                else:
                    typer.echo(f"  {i}. {name}")


def lint_process_file(
    file_path: Path,
    show_tokens: bool = False,
    show_ast: bool = False,
    config: Optional[Path] = None,
    linter: Optional[Linter] = None,
    return_issues: bool = False,
    silent_errors: bool = False,
    auto_fix: bool = False,
    select: Optional[str] = None,
    report_path: Optional[Path] = None,
) -> Optional[list]:
    """Lint one process file through a provider-backed flow.

    *file_path* is used to open the provider (discovery yields absolute paths);
    *report_path*, when given, is the human-readable path shown in output.
    """
    report_path = report_path if report_path is not None else file_path
    # Resolve the linter (and thus the input-hardening limits) before opening
    # the provider, so the file-size ceiling is enforced on the initial read.
    # `cfg` also carries the reporting settings used on the exit path below;
    # when a linter is passed in, its owner has already applied them.
    cfg = None
    if linter is None:
        cfg = load_config(file_path, config)
        linter = linter_from_config(cfg, select)

    try:
        provider = provider_for_path(file_path, max_file_size=linter.max_file_size)
        process_name = require_single_process_name(provider)
        process = provider.get_process(process_name)
    except Exception as e:
        if silent_errors:
            return None
        typer.echo(f"Error loading file: {e}", err=True)
        raise typer.Exit(code=1) from e

    if auto_fix:
        typer.echo(f"Applying auto-fixes where supported in {report_path}")

    _print_debug(process, show_tokens, show_ast)

    issue_map = lint_process(provider, process_name, linter, auto_fix=auto_fix)
    issues = issue_map[process_name]

    if return_issues:
        return issues

    reporting = cfg if cfg is not None else Config()
    raise typer.Exit(
        code=report_issues(
            report_path, issues, reporting.fail_on, reporting.min_severity
        )
    )


def lint_files(
    files: list[Path],
    report_root: Path,
    cfg: Config,
    show_tokens: bool = False,
    show_ast: bool = False,
    config: Optional[Path] = None,
    auto_fix: bool = False,
    select: Optional[str] = None,
) -> int:
    """Lint an explicit list of already-discovered process files.

    The files come pre-expanded and exclusion-filtered from
    :func:`linti.cli.file_discovery.discover_process_files`, so they are
    absolute, canonical paths; each is rendered relative to the current
    directory for output via :func:`linti.cli.file_discovery.display_path`.
    *cfg* is applied to
    all of them. A single file gets the classic single-file report; multiple
    files get a combined report headed by *report_root*. Returns the exit code.
    """

    def _new_linter() -> Linter:
        return linter_from_config(cfg, select)

    def _display(file: Path) -> Path:
        # Render relative to the current directory, matching the paths a user
        # typed; report_root only anchors the combined report's header.
        return Path(display_path(file))

    if len(files) == 1:
        issues = lint_process_file(
            files[0],
            show_tokens,
            show_ast,
            config,
            _new_linter(),
            return_issues=True,
            auto_fix=auto_fix,
            report_path=_display(files[0]),
        )
        return report_issues(
            _display(files[0]), issues or [], cfg.fail_on, cfg.min_severity
        )

    all_file_issues: list[FileProcedureIssue] = []
    for proc_file in files:
        file_issues = lint_process_file(
            proc_file,
            show_tokens,
            show_ast,
            config,
            _new_linter(),
            return_issues=True,
            silent_errors=True,
            auto_fix=auto_fix,
            report_path=_display(proc_file),
        )
        if file_issues:
            display = _display(proc_file)
            for proc_name, issue, source_line in file_issues:
                all_file_issues.append((display, proc_name, issue, source_line))

    return report_directory_issues(
        report_root, all_file_issues, cfg.fail_on, cfg.min_severity
    )
