"""Tests for centralized process-file discovery and path exclusion."""

from pathlib import Path

import pytest

from linti.cli.file_discovery import (
    PathGroup,
    discover_process_files,
    display_path,
    is_excluded,
)


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A small project tree, with cwd set to its root for relative patterns."""
    (tmp_path / "processes").mkdir()
    (tmp_path / "processes" / "a.ti").write_text("nA = 1;\n")
    (tmp_path / "processes" / "b.yaml").write_text("Name: b\n")
    (tmp_path / "processes" / "sub").mkdir()
    (tmp_path / "processes" / "sub" / "c.ti").write_text("nC = 1;\n")
    (tmp_path / "processes" / "archive").mkdir()
    (tmp_path / "processes" / "archive" / "old.ti").write_text("nOld = 1;\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "g.ti").write_text("nG = 1;\n")
    (tmp_path / "notes.txt").write_text("not a process\n")
    # cwd (and thus PathGroup.cli's anchor) is the tree root.
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _inputs(*patterns: str) -> list[PathGroup]:
    """CLI-sourced input groups (resolved against the current directory)."""
    return [PathGroup.cli(patterns)]


def _exclude(*patterns: str) -> tuple[PathGroup, ...]:
    """CLI-sourced exclusion groups (resolved against the current directory)."""
    return (PathGroup.cli(patterns),)


def _names(result) -> set[str]:
    return {p.name for p in result.files}


# --- expansion ------------------------------------------------------------


def test_directory_is_expanded_recursively(tree: Path):
    result = discover_process_files(_inputs("processes"))
    assert _names(result) == {"a.ti", "b.yaml", "c.ti", "old.ti"}


def test_directory_scan_skips_non_process_files(tree: Path):
    result = discover_process_files(_inputs("."))
    assert "notes.txt" not in _names(result)


def test_individual_file_is_included(tree: Path):
    result = discover_process_files(_inputs("processes/a.ti"))
    assert _names(result) == {"a.ti"}


def test_glob_is_expanded(tree: Path):
    result = discover_process_files(_inputs("processes/*.ti"))
    assert _names(result) == {"a.ti"}  # non-recursive: no sub/ or archive/


def test_recursive_glob_is_expanded(tree: Path):
    result = discover_process_files(_inputs("processes/**/*.ti"))
    assert _names(result) == {"a.ti", "c.ti", "old.ti"}


def test_missing_non_glob_path_is_reported(tree: Path):
    result = discover_process_files(_inputs("processes/does_not_exist.ti"))
    assert result.files == []
    assert result.missing == ["processes/does_not_exist.ti"]


def test_glob_matching_nothing_is_not_missing(tree: Path):
    result = discover_process_files(_inputs("processes/*.zzz"))
    assert result.files == []
    assert result.missing == []


def test_discovered_files_are_absolute(tree: Path):
    result = discover_process_files(_inputs("processes/a.ti"))
    assert result.files == [tree / "processes" / "a.ti"]
    assert all(p.is_absolute() for p in result.files)


# --- resolution anchor ----------------------------------------------------


def test_cli_group_resolves_against_cwd(tree: Path, monkeypatch: pytest.MonkeyPatch):
    # cwd elsewhere, but a CLI group still anchors on the (new) cwd.
    monkeypatch.chdir(tree / "processes")
    result = discover_process_files([PathGroup.cli(["a.ti"])])
    assert result.files == [tree / "processes" / "a.ti"]


def test_config_group_resolves_against_config_dir(tree: Path):
    # A config-sourced pattern resolves against the config file's directory,
    # independent of cwd.
    group = PathGroup.config(["a.ti"], tree / "processes")
    result = discover_process_files([group])
    assert result.files == [tree / "processes" / "a.ti"]


# --- de-duplication -------------------------------------------------------


def test_overlapping_inputs_lint_a_file_once(tree: Path):
    result = discover_process_files(
        _inputs("processes/a.ti", "processes/*.ti", "processes")
    )
    assert sum(p.name == "a.ti" for p in result.files) == 1


# --- Git-deploy .json/.ti pair collapse -----------------------------------


@pytest.fixture
def git_deploy(tree: Path) -> Path:
    """Add a Git-deploy process (a .json metadata file + a linked .ti)."""
    (tree / "processes" / "deploy.ti").write_text("nD = 1;\n")
    (tree / "processes" / "deploy.json").write_text('{"Name": "deploy"}\n')
    return tree


def test_glob_matching_both_pair_files_lints_once(git_deploy: Path):
    # 'deploy.*' matches both deploy.json and deploy.ti — the same process.
    result = discover_process_files(_inputs("processes/deploy.*"))
    deploy = [p for p in result.files if p.stem == "deploy"]
    assert deploy == [git_deploy / "processes" / "deploy.ti"]


def test_glob_matching_only_json_resolves_to_ti(git_deploy: Path):
    # Even when only the .json is matched, it collapses onto its sibling .ti.
    result = discover_process_files(_inputs("processes/*.json"))
    assert result.files == [git_deploy / "processes" / "deploy.ti"]


def test_explicit_pair_lints_once(git_deploy: Path):
    result = discover_process_files(
        _inputs("processes/deploy.json", "processes/deploy.ti")
    )
    assert [p for p in result.files if p.stem == "deploy"] == [
        git_deploy / "processes" / "deploy.ti"
    ]


def test_lone_json_without_ti_stands_in_for_itself(tree: Path):
    (tree / "processes" / "solo.json").write_text('{"Name": "solo"}\n')
    result = discover_process_files(_inputs("processes/solo.json"))
    assert result.files == [tree / "processes" / "solo.json"]


# --- exclusions -----------------------------------------------------------


def test_exclude_directory(tree: Path):
    result = discover_process_files(_inputs("."), _exclude("generated"))
    assert "g.ti" not in _names(result)
    assert result.excluded_count == 1


def test_exclude_nested_directory_by_bare_name(tree: Path):
    result = discover_process_files(_inputs("processes"), _exclude("archive"))
    assert "old.ti" not in _names(result)


def test_exclude_specific_file(tree: Path):
    result = discover_process_files(_inputs("processes"), _exclude("processes/a.ti"))
    assert "a.ti" not in _names(result)
    assert "b.yaml" in _names(result)


def test_exclude_glob_pattern(tree: Path):
    result = discover_process_files(_inputs("processes"), _exclude("**/archive/*.ti"))
    assert "old.ti" not in _names(result)
    assert "c.ti" in _names(result)


def test_exclude_by_extension_glob(tree: Path):
    result = discover_process_files(_inputs("processes"), _exclude("**/*.ti"))
    assert _names(result) == {"b.yaml"}


def test_bare_name_does_not_over_match_similar_filename(tree: Path):
    # 'generated' must not exclude a file merely containing that word.
    (tree / "processes" / "generated_report.ti").write_text("nX = 1;\n")
    result = discover_process_files(_inputs("processes"), _exclude("generated"))
    assert "generated_report.ti" in _names(result)


def test_anchored_file_pattern_does_not_match_nested_copy(tree: Path):
    # A slash-containing pattern is rooted: it must not also drop a same-named
    # file nested deeper in the tree.
    nested = tree / "processes" / "sub" / "processes"
    nested.mkdir()
    (nested / "a.ti").write_text("nX = 1;\n")
    result = discover_process_files(_inputs("processes"), _exclude("processes/a.ti"))
    kept = {display_path(p) for p in result.files}
    assert "processes/a.ti" not in kept  # the rooted file is excluded
    assert "processes/sub/processes/a.ti" in kept  # the nested one is kept


def test_anchored_directory_pattern_is_rooted(tree: Path):
    # 'processes/archive' anchored: excludes only the top-level archive dir.
    deep = tree / "processes" / "sub" / "processes" / "archive"
    deep.mkdir(parents=True)
    (deep / "d.ti").write_text("nX = 1;\n")
    result = discover_process_files(_inputs("processes"), _exclude("processes/archive"))
    kept = {display_path(p) for p in result.files}
    assert "processes/archive/old.ti" not in kept
    assert "processes/sub/processes/archive/d.ti" in kept


def test_config_exclusion_anchored_to_config_dir(tree: Path):
    # A config-sourced exclusion is anchored to the config file's directory:
    # 'a.ti' (bare) drops processes/a.ti when the config lives in processes/.
    config_group = PathGroup.config(["a.ti"], tree / "processes")
    result = discover_process_files(_inputs("processes"), (config_group,))
    assert "a.ti" not in _names(result)
    assert "b.yaml" in _names(result)


# --- is_excluded (direct) -------------------------------------------------


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("generated/g.ti", "generated", True),
        ("src/generated/g.ti", "generated", True),
        ("processes/test.ti", "processes/test.ti", True),
        # Anchored (slash) patterns do not match a same-named nested path.
        ("deep/processes/test.ti", "processes/test.ti", False),
        ("x/sub/generated/g.ti", "sub/generated", False),
        # An explicit **/ opts a slash pattern back into matching at any depth.
        ("a/b/archive/old.ti", "**/archive/*.ti", True),
        ("processes/a.ti", "generated", False),
        ("vendor.ti", "vendor", False),
    ],
)
def test_is_excluded_matching(
    path: str,
    pattern: str,
    expected: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # is_excluded works on absolute paths matched relative to the group anchor;
    # anchor the group on cwd and express the file relative to it.
    monkeypatch.chdir(tmp_path)
    assert is_excluded(tmp_path / path, [PathGroup.cli([pattern])]) is expected


def test_is_excluded_outside_anchor_never_matches(tmp_path: Path):
    # A file outside the anchor tree can never match, whatever the pattern.
    group = PathGroup.config(["**/*.ti"], tmp_path / "project")
    assert is_excluded(tmp_path / "elsewhere" / "x.ti", [group]) is False


# --- display_path ---------------------------------------------------------


def test_display_path_relativizes_to_root(tree: Path):
    abs_file = tree / "processes" / "a.ti"
    assert display_path(abs_file, tree) == "processes/a.ti"


def test_display_path_defaults_to_cwd(tree: Path):
    abs_file = tree / "processes" / "a.ti"
    assert display_path(abs_file) == "processes/a.ti"


def test_display_path_outside_root_is_absolute(tree: Path):
    outside = tree.parent / "somewhere_else.ti"
    assert display_path(outside, tree) == outside.resolve().as_posix()
