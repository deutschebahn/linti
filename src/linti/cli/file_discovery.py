"""Centralized process-file discovery and path-exclusion matching.

Both the CLI and any programmatic caller turn positional path arguments
(individual files, directories, or glob patterns) into a single, de-duplicated,
exclusion-filtered list of process files here — file discovery is not spread
across the codebase.

Two rules govern all path handling in this module:

1. **Input semantics (resolution anchor depends on the source).**
   A raw path or pattern resolves against an *anchor* directory that depends on
   where it came from: CLI-sourced values against the current working
   directory, config-sourAced values against the config file's directory. The
   source is carried explicitly via :class:`PathGroup`, so the anchor is never
   guessed from the shape of the string.

2. **Internal representation (always absolute and normalized).**
   The moment a path is resolved against its anchor it is canonicalized with
   :meth:`Path.resolve`. Everything downstream — de-duplication, exclusion
   matching, the returned :class:`DiscoveryResult` — operates on that single
   absolute, normalized form. There is no variant enumeration.

Glob expansion happens in this module (via :mod:`glob`), anchored to the group's
directory, so ``linti lint "**/*.ti"`` behaves the same on every platform.
"""

from __future__ import annotations

import glob as globlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pathspec

# Suffixes the provider layer understands. Directory scans and glob expansions
# only surface files with one of these; an explicitly named file is always
# included and left for the provider to accept or reject.
PROCESS_EXTENSIONS = frozenset({".ti", ".yaml", ".yml", ".json"})

# Suffixes discovered when scanning a *directory*. ``.json`` is intentionally
# excluded: a Git-deploy process is a ``.json`` plus a linked ``.ti``, and the
# ``.ti`` already resolves to it — scanning the ``.json`` too would lint the
# same process twice. Explicit paths and globs may still name ``.json`` files.
_DIRECTORY_EXTENSIONS = frozenset({".ti", ".yaml", ".yml"})

_GLOB_CHARS = ("*", "?", "[")


def _looks_like_glob(pattern: str) -> bool:
    """Whether *pattern* should be treated as a glob rather than a plain path."""
    return any(ch in pattern for ch in _GLOB_CHARS)


def _canonical(path: Path) -> Path:
    """Absolute, normalized form of *path* (Rule 2).

    ``resolve()`` also collapses symlinks, so two inputs that reach the same
    file by different routes compare equal. Falls back to ``absolute()`` on the
    rare resolution error (e.g. a symlink loop) so a single pathological entry
    never crashes discovery.
    """
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


@dataclass(frozen=True)
class PathGroup:
    """A set of raw path/pattern strings sharing a single resolution anchor.

    Used for both inputs and exclusions. ``anchor`` is the directory relative
    entries resolve against (Rule 1). Build groups via :meth:`cli` / :meth:`config`.
    """

    patterns: tuple[str, ...]
    anchor: Path

    @classmethod
    def cli(cls, patterns: Iterable[str]) -> PathGroup:
        """Group whose entries resolve against the current working directory."""
        return cls(tuple(str(p) for p in patterns), Path.cwd())

    @classmethod
    def config(cls, patterns: Iterable[str], config_path: Path | str) -> PathGroup:
        """Group whose entries resolve against the config file's directory.

        *config_path* may be the config file or its directory; either way the
        anchor is the directory.
        """
        config_path = Path(config_path)
        anchor = config_path.parent if config_path.is_file() else config_path
        return cls(tuple(str(p) for p in patterns), anchor)


@dataclass(frozen=True)
class _ExclusionGroup:
    """A compiled exclusion spec bound to its canonical anchor directory."""

    spec: pathspec.PathSpec
    anchor: Path

    def matches(self, canonical_file: Path) -> bool:
        """Whether *canonical_file* is caught by this group.

        The file is expressed relative to the anchor before matching, so
        gitignore anchoring semantics apply with the anchor as their root; a
        file outside the anchor tree can never match.
        """
        try:
            rel = canonical_file.relative_to(self.anchor)
        except ValueError:
            return False
        return self.spec.match_file(rel.as_posix())


def _compile_exclusions(groups: Iterable[PathGroup]) -> list[_ExclusionGroup]:
    """Compile non-empty exclusion groups, canonicalizing each anchor.

    ``gitwildmatch`` gives us the semantics we want, evaluated against a file
    made relative to the anchor: ``*``/``?`` never cross ``/``, ``**`` does, a
    *bare* name matches anywhere under the anchor, and a pattern containing
    ``/`` is anchored to the anchor directory. We use ``"gitwildmatch"`` rather
    than ``"gitignore"`` because it is the one factory name that behaves
    identically across pathspec 0.12.x and 1.x.
    """
    return [
        _ExclusionGroup(
            pathspec.PathSpec.from_lines("gitwildmatch", g.patterns),
            _canonical(g.anchor),
        )
        for g in groups
        if g.patterns
    ]


