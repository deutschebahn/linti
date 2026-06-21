"""File linting operations for process files and directories."""

from pathlib import Path
from typing import Optional

import typer

from linti.cli.config_loader import load_config
from linti.lexer.lexer import Lexer
from linti.linter.api import lint_process
from linti.linter.fixer import auto_fix_process
from linti.linter.linter import Linter
from linti.linter.reporter import (
    FileProcedureIssue,
    ProcedureIssue,
    directory_report_exit_code,
    file_report_exit_code,
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


def report_issues(file_path: Path, issues: list[ProcedureIssue]) -> int:
    """Report issues for a single file. Returns exit code."""
    for line in render_file_report(file_path, issues):
        typer.echo(line)
    return file_report_exit_code(issues)


def report_directory_issues(
    directory: Path, all_file_issues: list[FileProcedureIssue]
) -> int:
    """Report issues for a directory of files. Returns exit code."""
    for line in render_directory_report(directory, all_file_issues):
        typer.echo(line)
    return directory_report_exit_code(all_file_issues)


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
) -> Optional[list]:
    """Lint one process file through a provider-backed flow."""
    try:
        provider = provider_for_path(file_path)
        process_name = require_single_process_name(provider)
        process = provider.get_process(process_name)
    except Exception as e:
        if silent_errors:
            return None
        typer.echo(f"Error loading file: {e}", err=True)
        raise typer.Exit(code=1) from e

    if linter is None:
        cfg = load_config(file_path, config)
        token_rules, statement_rules = create_rules(cfg, select=select)
        linter = Linter(rules=token_rules, statement_rules=statement_rules)

    if auto_fix:
        typer.echo(f"Applying auto-fixes where supported in {file_path}")

    _print_debug(process, show_tokens, show_ast)

    issue_map = lint_process(provider, process_name, linter, auto_fix=auto_fix)
    issues = issue_map[process_name]

    if return_issues:
        return issues

    raise typer.Exit(code=report_issues(file_path, issues))


def lint_directory(
    directory: Path,
    show_tokens: bool,
    show_ast: bool,
    config: Optional[Path],
    auto_fix: bool = False,
    select: Optional[str] = None,
) -> None:
    """Lint all process files in a directory recursively."""
    process_files = sorted(
        {
            *directory.rglob("*.yaml"),
            *directory.rglob("*.yml"),
            *directory.rglob("*.ti"),
        }
    )

    if not process_files:
        typer.echo(f"No process files found in {directory}", err=False)
        raise typer.Exit(code=0)

    cfg = load_config(directory, config)
    all_file_issues = []

    for proc_file in process_files:
        token_rules, statement_rules = create_rules(cfg, select=select)
        linter = Linter(rules=token_rules, statement_rules=statement_rules)

        file_issues = lint_process_file(
            proc_file,
            show_tokens,
            show_ast,
            config,
            linter,
            return_issues=True,
            silent_errors=True,
            auto_fix=auto_fix,
        )
        if file_issues:
            for proc_name, issue, source_line in file_issues:
                all_file_issues.append((proc_file, proc_name, issue, source_line))

    raise typer.Exit(code=report_directory_issues(directory, all_file_issues))
