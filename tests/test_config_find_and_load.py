"""Tests for Config.find_and_load() directory-tree traversal (7.4)."""

from pathlib import Path

import pytest

from linti.config import Config


@pytest.fixture()
def nested_dirs(tmp_path: Path):
    """Create a nested directory structure for testing config discovery.

    Layout::

        tmp_path/
            grandparent/
                linti.yaml          <- config with keyword_casing disabled
                parent/
                    child/
                        process.ti
    """
    grandparent = tmp_path / "grandparent"
    parent = grandparent / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    config = grandparent / "linti.yaml"
    config.write_text("rules:\n  keyword_casing:\n    enabled: false\n")

    process_file = child / "process.ti"
    process_file.write_text("nValue = 1;")

    return {
        "grandparent": grandparent,
        "parent": parent,
        "child": child,
        "process_file": process_file,
        "config": config,
    }


def test_finds_config_in_same_directory(tmp_path: Path):
    """Config in the same directory as the target file is found."""
    config_file = tmp_path / "linti.yaml"
    config_file.write_text("rules:\n  keyword_casing:\n    enabled: false\n")
    target = tmp_path / "process.ti"
    target.write_text("")

    cfg = Config.find_and_load(target)
    assert cfg.rules.keyword_casing.enabled is False


def test_finds_config_in_ancestor_directory(nested_dirs):
    """Config two levels up is discovered when nothing closer exists."""
    cfg = Config.find_and_load(nested_dirs["process_file"])
    assert cfg.rules.keyword_casing.enabled is False


def test_closest_config_wins(nested_dirs):
    """A config in the immediate parent overrides one further up."""
    closer_config = nested_dirs["child"] / "linti.yaml"
    closer_config.write_text(
        "rules:\n  keyword_casing:\n    enabled: true\n    style: lowercase\n"
    )

    cfg = Config.find_and_load(nested_dirs["process_file"])
    # The closer config should win over the grandparent one.
    assert cfg.rules.keyword_casing.enabled is True
    assert cfg.rules.keyword_casing.style == "lowercase"


def test_returns_default_when_no_config_found(tmp_path: Path):
    """When no linti.yaml exists anywhere, the default Config is returned."""
    target = tmp_path / "process.ti"
    target.write_text("")

    cfg = Config.find_and_load(target)
    # Default: keyword_casing enabled, style uppercase
    assert cfg.rules.keyword_casing.enabled is True
    assert cfg.rules.keyword_casing.style == "uppercase"


def test_invalid_config_raises_value_error(tmp_path: Path):
    """A malformed config file raises ValueError, not silently ignored."""
    config_file = tmp_path / "linti.yaml"
    config_file.write_text("rules:\n  keyword_casing:\n    style: INVALID_STYLE\n")
    target = tmp_path / "process.ti"
    target.write_text("")

    with pytest.raises(ValueError, match="Failed to load config"):
        Config.find_and_load(target)


def test_removed_rule_config_emits_warning(tmp_path: Path):
    """Configuring a removed rule warns and is otherwise ignored."""
    config_file = tmp_path / "linti.yaml"
    config_file.write_text(
        "rules:\n"
        "  one_space_before_equals:\n"
        "    enabled: true\n"
        "  keyword_casing:\n"
        "    enabled: false\n"
    )

    with pytest.warns(UserWarning, match="removed Equals Spacing rule"):
        cfg = Config.load_from_file(config_file)

    assert cfg.rules.keyword_casing.enabled is False


def test_per_rule_generic_prefixes_emits_deprecation_warning(tmp_path: Path):
    """Per-rule generic_prefixes warns and points to the top-level setting."""
    config_file = tmp_path / "linti.yaml"
    config_file.write_text(
        "rules:\n  docstring_region:\n    generic_prefixes:\n      - '}core.'\n"
    )

    with pytest.warns(UserWarning, match="generic_prefixes.*deprecated"):
        cfg = Config.load_from_file(config_file)

    # The value is still loaded (honoured for now).
    assert cfg.rules.docstring_region.generic_prefixes == ["}core."]


def test_conflicting_generic_prefixes_raises(tmp_path: Path):
    """Both top-level and deprecated per-rule generic_prefixes is a hard error."""
    config_file = tmp_path / "linti.yaml"
    config_file.write_text(
        "generic_prefixes:\n"
        "  - '}core.'\n"
        "rules:\n"
        "  docstring_region:\n"
        "    generic_prefixes:\n"
        "      - '}custom.'\n"
    )

    with pytest.raises(ValueError, match="generic_prefixes"):
        Config.load_from_file(config_file)


def test_top_level_generic_prefixes_does_not_warn(tmp_path: Path):
    """The new top-level location loads cleanly without a deprecation warning."""
    import warnings

    config_file = tmp_path / "linti.yaml"
    config_file.write_text("generic_prefixes:\n  - '}core.'\n")

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would fail the test
        cfg = Config.load_from_file(config_file)

    assert cfg.generic_prefixes == ["}core."]


def test_stops_at_git_root(tmp_path: Path):
    """Search does not pass a .git project root marker."""
    # Layout:
    #   tmp_path/
    #       linti.yaml        <- should NOT be found (outside project)
    #       project/
    #           .git/            <- project root marker
    #           sub/
    #               process.ti
    (tmp_path / "linti.yaml").write_text(
        "rules:\n  keyword_casing:\n    enabled: false\n"
    )
    project = tmp_path / "project"
    git_dir = project / ".git"
    git_dir.mkdir(parents=True)
    sub = project / "sub"
    sub.mkdir()
    target = sub / "process.ti"
    target.write_text("")

    cfg = Config.find_and_load(target)
    # Should fall back to defaults because .git stopped the search
    assert cfg.rules.keyword_casing.enabled is True


def test_stops_at_pyproject_toml(tmp_path: Path):
    """Search does not pass a pyproject.toml project root marker."""
    (tmp_path / "linti.yaml").write_text(
        "rules:\n  keyword_casing:\n    enabled: false\n"
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[tool.pytest]\n")
    sub = project / "sub"
    sub.mkdir()
    target = sub / "process.ti"
    target.write_text("")

    cfg = Config.find_and_load(target)
    assert cfg.rules.keyword_casing.enabled is True


def test_config_at_project_root_is_still_found(tmp_path: Path):
    """A config co-located with a project root marker IS loaded."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "linti.yaml").write_text(
        "rules:\n  keyword_casing:\n    enabled: false\n"
    )
    sub = project / "sub"
    sub.mkdir()
    target = sub / "process.ti"
    target.write_text("")

    cfg = Config.find_and_load(target)
    # Config in the same dir as .git should be found before the marker stops us
    assert cfg.rules.keyword_casing.enabled is False