def is_excluded(file: Path | str, groups: Iterable[PathGroup]) -> bool:
    """Whether *file* matches any exclusion group."""
    canonical = _canonical(Path(file))
    return any(eg.matches(canonical) for eg in _compile_exclusions(groups))


@dataclass
class DiscoveryResult:
    """Outcome of :func:`discover_process_files`.

    ``files`` holds canonical (absolute, normalized) paths; use
    :func:`display_path` to render them relative to a root for reports.
    """

    files: list[Path]  # canonical, de-duplicated, exclusion-filtered, sorted
    missing: list[str]  # explicit (non-glob) paths that do not exist
    excluded_count: int  # discovered files dropped by an exclusion


def _process_representative(path: Path) -> Path:
    """The single file that stands in for the process *path* belongs to.

    A Git-deploy process is a ``.json`` metadata file plus a linked ``.ti`` code
    file sharing its stem; the two files denote *one* process, and
    :func:`linti.provider.factory.provider_for_path` maps both to the same
    provider. Collapse the ``.json`` onto that sibling ``.ti`` when it exists so
    an input that matches both files (an explicit pair, or a glob like
    ``git-format.*``) lints the process once — via the ``.ti``, the same
    representative a directory scan already yields (``.json`` is excluded from
    :data:`_DIRECTORY_EXTENSIONS` for exactly this reason). A lone ``.json``
    with no sibling ``.ti`` stands in for itself.
    """
    if path.suffix.lower() == ".json":
        ti_sibling = path.with_suffix(".ti")
        if ti_sibling.exists():
            return ti_sibling
    return path


def _iter_directory(directory: Path) -> Iterable[Path]:
    """Recursively yield process files under *directory*."""
    for ext in sorted(_DIRECTORY_EXTENSIONS):
        yield from directory.rglob(f"*{ext}")


def discover_process_files(
    inputs: Iterable[PathGroup],
    exclusions: Iterable[PathGroup] = (),
) -> DiscoveryResult:
    """Expand *inputs* into the de-duplicated set of process files to lint.

    Every entry is resolved against its group's anchor (Rule 1) and
    canonicalized (Rule 2); directories are scanned, globs expanded, and results
    de-duplicated by canonical path so overlapping inputs lint a file exactly
    once. A Git-deploy ``.json``/``.ti`` pair is collapsed to a single
    representative (see :func:`_process_representative`), so a glob matching both
    files does not lint the process twice. Any file caught by an *exclusions*
    group (matched relative to that group's anchor) is then dropped.
    """
    exclusion_groups = _compile_exclusions(exclusions)

    seen: set[Path] = set()
    collected: list[Path] = []
    missing: list[str] = []

    def _add(candidates: Iterable[Path]) -> None:
        for f in candidates:
            # Collapse a Git-deploy .json/.ti pair to one representative before
            # keying, so a glob matching both files lints the process once.
            key = _canonical(_process_representative(f))
            if key not in seen:
                seen.add(key)
                collected.append(key)  # store the canonical form (Rule 2)

    for group in inputs:
        anchor = _canonical(group.anchor)
        for raw in group.patterns:
            if _looks_like_glob(raw):
                pattern = raw if Path(raw).is_absolute() else str(anchor / raw)
                _add(
                    p
                    for m in globlib.glob(pattern, recursive=True)
                    if (p := Path(m)).is_file()
                    and p.suffix.lower() in PROCESS_EXTENSIONS
                )
                continue

            path = anchor / raw
            if path.is_dir():
                _add(_iter_directory(path))
            elif path.is_file():
                _add([path])
            else:
                missing.append(raw)

    kept = [f for f in collected if not any(eg.matches(f) for eg in exclusion_groups)]
    return DiscoveryResult(
        files=sorted(kept),
        missing=missing,
        excluded_count=len(collected) - len(kept),
    )


def display_path(file: Path | str, root: Path | str | None = None) -> str:
    """Render a canonical *file* relative to *root* for human-readable output.

    Internal paths are absolute (Rule 2), so reports relativize them. *root*
    defaults to the current working directory; files outside it fall back to
    their absolute posix form.
    """
    root_dir = _canonical(Path(root)) if root is not None else _canonical(Path.cwd())
    canonical = _canonical(Path(file))
    try:
        return canonical.relative_to(root_dir).as_posix()
    except ValueError:
        return canonical.as_posix()


def config_base_path(paths: list[str]) -> Path:
    """Path the shared config is discovered from (walking upward).

    The first path that actually exists anchors the search — otherwise the
    current directory is used (e.g. when only glob patterns are given).
    """
    return next((p for raw in paths if (p := Path(raw)).exists()), Path.cwd())


def report_root(paths: list[str]) -> Path:
    """Display root for a combined multi-file report (see :func:`display_path`)."""
    if len(paths) == 1 and (only := Path(paths[0])).is_dir():
        return only
    return Path(".")
