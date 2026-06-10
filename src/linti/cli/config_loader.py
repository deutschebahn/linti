"""Configuration loading with CLI output."""

from pathlib import Path
from typing import Optional

import typer

from linti.config import Config


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

    if file_path.is_dir():
        # For directories, walk upward from the directory itself
        target_sentinel = file_path / "_dummy"
        cfg = Config.find_and_load(target_sentinel)
        # Check if a config was actually found (walk upward)
        directory = file_path.resolve()
        while True:
            config_file = directory / "linti.yaml"
            if config_file.exists():
                typer.echo(f"Loaded config from: {config_file}")
                break
            parent = directory.parent
            if parent == directory:
                break
            directory = parent
        return cfg

    # For files, walk upward from the file's directory
    cfg = Config.find_and_load(file_path)
    directory = file_path.parent.resolve()
    while True:
        config_file = directory / "linti.yaml"
        if config_file.exists():
            typer.echo(f"Loaded config from: {config_file}")
            break
        parent = directory.parent
        if parent == directory:
            break
        directory = parent
    return cfg
