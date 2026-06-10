"""Loaders for different TM1 file formats."""

from pathlib import Path

from linti.loader.base import (  # noqa: F401 – public API
    BaseLoader,
    ProcedureInfo,
    TM1Process,
    extract_procedures,
)
from linti.loader.ti_loader import TiLoader
from linti.loader.yaml_loader import YamlLoader

# Loader registry — order matters: first match wins.
_LOADERS: list[BaseLoader] = [
    YamlLoader(),
    TiLoader(),
]


def load_process(file_path: Path) -> TM1Process:
    """Load a TM1 process from *file_path* using the appropriate loader.

    Iterates through registered loaders and delegates to the first one
    whose :meth:`~BaseLoader.can_load` returns ``True``.

    Raises:
        ValueError: If no loader supports *file_path*.
    """
    for loader in _LOADERS:
        if loader.can_load(file_path):
            return loader.load(file_path)
    raise ValueError(
        f"No loader registered for file type: {file_path.suffix!r} ({file_path})"
    )
