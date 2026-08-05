"""Loader for TI (``.ti``) process files.

Supports both formats:
- Plain ``.ti`` where the entire file is treated as prolog.
- Region-based ``.ti`` with ``#region``/``#endregion`` procedure sections.
"""

from pathlib import Path

from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import ProviderError, count_code_lines, validate_process_name
from linti.provider.ti_regions import parse_ti_regions, serialize_ti_regions


class TiProvider:
    """Single-process provider for plain ``.ti`` files."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def list_processes(self) -> list[str]:
        return [self.file_path.stem]

    def get_process(self, name: str) -> ProcessIR:
        """Load a ``.ti`` file as a process IR.

        If region markers are present, all recognized sections are loaded.
        Otherwise the full file is treated as the ``prolog`` procedure.
        """
        expected_name = self.file_path.stem
        if name != expected_name:
            raise ProviderError(
                f"Unknown TI process: {name!r} (expected {expected_name!r})"
            )

        code = self.file_path.read_text()
        sections = parse_ti_regions(code)
        if sections:
            return ProcessIR(
                name=expected_name,
                prolog=sections.get("prolog"),
                metadata=sections.get("metadata"),
                data=sections.get("data"),
                epilog=sections.get("epilog"),
                provider_data={"ti_has_regions": True},
            )

        line_count = count_code_lines(code)

        return ProcessIR(
            name=expected_name,
            prolog=ProcedureInfo(
                code=code,
                source_line=1,
                source_end_line=max(line_count, 1),
            ),
        )

    def save_process(self, process: ProcessIR) -> None:
        validate_process_name(process.name, self.file_path.stem, str(self.file_path))

        has_regions = bool(process.provider_data.get("ti_has_regions"))
        has_non_prolog_sections = (
            process.metadata is not None
            or process.data is not None
            or process.epilog is not None
        )
        if has_regions or has_non_prolog_sections:
            self.file_path.write_text(serialize_ti_regions(process))
            return

        code = process.prolog.code if process.prolog is not None else ""
        self.file_path.write_text(code)
