"""Provider for the TM1 Git-deploy format (JSON metadata + .ti code file).

The Git-deploy format stores each process as a pair of files:
- A ``.json`` file with metadata (name, parameters, variables, data source).
- A ``.ti`` file with procedure code delimited by ``#region`` / ``#endregion``
  markers.

The JSON field ``"Code@Code.link"`` references the ``.ti`` file path relative
to the JSON file.

Note: This provider models exactly one JSON/TI pair as one process. If
directory-level batching is needed in the future, prefer adding a separate
directory provider instead of expanding this class.
"""

import json
from pathlib import Path

from linti.model.process_ir import ProcessIR
from linti.provider.base import (
    DEFAULT_MAX_FILE_SIZE,
    ProviderError,
    ensure_within_size_limit,
    extract_datasource,
    extract_named_entries,
    validate_process_name,
)
from linti.provider.ti_regions import parse_ti_regions, serialize_ti_regions


class GitProvider:
    """Provider for the TM1 Git-deploy format (JSON + .ti file pair)."""

    def __init__(self, json_path: Path, max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        self.json_path = json_path
        self._max_file_size = max_file_size
        ensure_within_size_limit(json_path, max_file_size)
        try:
            self._meta = json.loads(json_path.read_text())
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Invalid JSON in {json_path}: {exc}") from exc
        code_link = self._meta.get("Code@Code.link")
        if not code_link:
            raise ProviderError(
                f"JSON metadata missing 'Code@Code.link' field: {json_path}"
            )
        self._ti_path = self._resolve_code_link(json_path, code_link)

    @staticmethod
    def _resolve_code_link(json_path: Path, code_link: str) -> Path:
        """Resolve ``code_link`` against the JSON file's directory, confined to it.

        The ``Code@Code.link`` value comes from untrusted metadata. Reject
        absolute paths and any relative path that escapes the JSON file's
        parent directory (e.g. ``../../etc/passwd``) to prevent linti from
        reading or overwriting arbitrary files when run on untrusted repos.
        """
        link = Path(code_link)
        if link.is_absolute():
            raise ProviderError(
                f"'Code@Code.link' must be a relative path, got absolute: "
                f"{code_link!r} in {json_path}"
            )
        base = json_path.parent.resolve()
        resolved = (base / link).resolve()
        if not resolved.is_relative_to(base):
            raise ProviderError(
                f"'Code@Code.link' escapes the process directory: "
                f"{code_link!r} in {json_path}"
            )
        return resolved

    def list_processes(self) -> list[str]:
        return [self._meta["Name"]]

    def get_process(self, name: str) -> ProcessIR:
        expected_name = self._meta["Name"]
        if name != expected_name:
            raise ProviderError(
                f"Unknown process: {name!r} (expected {expected_name!r})"
            )

        ensure_within_size_limit(self._ti_path, self._max_file_size)
        code = self._ti_path.read_text()
        sections = parse_ti_regions(code)
        parameters, parameter_lines = extract_named_entries(
            self._meta.get("Parameters", [])
        )
        variables, variable_lines = extract_named_entries(
            self._meta.get("Variables", [])
        )
        datasource_type, datasource_query = extract_datasource(self._meta)

        return ProcessIR(
            name=expected_name,
            prolog=sections.get("prolog"),
            metadata=sections.get("metadata"),
            data=sections.get("data"),
            epilog=sections.get("epilog"),
            parameters=parameters,
            parameter_lines=parameter_lines,
            variables=variables,
            variable_lines=variable_lines,
            datasource_type=datasource_type,
            datasource_query=datasource_query,
        )

    def save_process(self, process: ProcessIR) -> None:
        validate_process_name(process.name, self._meta["Name"], str(self.json_path))
        self._ti_path.write_text(serialize_ti_regions(process))
