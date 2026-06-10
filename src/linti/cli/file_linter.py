"""File linting operations for TI files, YAML files, and directories."""

from pathlib import Path
from typing import Optional

import typer

from linti.cli.auto_fixer import (
    auto_fix_ti_file,
    auto_fix_yaml_procedures,
)
from linti.cli.config_loader import load_config
from linti.cli.issue_reporter import (
    report_directory_issues,
    report_issues,
    report_yaml_issues,
)
from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.loader.base import extract_procedures
from linti.loader.yaml_loader import load_yaml_process
from linti.parser.ast import UnknownStatement
from linti.parser.parser import Parser
from linti.rules.rule_factory import create_rules


def analyze_and_lint_code(
    code: str,
    linter: Linter,
    show_tokens: bool,
    show_ast: bool,
    context_label: Optional[str] = None,
    lint_context: Optional[LintContext] = None,
) -> list:
    """
    Tokenize, parse, and lint code.

    Args:
        code: The TI code to analyze
        linter: Configured linter instance
        show_tokens: Whether to display tokens
        show_ast: Whether to display AST
        context_label: Optional context label for output (e.g., procedure name)
        lint_context: Optional LintContext with block, parameters, variables

    Returns:
        List of linting issues
    """
    lexer = Lexer(code)
    tokens = lexer.tokenize()

    if show_tokens:
        label = f" ({context_label})" if context_label else ""
        typer.echo(f"\nTokens{label}:")
        for token in tokens:
            if token.type.name not in ["WHITESPACE", "NEWLINE"]:
                typer.echo(f"{token.type.name:15} {token.value!r}")

    # Build AST
    parser = Parser(tokens)
    ast = parser.parse()

    if show_ast:
        label = f" ({context_label})" if context_label else ""
        typer.echo(f"\nAST{label}:")
        typer.echo(f"Program with {len(ast.statements)} statements:")
        for i, stmt in enumerate(ast.statements, 1):
            stmt_name = stmt.__class__.__name__
            if isinstance(stmt, UnknownStatement):
                typer.echo(
                    f"  {i}. {stmt_name} (error: {stmt.error_message})",
                    err=True,
                )
            else:
                typer.echo(f"  {i}. {stmt_name}")

    # Run linter and return issues
    return linter.lint(tokens, lint_context, ast=ast)


def lint_ti_file(
    file_path: Path,
    show_tokens: bool,
    show_ast: bool,
    config: Optional[Path],
    auto_fix: bool = False,
    select: Optional[str] = None,
) -> None:
    """
    Lint a TI (.ti) file.

    Args:
        file_path: Path to the TI file
        show_tokens: Whether to display tokens
        show_ast: Whether to display AST
        config: Optional config file path
        auto_fix: Whether to automatically fix supported auto-fixable issues
        select: Optional rule IDs/patterns to select (e.g., "F110" or "F,N1")

    Raises:
        typer.Exit: With appropriate exit code
    """
    cfg = load_config(file_path, config)
    token_rules, statement_rules = create_rules(cfg, select=select)
    linter = Linter(rules=token_rules, statement_rules=statement_rules)

    if auto_fix:
        # Apply auto-fixes
        num_fixes = auto_fix_ti_file(file_path, linter, lint_context=None)
        if num_fixes > 0:
            typer.echo(f"Fixed {num_fixes} auto-fixable issue(s) in {file_path}")
        else:
            typer.echo(f"No auto-fixable issues to fix in {file_path}")

    # Read the file (potentially after fixes have been applied)
    with open(file_path, "r") as f:
        ti_code = f.read()

    issues = analyze_and_lint_code(
        ti_code,
        linter,
        show_tokens,
        show_ast,
        context_label=None,
        lint_context=LintContext(block="prolog", process_name=file_path.stem),
    )

    raise typer.Exit(code=report_issues(file_path, issues))


