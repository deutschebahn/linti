"""Explain rules via the CLI — lists all rules or shows details for one."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from linti.rules import _RULE_REGISTRY
from linti.rules.Rule import RuleMetadata
from linti.rules.rule_ids import deprecated_ids_for, group_sort_key, resolve_and_warn


def _build_rule_index() -> dict[str, RuleMetadata]:
    """Build a mapping from rule ID (e.g. ``F110``) to its metadata."""
    index: dict[str, RuleMetadata] = {}
    for rule_cls in _RULE_REGISTRY:
        meta: RuleMetadata | None = getattr(rule_cls, "METADATA", None)
        if meta is None:
            continue
        try:
            instances = rule_cls.from_config({})
        except Exception:
            instances = [rule_cls()]
        for inst in instances:
            index.setdefault(inst.RULE_ID, meta)
    return index


def _sorted_ids(index: dict[str, RuleMetadata]) -> list[str]:
    return sorted(index, key=group_sort_key)


# -- public entry points -----------------------------------------------------


def list_rules() -> None:
    """Print a compact summary table of all available rules."""
    console = Console()
    index = _build_rule_index()

    table = Table(title="linti rules", show_lines=False)
    table.add_column("Rule ID", style="bold cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Auto-fix", justify="center")

    current_group = ""
    for rule_id in _sorted_ids(index):
        meta = index[rule_id]
        group = rule_id[0]
        if group != current_group:
            if current_group:
                table.add_section()
            current_group = group
        fix = "✅" if meta.auto_fix else "❌"
        table.add_row(rule_id, meta.name, meta.description, fix)

    console.print(table)
    console.print(
        "\n[dim]Run [bold]linti explain <RULE_ID>[/bold] for details on a specific rule.[/dim]"
    )


def explain_rule(rule_id: str) -> None:
    """Print detailed explanation for a single rule."""
    console = Console()
    index = _build_rule_index()

    # Accept a deprecated ID and resolve it to the canonical rule (with a warning).
    canonical = resolve_and_warn(rule_id)
    meta = index.get(canonical)

    if meta is None:
        console.print(f"[red]Unknown rule:[/red] {rule_id}")
        console.print("[dim]Use [bold]linti explain[/bold] to list all rules.[/dim]")
        raise SystemExit(1)

    rule_id = canonical

    # Header
    title = f"{rule_id}: {meta.name}"
    auto_fix_badge = " [green]✨ Auto-fix available[/green]" if meta.auto_fix else ""
    console.print(Panel(f"[bold]{title}[/bold]{auto_fix_badge}", expand=False))

    # Previous (deprecated) rule IDs, if any.
    previous = deprecated_ids_for(rule_id)
    if previous:
        joined = ", ".join(previous)
        console.print(f"\n[dim]Previous rule ID: {joined} (deprecated)[/dim]")

    # Description
    console.print(f"\n{meta.description}.\n")

    # Explanation
    if meta.explanation:
        console.print(Text(meta.explanation))
        console.print()

    # Configuration
    if meta.config_example:
        console.print("[bold]Configuration:[/bold]")
        console.print(Syntax(meta.config_example, "yaml", theme="monokai", padding=1))
        console.print()

    # Examples
    valid = [e for e in meta.examples if e.valid]
    invalid = [e for e in meta.examples if not e.valid]

    if valid:
        console.print("[bold green]✓ Valid usage:[/bold green]")
        for ex in valid:
            if ex.description:
                console.print(f"  [dim]# {ex.description}[/dim]")
            console.print(Syntax(ex.code, "sql", theme="monokai", padding=(0, 2)))
        console.print()

    if invalid:
        console.print("[bold red]✗ Invalid usage:[/bold red]")
        for ex in invalid:
            if ex.description:
                console.print(f"  [dim]# {ex.description}[/dim]")
            console.print(Syntax(ex.code, "sql", theme="monokai", padding=(0, 2)))
        console.print()
