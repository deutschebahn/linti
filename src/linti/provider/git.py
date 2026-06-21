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
from linti.provider.base import extract_named_entries, validate_process_name
from linti.provider.ti_regions import parse_ti_regions, serialize_ti_regions


class GitProvider:
    """Provider for the TM1 Git-deploy format (JSON + .ti file pair)."""

    def __init__(self, json_path: Path):
        self.json_path = json_path
        self._meta = json.loads(json_path.read_text())
        code_link = self._meta.get("Code@Code.link")
        if not code_link:
            raise ValueError(
                f"JSON metadata missing 'Code@Code.link' field: {json_path}"
            )
        self._ti_path = json_path.parent / code_link

    def list_processes(self) -> list[str]:
        return [self._meta["Name"]]

    def get_process(self, name: str) -> ProcessIR:
        expected_name = self._meta["Name"]
        if name != expected_name:
            raise ValueError(f"Unknown process: {name!r} (expected {expected_name!r})")

        code = self._ti_path.read_text()
        sections = parse_ti_regions(code)
        parameters, parameter_lines = extract_named_entries(
            self._meta.get("Parameters", [])
        )
        variables, variable_lines = extract_named_entries(
            self._meta.get("Variables", [])
        )

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
        )

    def save_process(self, process: ProcessIR) -> None:
        validate_process_name(process.name, self._meta["Name"], str(self.json_path))
        self._ti_path.write_text(serialize_ti_regions(process))