def lint_yaml_file(
    file_path: Path,
    show_tokens: bool,
    show_ast: bool,
    config: Optional[Path],
    linter: Optional[Linter] = None,
    return_issues: bool = False,
    silent_errors: bool = False,
    auto_fix: bool = False,
    select: Optional[str] = None,
) -> Optional[list]:
    """
    Lint a YAML ProcessObject file (TM1py format).

    Args:
        file_path: Path to the YAML file
        show_tokens: Whether to display tokens
        show_ast: Whether to display AST
        config: Optional config file path
        linter: Optional pre-created Linter instance (if None, will be created)
        return_issues: If True, return issues instead of reporting and exiting
        silent_errors: If True, return None on error instead of raising Exit
        auto_fix: Whether to automatically fix supported auto-fixable issues
        select: Optional rule IDs/patterns to select (e.g., "F110" or "F,N1")

    Returns:
        List of (proc_name, issue, yaml_line) tuples if return_issues=True, else None

    Raises:
        typer.Exit: With appropriate exit code (unless return_issues=True)
    """
    try:
        process = load_yaml_process(file_path)
    except Exception as e:
        if silent_errors:
            return None
        typer.echo(f"Error loading YAML file: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Process: {process.name}")

    # Use provided linter or create a new one
    if linter is None:
        cfg = load_config(file_path, config)
        token_rules, statement_rules = create_rules(cfg, select=select)
        linter = Linter(rules=token_rules, statement_rules=statement_rules)

    # Apply auto-fixes if requested
    if auto_fix:
        fixes_by_proc = auto_fix_yaml_procedures(file_path, process, linter)
        if fixes_by_proc:
            total_fixes = sum(fixes_by_proc.values())
            typer.echo(f"Fixed {total_fixes} auto-fixable issue(s) in {file_path}:")
            for proc_name, count in fixes_by_proc.items():
                typer.echo(f"  - {proc_name}: {count} fix(es)")
            # Reload process after fixes
            process = load_yaml_process(file_path)
        else:
            typer.echo(f"No auto-fixable issues to fix in {file_path}")

    # Extract and lint each procedure
    procedures = extract_procedures(process)
    all_issues = []

    for proc_name, proc_info in procedures.items():
        lint_ctx = LintContext(
            block=proc_name,
            process_name=process.name,
            parameters=process.parameters,
            parameter_lines=process.parameter_lines,
            variables=process.variables,
            variable_lines=process.variable_lines,
            block_start_line=proc_info.source_line,
            block_end_line=proc_info.source_end_line,
        )
        issues = analyze_and_lint_code(
            proc_info.code,
            linter,
            show_tokens,
            show_ast,
            context_label=proc_name,
            lint_context=lint_ctx,
        )
        for issue in issues:
            # Adjust line number to source file location
            adjusted_issue = (proc_name, issue, proc_info.source_line)
            all_issues.append(adjusted_issue)

    if return_issues:
        return all_issues
    else:
        raise typer.Exit(code=report_yaml_issues(file_path, all_issues))


def lint_directory(
    directory: Path,
    show_tokens: bool,
    show_ast: bool,
    config: Optional[Path],
    auto_fix: bool = False,
    select: Optional[str] = None,
) -> None:
    """
    Lint all YAML process files in a directory and all subdirectories.

    Args:
        directory: Path to the directory
        show_tokens: Whether to display tokens
        show_ast: Whether to display AST
        config: Optional config file path
        auto_fix: Whether to automatically fix supported auto-fixable issues
        select: Optional rule IDs/patterns to select (e.g., "F110" or "F,N1")

    Raises:
        typer.Exit: With appropriate exit code
    """
    yaml_files = sorted({*directory.rglob("*.yaml"), *directory.rglob("*.yml")})

    if not yaml_files:
        typer.echo(f"No YAML files found in {directory}", err=False)
        raise typer.Exit(code=0)

    # Load configuration once for the directory
    cfg = load_config(directory, config)

    # Lint each YAML file and collect all issues
    all_file_issues = []  # List of (file_path, proc_name, issue, yaml_line) tuples

    for yaml_file in yaml_files:
        # Create fresh rule instances per file to avoid cross-file state contamination
        token_rules, statement_rules = create_rules(cfg, select=select)
        linter = Linter(rules=token_rules, statement_rules=statement_rules)

        file_issues = lint_yaml_file(
            yaml_file,
            show_tokens,
            show_ast,
            config,
            linter,
            return_issues=True,
            silent_errors=True,
            auto_fix=auto_fix,
            select=select,
        )
        if file_issues:
            for proc_name, issue, yaml_line in file_issues:
                all_file_issues.append((yaml_file, proc_name, issue, yaml_line))

    raise typer.Exit(code=report_directory_issues(directory, all_file_issues))
