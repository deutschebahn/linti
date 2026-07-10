"""Configuration loading with CLI output."""

from pathlib import Path
from typing import Optional

import typer

from linti.config import Config


def find_config_file(
    file_path: Path, config_override: Optional[Path] = None
) -> Optional[Path]:
    """Locate the ``linti.yaml`` that governs *file_path*, if any.

    An explicit *config_override* is returned as-is; otherwise the upward search
    and project-root boundary of :meth:`Config.find_config_file` apply. Returns
    ``None`` when discovery falls back to the built-in defaults.

    Used as the resolution anchor for config-sourced exclusion patterns (see
    :class:`linti.cli.file_discovery.PathGroup`).
    """
    if config_override:
        return config_override
    target = file_path / "_dummy" if file_path.is_dir() else file_path
    return Config.find_config_file(target)


def load_config(file_path: Path, config_override: Optional[Path] = None) -> Config:
    """
    Load configuration from file or discover default.

    Args:
        file_path: Path to a TI file, YAML file, or directory being linted
        config_override: Optional explicit config file path

    Returns:
        Loaded Config object
    """
    if config_override:
        cfg = Config.load_from_file(config_override)
        typer.echo(f"Loaded config from: {config_override}")
        return cfg

    target = file_path / "_dummy" if file_path.is_dir() else file_path
    cfg = Config.find_and_load(target)
    config_file = Config.find_config_file(target)
    if config_file is not None:
        typer.echo(f"Loaded config from: {config_file}")
    return cfg
