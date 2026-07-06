"""Provider protocol for loading and persisting process IR objects."""

from pathlib import Path
from typing import Any, Optional, Protocol

from linti.model.process_ir import ProcessIR

# Default file-size ceiling (bytes). Files above this are rejected before being
# read into memory, guarding against resource exhaustion on untrusted input.
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def ensure_within_size_limit(path: Path, max_bytes: int) -> None:
    """Raise if *path* exceeds *max_bytes*, checking size without reading it."""
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(
            f"File exceeds size limit ({size} > {max_bytes} bytes): {path}"
        )


class ProcessProvider(Protocol):
    def list_processes(self) -> list[str]: ...

    def get_process(self, name: str) -> ProcessIR: ...

    def save_process(self, process: ProcessIR) -> None: ...


def require_single_process_name(provider: ProcessProvider) -> str:
    """Return the only process name from *provider* or raise a clear error."""
    process_names = provider.list_processes()
    if not process_names:
        raise ValueError("Provider returned no process names")
    if len(process_names) > 1:
        raise ValueError(
            "Expected exactly one process name, got "
            f"{len(process_names)}: {process_names!r}"
        )
    return process_names[0]


def load_single_process(provider: ProcessProvider) -> ProcessIR:
    """Load the only process from a single-process provider."""
    name = require_single_process_name(provider)
    return provider.get_process(name)


def validate_process_name(actual: str, expected: str, context: str) -> None:
    """Raise if *actual* does not match *expected* process name."""
    if actual != expected:
        raise ValueError(
            f"Cannot save process {actual!r} to {context} (expected {expected!r})"
        )


def extract_named_entries(
    items: Any, default_line: int = 0
) -> tuple[list[str], dict[str, int]]:
    """Extract names from a list of dicts with a 'Name' key.

    Returns (names, {name: default_line}) tuple.
    """
    if not isinstance(items, list):
        return [], {}
    names = [
        item["Name"] for item in items if isinstance(item, dict) and "Name" in item
    ]
    return names, {name: default_line for name in names}


def extract_datasource(meta: Any) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(datasource_type, datasource_query)`` from process metadata.

    *meta* is the format-specific metadata mapping (the JSON object, the parsed
    YAML ``definition``, …).  Returns ``(None, None)`` when no ``DataSource`` is
    present.  The query is only meaningful for ODBC sources; other types leave
    it ``None``.
    """
    if not isinstance(meta, dict):
        return None, None
    datasource = meta.get("DataSource")
    if not isinstance(datasource, dict):
        return None, None
    ds_type = datasource.get("Type")
    query = datasource.get("Query")
    return (
        ds_type if isinstance(ds_type, str) else None,
        query if isinstance(query, str) else None,
    )
