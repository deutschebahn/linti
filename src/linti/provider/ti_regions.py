"""Shared parser/serializer for region-based ``.ti`` process code."""

import re

from linti.model.process_ir import ProcedureInfo, ProcessIR

_REGION_PATTERN = re.compile(
    r"^#region\s+(Prolog|Metadata|Data|Epilog)\s*$", re.IGNORECASE
)
_ENDREGION_PATTERN = re.compile(r"^#endregion\s*$", re.IGNORECASE)

_SECTION_ORDER = ("Prolog", "Metadata", "Data", "Epilog")


def parse_ti_regions(code: str) -> dict[str, ProcedureInfo]:
    """Parse ``#region``-delimited sections from ``.ti`` code.

    Returns:
        Mapping of lowercase section names (prolog, metadata, data, epilog)
        to ProcedureInfo objects.
    """
    lines = code.split("\n")
    sections: dict[str, ProcedureInfo] = {}

    current_section: str | None = None
    section_start: int = 0
    section_lines: list[str] = []

    for i, line in enumerate(lines, 1):
        region_match = _REGION_PATTERN.match(line.strip())
        if region_match:
            current_section = region_match.group(1).lower()
            section_start = i + 1
            section_lines = []
            continue

        if _ENDREGION_PATTERN.match(line.strip()):
            if current_section is not None:
                section_code = "\n".join(section_lines)
                sections[current_section] = ProcedureInfo(
                    code=section_code,
                    source_line=section_start,
                    source_end_line=max(i - 1, section_start),
                )
                current_section = None
            continue

        if current_section is not None:
            section_lines.append(line)

    return sections


def serialize_ti_regions(process: ProcessIR) -> str:
    """Serialize ProcessIR into ``#region``-delimited ``.ti`` code."""
    parts: list[str] = []

    for section_name in _SECTION_ORDER:
        proc_info: ProcedureInfo | None = getattr(process, section_name.lower(), None)
        if proc_info is None:
            continue
        parts.append(f"#region {section_name}")
        parts.append(proc_info.code)
        parts.append("#endregion")

    return "\n".join(parts) + "\n"
