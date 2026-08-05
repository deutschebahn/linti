"""Loader for TM1 YAML process files.

Supports two formats:
- Legacy TM1py format: ``!TM1py.ProcessObject`` tag with fields at root level.
- Process-definition format: ``config.definition`` wrapper with the same fields
  nested under ``config.definition``.
"""

from pathlib import Path
from typing import Any

import yaml

from linti.model.process_ir import (
    ProcedureInfo,
    ProcessIR,
    extract_procedures,  # noqa: F401 – re-export
)
from linti.provider.base import extract_datasource


# Custom YAML constructor to handle !TM1py.ProcessObject tags
def _process_object_constructor(loader: Any, node: Any) -> dict:
    """Constructor for !TM1py.ProcessObject tag."""
    return loader.construct_mapping(node)


# Register the custom constructor with different loaders
yaml.add_constructor(
    "!TM1py.ProcessObject", _process_object_constructor, Loader=yaml.SafeLoader
)


def _find_all_item_lines(lines: list[str], section: str, key: str) -> list[int]:
    """
    Find the YAML line numbers of all items in a list section in a single pass.

    Args:
        lines: Split content lines
        section: Section name (e.g., "Parameters", "Variables")
        key: Key to search for inside each list item (e.g., "Name")

    Returns:
        List of 1-based line numbers, one per list item (defaults to 1 when
        the key line cannot be located).
    """
    result: list[int] = []
    section_found = False
    in_item = False
    item_line = 1  # fallback

    for i, line in enumerate(lines, 1):
        if line.strip().startswith(section + ":"):
            section_found = True
            continue

        if not section_found:
            continue

        # A non-indented line after the section header means the section ended.
        if line and not line[0].isspace():
            break

        stripped = line.strip()
        if stripped.startswith("- "):
            # Flush the previous item if we didn't find its key line.
            if in_item:
                result.append(item_line)
            in_item = True
            item_line = 1  # reset fallback
            # The key might be on the same line as the "- " marker.
            if f"{key}:" in stripped:
                result.append(i)
                in_item = False
        elif in_item and f"{key}:" in stripped:
            result.append(i)
            in_item = False

    # Flush last item if its key was never found.
    if in_item:
        result.append(item_line)

    return result


def _find_procedure_end_line(
    lines: list[str], content_start_line: int, content_indent: int
) -> int:
    """Find the 1-based YAML line where procedure content ends.

    Args:
        lines: Full YAML file split into lines
        content_start_line: 1-based line where procedure content starts
        content_indent: Required content indentation for this YAML format

    Returns:
        1-based line number of the last non-empty content line.
    """
    content_prefix = " " * content_indent
    start_idx = max(content_start_line - 1, 0)
    last_content_line = content_start_line - 1

    for idx in range(start_idx, len(lines)):
        line = lines[idx]

        # Blank lines can be inside block scalars; ignore for boundary detection.
        if not line.strip():
            continue

        # Properly-indented content line.
        if line.startswith(content_prefix):
            last_content_line = idx + 1
            continue

        # Any non-content line ends the block scalar content.
        break

    return last_content_line


def _is_tm1_process_yaml(content: str, data: dict) -> bool:
    """Return *True* if *content* / *data* represent a TM1 process YAML.

    Detection rules:
    - **Legacy format** - the raw text starts with the ``!TM1py.ProcessObject``
      YAML tag.
    - **New format** - the parsed mapping contains ``kind: "process_definition"``.
    - **Bare format** - the root mapping contains at least one TM1 procedure
      key (``PrologProcedure``, ``MetadataProcedure``, ``DataProcedure``,
      ``EpilogProcedure``).
    """
    # Legacy TM1py export — tag is always the very first token.
    if content.lstrip().startswith("!TM1py.ProcessObject"):
        return True

    # New structured format uses an explicit discriminator.
    if isinstance(data, dict) and data.get("kind") == "process_definition":
        return True

    # Bare YAML with procedure keys at root level.
    _PROCEDURE_KEYS = {
        "PrologProcedure",
        "MetadataProcedure",
        "DataProcedure",
        "EpilogProcedure",
    }
    if isinstance(data, dict) and _PROCEDURE_KEYS & data.keys():
        return True

    return False


def _extract_definition(data: dict) -> tuple[dict, bool]:
    """Return the process-definition dict and whether the new format was used.

    New format:  config.definition.<fields>
    Legacy:      <fields> at root level
    """
    config = data.get("config")
    if isinstance(config, dict):
        definition = config.get("definition")
        if isinstance(definition, dict):
            return definition, True
    return data, False


def _serialize_procedure_lines(code: str, indent_prefix: str) -> list[str]:
    """Serialize procedure code back into YAML block-scalar content lines."""
    serialized_lines: list[str] = []
    for line in code.split("\n"):
        if not line and not serialized_lines:
            continue
        if line:
            serialized_lines.append(f"{indent_prefix}{line}\n")
        else:
            serialized_lines.append("\n")

    if not serialized_lines:
        return []

    return serialized_lines


