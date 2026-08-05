"""Provider for PA code ``.ti`` format with ``#SECTION`` and ``#JSON_PROPERTIES``."""

import json
import re
from pathlib import Path
from typing import Any

from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import (
    ProviderError,
    extract_datasource,
    extract_named_entries,
    validate_process_name,
)

_SECTION_PATTERN = re.compile(
    r"^#SECTION\s+(Prolog|Metadata|Data|Epilog)\s*$", re.IGNORECASE
)
_JSON_PROPERTIES_PATTERN = re.compile(r"^#JSON_PROPERTIES\s*$", re.IGNORECASE)

_SECTION_ORDER = ("Prolog", "Metadata", "Data", "Epilog")


def is_pa_code_content(content: str) -> bool:
    """Return True if content matches PA code markers."""
    has_section = False
    has_json_properties = False

    for line in content.splitlines():
        stripped = line.strip()
        if _SECTION_PATTERN.match(stripped):
            has_section = True
        elif _JSON_PROPERTIES_PATTERN.match(stripped):
            has_json_properties = True

    return has_section and has_json_properties


def _parse_sections(lines: list[str], end_line: int) -> dict[str, ProcedureInfo]:
    """Parse section code from lines until *end_line* (1-based, exclusive)."""
    sections: dict[str, ProcedureInfo] = {}

    current_name: str | None = None
    current_start: int = 0
    current_lines: list[str] = []

    for line_no in range(1, end_line):
        line = lines[line_no - 1]
        match = _SECTION_PATTERN.match(line.strip())
        if match:
            if current_name is not None:
                code = "\n".join(current_lines)
                sections[current_name] = ProcedureInfo(
                    code=code,
                    source_line=current_start,
                    source_end_line=max(line_no - 1, current_start),
                )

            current_name = match.group(1).lower()
            current_start = line_no + 1
            current_lines = []
            continue

        if current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        code = "\n".join(current_lines)
        sections[current_name] = ProcedureInfo(
            code=code,
            source_line=current_start,
            source_end_line=max(end_line - 1, current_start),
        )

    return sections


def _parse_json_properties(lines: list[str]) -> tuple[dict[str, Any], int]:
    """Parse JSON object following ``#JSON_PROPERTIES`` marker.

    Returns:
        Tuple of (properties_dict, json_marker_line)
    """
    json_marker_line = 0
    for i, line in enumerate(lines, 1):
        if _JSON_PROPERTIES_PATTERN.match(line.strip()):
            json_marker_line = i
            break

    if json_marker_line == 0:
        return {}, 0

    json_text = "\n".join(lines[json_marker_line:]).strip()
    if not json_text:
        return {}, json_marker_line

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ProviderError("Invalid #JSON_PROPERTIES JSON block") from exc

    return data if isinstance(data, dict) else {}, json_marker_line


def serialize_pa_code(process: ProcessIR, metadata: dict[str, Any]) -> str:
    """Serialize ProcessIR and metadata to PA code format."""
    parts: list[str] = []
    for section_name in _SECTION_ORDER:
        proc_info: ProcedureInfo | None = getattr(process, section_name.lower(), None)
        parts.append(f"#SECTION {section_name}")
        parts.append((proc_info.code if proc_info is not None else "").rstrip("\n"))
        parts.append("")

    parts.append("#JSON_PROPERTIES")
    parts.append(json.dumps(metadata, indent=2))
    return "\n".join(parts).rstrip() + "\n"


class PaCodeProvider:
    """Single-process provider for PA code ``.ti`` files."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def list_processes(self) -> list[str]:
        return [self.file_path.stem]

    def get_process(self, name: str) -> ProcessIR:
        expected_name = self.file_path.stem
        if name != expected_name:
            raise ProviderError(
                f"Unknown PA code process: {name!r} (expected {expected_name!r})"
            )

        content = self.file_path.read_text()
        if not is_pa_code_content(content):
            raise ProviderError(f"Not a PA code file: {self.file_path}")

        lines = content.splitlines()
        metadata, json_marker_line = _parse_json_properties(lines)
        section_end = json_marker_line if json_marker_line > 0 else len(lines) + 1
        sections = _parse_sections(lines, section_end)

        parameters, parameter_lines = extract_named_entries(
            metadata.get("Parameters", []), default_line=1
        )
        variables, variable_lines = extract_named_entries(
            metadata.get("Variables", []), default_line=1
        )
        datasource_type, datasource_query = extract_datasource(metadata)

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
            provider_data={"pa_json_properties": metadata, "pa_code": True},
        )

    def save_process(self, process: ProcessIR) -> None:
        validate_process_name(process.name, self.file_path.stem, str(self.file_path))

        metadata = process.provider_data.get("pa_json_properties")
        if not isinstance(metadata, dict):
            metadata = {}

        self.file_path.write_text(serialize_pa_code(process, metadata))
