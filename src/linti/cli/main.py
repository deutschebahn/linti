"""Main CLI application for linti."""

from pathlib import Path
from typing import Optional

import click
import typer
from typer.core import TyperGroup

from linti.cli.file_linter import lint_directory, lint_ti_file, lint_yaml_file
from linti.cli.rule_explainer import explain_rule, list_rules


class _DefaultLintGroup(TyperGroup):
    """Typer group that falls back to the ``lint`` command.

    When the first positional argument is not a known sub-command name
    (e.g. ``linti process.ti`` instead of ``linti lint process.ti``),
    the ``lint`` command is injected automatically so that backward
    compatibility is preserved.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If there are args and the first one isn't a registered command,
        # treat it as an argument to the default "lint" command.
        if args and args[0] not in self.commands:
            args = ["lint", *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="linti",
    help="Linter for TM1-like TI process scripts",
    cls=_DefaultLintGroup,
)

# Module-level argument/option definitions
FILE_PATH_ARG = typer.Argument(
    ...,
    help="Path to a TI file, YAML file, or directory to lint",
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


@app.command()
def lint(
    file_path: Path = FILE_PATH_ARG,
    show_tokens: bool = SHOW_TOKENS_OPT,
    show_ast: bool = SHOW_AST_OPT,
    config: Optional[Path] = CONFIG_OPT,
    auto_fix: bool = AUTO_FIX_OPT,
    select: Optional[str] = SELECT_OPT,
) -> None:
    """
    Lint a TM1 TI process file, YAML ProcessObject, or directory of YAMLs.

    Example:
        linti process.ti
        linti process.yaml
        linti /path/to/processes/
        linti process.ti --tokens --ast
        linti process.ti --config custom-config.yaml
        linti process.ti --auto-fix
        linti process.ti --select F110
        linti process.ti --select F,N1
    """
    if not file_path.exists():
        typer.echo(f"Error: Path does not exist: {file_path}", err=True)
        raise typer.Exit(code=1)

    if file_path.is_dir():
        lint_directory(file_path, show_tokens, show_ast, config, auto_fix, select)
    elif file_path.suffix.lower() == ".yaml":
        lint_yaml_file(
            file_path, show_tokens, show_ast, config, auto_fix=auto_fix, select=select
        )
    else:
        lint_ti_file(file_path, show_tokens, show_ast, config, auto_fix, select)


@app.command()
def explain(
    rule_id: Optional[str] = typer.Argument(
        None, help="Rule ID to explain (e.g. F110)"
    ),
) -> None:
    """
    Explain a linting rule in detail, or list all available rules.

    Example:
        linti explain          # list all rules
        linti explain F110     # explain a specific rule
    """
    if rule_id:
        explain_rule(rule_id)
    else:
        list_rules()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