class YamlProvider:
    """Single-process provider for YAML-based TM1 process files.

    Supports legacy ``!TM1py.ProcessObject`` and ``config.definition``
    wrapper formats.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def list_processes(self) -> list[str]:
        return [self._load_process().name]

    def get_process(self, name: str) -> ProcessIR:
        process = self._load_process()
        if process.name != name:
            raise ValueError(
                f"Unknown YAML process: {name!r} (expected {process.name!r})"
            )
        return process

    def save_process(self, process: ProcessIR) -> None:
        yaml_lines = self.file_path.read_text().splitlines(keepends=True)
        indent_prefix = " " * process.provider_data.get("content_indent", 0)

        procedure_infos = sorted(
            extract_procedures(process).items(),
            key=lambda item: item[1].source_line,
            reverse=True,
        )

        for _name, proc_info in procedure_infos:
            if proc_info.source_line < 1:
                raise ValueError("ProcessIR is missing valid YAML source line metadata")
            # Empty procedure (no content lines in YAML) — nothing to replace.
            if proc_info.source_end_line < proc_info.source_line:
                continue
            start_idx = proc_info.source_line - 1
            end_idx = proc_info.source_end_line
            yaml_lines[start_idx:end_idx] = _serialize_procedure_lines(
                proc_info.code,
                indent_prefix,
            )

        self.file_path.write_text("".join(yaml_lines))

    def _load_process(self) -> ProcessIR:
        """Load a TM1 process from a YAML file."""
        content, lines, data = self._read_and_validate()
        definition, is_new_format = _extract_definition(data)

        # In the new format, procedure code lines are indented by 6 spaces
        # (config: 0, definition: 2, PrologProcedure: 4, content: 6).
        # In the legacy format, content is indented by 2 spaces.
        content_indent = 6 if is_new_format else 2

        process_name = definition.get("Name", "Unknown")
        procedures = self._parse_procedures(lines, definition, content_indent)
        parameters, parameter_lines = self._parse_named_items(
            lines, definition, "Parameters"
        )
        variables, variable_lines = self._parse_named_items(
            lines, definition, "Variables"
        )
        datasource_type, datasource_query = extract_datasource(definition)

        return ProcessIR(
            name=process_name,
            prolog=procedures["prolog"],
            metadata=procedures["metadata"],
            data=procedures["data"],
            epilog=procedures["epilog"],
            parameters=parameters,
            parameter_lines=parameter_lines,
            variables=variables,
            variable_lines=variable_lines,
            datasource_type=datasource_type,
            datasource_query=datasource_query,
            provider_data={"content_indent": content_indent},
        )

    def _read_and_validate(self) -> tuple[str, list[str], dict]:
        """Read the YAML file and validate it as a TM1 process."""
        content = self.file_path.read_text()
        lines = content.split("\n")
        data = yaml.safe_load(content)

        if not data:
            raise ValueError(f"Empty or invalid YAML file: {self.file_path}")

        if not _is_tm1_process_yaml(content, data):
            raise ValueError(
                f"Not a TM1 process YAML file (missing !TM1py.ProcessObject "
                f'tag or kind: "process_definition"): {self.file_path}'
            )
        return content, lines, data

    @staticmethod
    def _parse_procedures(
        lines: list[str], definition: dict, content_indent: int
    ) -> dict[str, ProcedureInfo | None]:
        """Parse procedure sections from the YAML definition."""
        procedure_keys = [
            "PrologProcedure",
            "MetadataProcedure",
            "DataProcedure",
            "EpilogProcedure",
        ]
        line_numbers = {}
        for i, line in enumerate(lines, 2):
            for key in procedure_keys:
                if line.strip().startswith(key + ":"):
                    line_numbers[key] = i

        procedures: dict[str, ProcedureInfo | None] = {}
        for key, short_name in zip(
            procedure_keys, ["prolog", "metadata", "data", "epilog"], strict=False
        ):
            code = definition.get(key)
            if code is not None:
                yaml_line = line_numbers.get(key, 0)
                yaml_end_line = _find_procedure_end_line(
                    lines, yaml_line, content_indent
                )
                procedures[short_name] = ProcedureInfo(
                    code=code,
                    source_line=yaml_line,
                    source_end_line=yaml_end_line,
                )
            else:
                procedures[short_name] = None

        return procedures

    @staticmethod
    def _parse_named_items(
        lines: list[str], definition: dict, section: str
    ) -> tuple[list[str], dict[str, int]]:
        """Extract named items with YAML line numbers from a definition section."""
        items_list = definition.get(section)
        if not isinstance(items_list, list):
            return [], {}

        item_line_numbers = _find_all_item_lines(lines, section, "Name")
        names: list[str] = []
        name_lines: dict[str, int] = {}
        for i, item in enumerate(items_list):
            if isinstance(item, dict) and "Name" in item:
                name = item["Name"]
                names.append(name)
                name_lines[name] = (
                    item_line_numbers[i] if i < len(item_line_numbers) else 1
                )
        return names, name_lines
