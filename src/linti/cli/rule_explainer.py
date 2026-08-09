"""Explain rules via the CLI — lists all rules or shows details for one."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from linti.cli.config_loader import load_config
from linti.config import Config, rule_severity_override
from linti.rules import _RULE_REGISTRY
from linti.linter.lint_issue import Severity
from linti.rules.Rule import RuleMetadata
from linti.rules.rule_ids import (
    deprecated_ids_for,
    group_sort_key,
    resolve_and_warn,
    synthetic_rules,
)


@dataclass(frozen=True)
class _RuleEntry:
    """A rule as ``explain`` sees it: its metadata plus the project's weighting.

    ``severity`` is the *effective* one — what a run in this project would
    actually report — so the command cannot promise "does not fail the run" for
    a rule that `linti.yaml` promoted to an error.
    """

    meta: RuleMetadata
    severity: Severity
    overridden: bool


def _build_rule_index(cfg: Config | None = None) -> dict[str, _RuleEntry]:
    """Build a mapping from rule ID (e.g. ``F110``) to its explain entry."""
    index: dict[str, _RuleEntry] = {}
    for rule_cls in _RULE_REGISTRY:
        meta: RuleMetadata | None = getattr(rule_cls, "METADATA", None)
        if meta is None:
            continue
        override = (
            rule_severity_override(cfg.rules, rule_cls.CONFIG_KEY)
            if cfg is not None
            else None
        )
        entry = _RuleEntry(
            meta=meta,
            severity=override if override is not None else meta.severity,
            overridden=override is not None and override is not meta.severity,
        )
        try:
            instances = rule_cls.from_config({})
        except Exception:
            instances = [rule_cls()]
        for inst in instances:
            index.setdefault(inst.RULE_ID, entry)

    # Pseudo-rules with no class in _RULE_REGISTRY (currently only P900) —
    # see synthetic_rules() — merged in through the same severity-override
    # path every real rule uses.
    for synth in synthetic_rules():
        override = (
            rule_severity_override(cfg.rules, synth.config_key)
            if cfg is not None
            else None
        )
        index[synth.rule_id] = _RuleEntry(
            meta=synth.metadata,
            severity=override if override is not None else synth.metadata.severity,
            overridden=override is not None and override is not synth.metadata.severity,
        )
    return index


def _load_cfg(config_path: Optional[Path]) -> Config:
    """Config governing the current directory, so explain reflects the project."""
    try:
        return load_config(Path.cwd(), config_path)
    except Exception:
        # An unloadable config is the lint command's problem to report; explain
        # stays useful and simply describes the built-in defaults.
        return Config()


def _sorted_ids(index: dict[str, _RuleEntry]) -> list[str]:
    return sorted(index, key=group_sort_key)


def _severity_badge(entry: _RuleEntry) -> str:
    """Header badge for a rule whose weight is worth calling out.

    A plain ``error`` — the default for nearly every rule — says nothing new and
    gets no badge; a warning, or any severity a project changed, does.
    """
    source = " (set by linti.yaml)" if entry.overridden else ""
    if entry.severity is Severity.WARNING:
        return f" [yellow]⚠ Warning — does not fail the run{source}[/yellow]"
    if entry.overridden:
        return f" [red]⛔ Error — fails the run{source}[/red]"
    return ""


# -- public entry points -----------------------------------------------------


def list_rules(config_path: Optional[Path] = None) -> None:
    """Print a compact summary table of all available rules."""
    console = Console()
    index = _build_rule_index(_load_cfg(config_path))

    table = Table(title="linti rules", show_lines=False)
    table.add_column("Rule ID", style="bold cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Auto-fix", justify="center")
    table.add_column("Severity", justify="center")

    current_group = ""
    for rule_id in _sorted_ids(index):
        entry = index[rule_id]
        meta = entry.meta
        group = rule_id[0]
        if group != current_group:
            if current_group:
                table.add_section()
            current_group = group
        fix = "✅" if meta.auto_fix else "❌"
        severity = entry.severity.value + (" *" if entry.overridden else "")
        table.add_row(rule_id, meta.name, meta.description, fix, severity)

    console.print(table)
    if any(entry.overridden for entry in index.values()):
        console.print("\n[dim]* severity overridden by linti.yaml[/dim]")
    console.print(
        "\n[dim]Run [bold]linti explain <RULE_ID>[/bold] for details on a specific rule.[/dim]"
    )


def explain_rule(rule_id: str, config_path: Optional[Path] = None) -> None:
    """Print detailed explanation for a single rule."""
    console = Console()
    index = _build_rule_index(_load_cfg(config_path))

    # Accept a deprecated ID and resolve it to the canonical rule (with a warning).
    canonical = resolve_and_warn(rule_id)
    entry = index.get(canonical)

    if entry is None:
        console.print(f"[red]Unknown rule:[/red] {rule_id}")
        console.print("[dim]Use [bold]linti explain[/bold] to list all rules.[/dim]")
        raise SystemExit(1)

    rule_id = canonical
    meta = entry.meta

    # Header
    title = f"{rule_id}: {meta.name}"
    auto_fix_badge = " [green]✨ Auto-fix available[/green]" if meta.auto_fix else ""
    severity_badge = _severity_badge(entry)
    console.print(
        Panel(f"[bold]{title}[/bold]{auto_fix_badge}{severity_badge}", expand=False)
    )

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
