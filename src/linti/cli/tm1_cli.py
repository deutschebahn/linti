"""The ``linti tm1`` command group: lint processes straight off a TM1 server.

Its own group rather than a flag on ``lint`` because the two take genuinely
different inputs: ``lint`` discovers files, expands globs and applies
``exclude_paths``, none of which mean anything for a server. What they do share
— config loading, rule selection, the linter, the reporter — is reused rather
than duplicated.
"""

from pathlib import Path
from typing import Optional

import typer

from linti.cli.config_loader import load_config
from linti.cli.tm1_linter import lint_tm1_processes, select_processes
from linti.linter.lint_issue import Severity
from linti.provider.base import ProviderError
from linti.provider.tm1 import TM1Provider
from linti.rules.rule_factory import RuleSelection
from linti.tm1 import credentials
from linti.tm1.connections import ConnectionsError, ConnectionsFile
from linti.tm1.credentials import CredentialsError
from linti.tm1.service import TM1ConnectionError, connect, server_version

tm1_app = typer.Typer(
    name="tm1",
    help=(
        "Lint TI processes on a TM1 server.\n\n"
        "Connection profiles live in a per-user connections.yaml and never "
        "contain passwords; those are stored in the system keyring via "
        "'linti tm1 login'."
    ),
    no_args_is_help=True,
)

PROFILE_OPT = typer.Option(
    None,
    "--profile",
    "-p",
    help="Connection profile to use (defaults to 'default_profile').",
)
CONNECTIONS_OPT = typer.Option(
    None,
    "--connections",
    help=(
        "Path to the connection profile file (defaults to connections.yaml in "
        "linti's config directory; also settable via LINTI_CONNECTIONS)."
    ),
)
PATTERNS_ARG = typer.Argument(
    None,
    metavar="[PATTERN]...",
    help=(
        "Glob patterns matched against process names, case-insensitively (e.g. "
        '"Sales.*"). Quote them so the shell does not expand them. Omit to lint '
        "every process."
    ),
)
INCLUDE_CONTROL_OPT = typer.Option(
    False,
    "--include-control",
    help="Also lint TM1's own '}'/'{'-prefixed control processes.",
)
AUTO_FIX_OPT = typer.Option(
    False,
    "--auto-fix",
    help="Not supported for TM1 connections; linti never writes to a server.",
)


def _load_profile(profile: Optional[str], connections: Optional[Path]):
    """Resolve ``(name, profile)`` or exit with the loader's own message."""
    try:
        return ConnectionsFile.load(connections).resolve(profile)
    except ConnectionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _require_user(name: str, profile) -> str:
    if not profile.user:
        typer.echo(
            f"Error: profile {name!r} has no 'user'. Add one to your "
            f"connections.yaml — linti needs it to look up the password.",
            err=True,
        )
        raise typer.Exit(code=2)
    return profile.user


