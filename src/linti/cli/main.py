"""Main CLI application for linti."""

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from typer.core import TyperGroup

from linti.cli.config_loader import find_config_file, load_config
from linti.cli.file_discovery import (
    PathGroup,
    config_base_path,
    discover_process_files,
    report_root,
)
from linti.cli.file_linter import lint_files
from linti.cli.rule_explainer import explain_rule, list_rules
from linti.config import LintiConfigWarning
from linti.linter.lint_issue import Severity

if TYPE_CHECKING:
    from click import Context


class _DefaultLintGroup(TyperGroup):
    """Typer group that falls back to the ``lint`` command.

    When the first positional argument is not a known sub-command name
    (e.g. ``linti process.ti`` instead of ``linti lint process.ti``),
    the ``lint`` command is injected automatically so that backward
    compatibility is preserved.
    """

    def parse_args(self, ctx: "Context", args: list[str]) -> list[str]:
        # If there are args and the first one isn't a registered command,
        # treat it as an argument to the default "lint" command.  Top-level
        # help flags are left alone so ``linti --help`` shows the group help
        # instead of being rewritten to ``linti lint --help``.
        if args and args[0] not in ("--help", "-h") and args[0] not in self.commands:
            args = ["lint", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="linti",
    help=(
        "Linter for TM1-like TI process scripts.\n\n"
        "'lint' is the default command: 'linti PATH' is a shortcut for "
        "'linti lint PATH' — both do exactly the same."
    ),
    cls=_DefaultLintGroup,
)

# Module-level argument/option definitions
PATHS_ARG = typer.Argument(
    ...,
    metavar="PATH...",
    help=(
        "One or more files, directories, or glob patterns to lint. Quote globs "
        'so the shell does not expand them (e.g. "processes/**/*.ti").'
    ),
)
SHOW_TOKENS_OPT = typer.Option(
    False,
    "--tokens",
    help="Show tokenization output",
)
SHOW_AST_OPT = typer.Option(
    False,
    "--ast",
    help="Show AST structure",
)
CONFIG_OPT = typer.Option(
    None,
    "--config",
    help="Path to config file (defaults to linti.yaml in file's directory)",
)
AUTO_FIX_OPT = typer.Option(
    False,
    "--auto-fix",
    help="Automatically fix all supported auto-fixable issues",
)
SELECT_OPT = typer.Option(
    None,
    "--select",
    help="Select specific rules to run (e.g., F, F1, F110 or comma-separated list)",
)
FAIL_ON_OPT = typer.Option(
    None,
    "--fail-on",
    help=(
        "Lowest severity that makes the run fail (warning, error). Defaults to "
        "error, so findings linti weighs as warnings (P110, S900 — the parse "
        "diagnostics) are reported but exit 0."
    ),
)
SEVERITY_OPT = typer.Option(
    None,
    "--severity",
    help=(
        "Only report findings of this severity or higher (warning, error). "
        "Anything below is dropped entirely and cannot fail the run."
    ),
)
EXCLUDE_PATH_OPT = typer.Option(
    None,
    "--exclude-path",
    help=(
        "Exclude a file, directory, or glob pattern from linting. Repeatable; "
        "values extend (never replace) any exclude_paths from the config."
    ),
)


@app.command()
def lint(
    paths: list[str] = PATHS_ARG,
    show_tokens: bool = SHOW_TOKENS_OPT,
    show_ast: bool = SHOW_AST_OPT,
    config: Optional[Path] = CONFIG_OPT,
    auto_fix: bool = AUTO_FIX_OPT,
    select: Optional[str] = SELECT_OPT,
    fail_on: Optional[Severity] = FAIL_ON_OPT,
    severity: Optional[Severity] = SEVERITY_OPT,
    exclude_path: Optional[list[str]] = EXCLUDE_PATH_OPT,
) -> None:
    """
    Lint TM1 TI process files, YAML ProcessObjects, directories, or globs (default command).

    This is the default command: 'linti PATH' is a shortcut for 'linti lint PATH'.
    Multiple paths and glob patterns are accepted and expanded together; a file
    reached through several inputs is linted only once.

    Example:
        linti process.ti
        linti processes/
        linti "processes/**/*.ti"
        linti processes/ "*.yaml" other/process.ti
        linti . --exclude-path generated --exclude-path "**/archive/*.ti"
        linti process.ti --auto-fix
        linti process.ti --select F110
        linti processes/ --fail-on warning
        linti processes/ --severity error
    """
    cli_excludes = exclude_path or []

    base_path = config_base_path(paths)
    cfg = load_config(base_path, config)

    # CLI wins over the config file, matching --exclude-path and --select.
    if fail_on is not None:
        cfg.fail_on = fail_on
    if severity is not None:
        cfg.min_severity = severity

    # Inputs and CLI exclusions resolve against the current directory; config
    # exclusions resolve against the config file's directory (Rule 1). Missing a
    # config file, the config group is empty and simply contributes nothing.
    config_file = find_config_file(base_path, config)
    config_anchor = config_file if config_file is not None else base_path
    exclusions = (
        PathGroup.config(cfg.exclude_paths, config_anchor),
        PathGroup.cli(cli_excludes),
    )

    result = discover_process_files([PathGroup.cli(paths)], exclusions)

    # A missing path is reported but does not abort the run: any files that were
    # found are still linted, and the missing path forces a non-zero exit.
    for missing in result.missing:
        typer.echo(f"Error: Path does not exist: {missing}", err=True)

    if not result.files:
        if result.missing:
            raise typer.Exit(code=1)
        typer.echo(_no_files_message(paths, result.excluded_count))
        raise typer.Exit(code=0)

    exit_code = lint_files(
        result.files,
        report_root(paths),
        cfg,
        show_tokens,
        show_ast,
        config,
        auto_fix=auto_fix,
        select=select,
    )
    if result.missing:
        exit_code = max(exit_code, 1)
    raise typer.Exit(code=exit_code)


def _no_files_message(paths: list[str], excluded_count: int) -> str:
    """Message when discovery yields nothing to lint."""
    joined = ", ".join(str(p) for p in paths)
    if excluded_count:
        return (
            f"No process files to lint in {joined} "
            f"(all {excluded_count} matched file(s) were excluded)"
        )
    return f"No process files found in {joined}"


@app.command()
def explain(
    rule_id: Optional[str] = typer.Argument(
        None, help="Rule ID to explain (e.g. F110)"
    ),
    config: Optional[Path] = CONFIG_OPT,
) -> None:
    """
    Explain a linting rule in detail, or list all available rules.

    Severities shown are the effective ones: any `rules.<key>.severity` from the
    config governing the current directory is applied and marked.

    Example:
        linti explain          # list all rules
        linti explain F110     # explain a specific rule
    """
    if rule_id:
        explain_rule(rule_id, config)
    else:
        list_rules(config)


def _install_config_warning_handler() -> None:
    """Render linti config warnings cleanly instead of raw Python warnings.

    Only ``LintiConfigWarning`` is intercepted; every other warning keeps the
    default formatting via the original handler.
    """
    default_showwarning = warnings.showwarning

    def showwarning(message, category, filename, lineno, file=None, line=None):
        if issubclass(category, LintiConfigWarning):
            typer.secho(f"⚠  {message}", fg=typer.colors.YELLOW, err=True)
        else:
            default_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = showwarning
    warnings.simplefilter("always", LintiConfigWarning)


def main() -> None:
    """Entry point for the CLI."""
    _install_config_warning_handler()
    app()


if __name__ == "__main__":
    main()