@tm1_app.command("lint")
def tm1_lint(
    patterns: Optional[list[str]] = PATTERNS_ARG,
    profile: Optional[str] = PROFILE_OPT,
    connections: Optional[Path] = CONNECTIONS_OPT,
    config: Optional[Path] = typer.Option(
        None, "--config", help="Path to linti.yaml (defaults to discovery from CWD)."
    ),
    select: Optional[list[str]] = typer.Option(
        None, "--select", help="Run only these rules (e.g. F, F1, F110)."
    ),
    extend_select: Optional[list[str]] = typer.Option(
        None, "--extend-select", help="Run these rules in addition to the current set."
    ),
    exclude_rule: Optional[list[str]] = typer.Option(
        None, "--exclude-rule", "--ignore", help="Skip these rules for this run."
    ),
    fail_on: Optional[Severity] = typer.Option(
        None, "--fail-on", help="Lowest severity that makes the run fail."
    ),
    severity: Optional[Severity] = typer.Option(
        None, "--severity", help="Only report findings of this severity or higher."
    ),
    include_control: bool = INCLUDE_CONTROL_OPT,
    auto_fix: bool = AUTO_FIX_OPT,
) -> None:
    """
    Lint TI processes on a TM1 server.

    Example:
        linti tm1 lint --profile prod
        linti tm1 lint -p prod "Sales.*" "Load_*"
        linti tm1 lint -p prod --select F110 --fail-on warning
    """
    if auto_fix:
        # A named option with a real explanation, rather than click's "No such
        # option": anyone arriving from `linti lint --auto-fix` expects parity
        # and deserves to know why there is none yet.
        typer.echo(
            "Error: --auto-fix is not supported for TM1 connections. linti does "
            "not write processes back to a server yet, so nothing on the server "
            "would change. Run without it to see the findings.",
            err=True,
        )
        raise typer.Exit(code=2)

    profile_name, conn = _load_profile(profile, connections)
    user = _require_user(profile_name, conn)

    # Config discovery is path-based, so a server run anchors it at the current
    # directory: a repo checkout's linti.yaml governs how its processes are
    # linted, wherever they are read from.
    cfg = load_config(Path.cwd(), config)
    if fail_on is not None:
        cfg.fail_on = fail_on
    if severity is not None:
        cfg.min_severity = severity

    # Parsed once per run, like in `lint`: this is where deprecated IDs and
    # patterns matching nothing are reported, and they should be said once.
    selection = RuleSelection.parse(select, extend_select, exclude_rule)

    try:
        password = credentials.resolve_password(profile_name, user)
    except CredentialsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        with connect(conn, password, label=profile_name) as tm1:
            provider = TM1Provider(
                tm1,
                skip_control_processes=not include_control,
                max_process_size=cfg.max_file_size,
                label=profile_name,
            )
            names = select_processes(provider.list_processes(), patterns or [])
            # Reporting happens inside the `with`, because a per-process fetch
            # failure is reported rather than raised — the session has to still
            # be open for the processes that follow it.
            exit_code = (
                lint_tm1_processes(provider, names, profile_name, cfg, selection)
                if names
                else None
            )
    except (TM1ConnectionError, ProviderError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if exit_code is None:
        typer.echo(_nothing_matched(profile_name, patterns or []))
        raise typer.Exit(code=0)
    raise typer.Exit(code=exit_code)


def _nothing_matched(profile: str, patterns: list[str]) -> str:
    if patterns:
        return (
            f"No processes on {profile} match {', '.join(patterns)} "
            f"(patterns are matched case-insensitively against process names)"
        )
    return f"No processes to lint on {profile}"


@tm1_app.command("login")
def tm1_login(
    profile: Optional[str] = typer.Argument(
        None, help="Profile to store a password for."
    ),
    connections: Optional[Path] = CONNECTIONS_OPT,
) -> None:
    """
    Store a password for a connection profile in the system keyring.

    The password is verified against the server before it is stored: a saved
    credential that does not work is worse than none at all.
    """
    profile_name, conn = _load_profile(profile, connections)
    user = _require_user(profile_name, conn)

    try:
        password = credentials.prompt_password(profile_name, user)
    except CredentialsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        with connect(conn, password, label=profile_name) as tm1:
            version = server_version(tm1)
    except TM1ConnectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        typer.echo("Nothing was stored.", err=True)
        raise typer.Exit(code=1) from exc

    try:
        credentials.store_password(profile_name, user, password)
    except CredentialsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    suffix = f" (TM1 {version})" if version else ""
    typer.echo(f"✓ Stored the password for {user}@{profile_name}{suffix}")


@tm1_app.command("logout")
def tm1_logout(
    profile: Optional[str] = typer.Argument(None, help="Profile to forget."),
    connections: Optional[Path] = CONNECTIONS_OPT,
) -> None:
    """Remove a stored password from the system keyring."""
    profile_name, conn = _load_profile(profile, connections)
    user = _require_user(profile_name, conn)

    try:
        removed = credentials.delete_password(profile_name, user)
    except CredentialsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if removed:
        typer.echo(f"✓ Removed the password for {user}@{profile_name}")
    else:
        typer.echo(f"No password was stored for {user}@{profile_name}")


@tm1_app.command("profiles")
def tm1_profiles(connections: Optional[Path] = CONNECTIONS_OPT) -> None:
    """List the configured connection profiles."""
    try:
        parsed = ConnectionsFile.load(connections)
    except ConnectionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Profiles in {parsed.path}:")
    for name in sorted(parsed.profiles):
        conn = parsed.profiles[name]
        target = conn.base_url or f"{conn.address}:{conn.port or ''}".rstrip(":")
        marks = []
        if name == parsed.default_profile:
            marks.append("default")
        if conn.user and credentials.has_stored_password(name, conn.user):
            # Whether a password is stored, never what it is.
            marks.append("password stored")
        suffix = f"  [{', '.join(marks)}]" if marks else ""
        typer.echo(f"  {name}: {conn.user or '<no user>'}@{target}{suffix}")
