"""Format-agnostic process intermediate representation.

This module defines the in-memory process model shared by all providers,
independent of whether the process originates from a file, an API, or any
other storage backend.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProcedureInfo:
    """Code of a single procedure section with source location information.

    Attributes:
        code: Raw TI code extracted from the source file.
        source_line: 1-based line number where the code starts in the
            original source file (YAML, .pro, ...). For plain ``.ti``
            files this is always ``1``.
        source_end_line: 1-based line number where the code ends in the
            original source file.
    """

    code: str
    source_line: int = 1
    source_end_line: int = 1


@dataclass
class ProcessIR:
    """Format-agnostic representation of a TM1 process.

    Attributes:
        name: Provider-level process name.
        prolog: Prolog procedure, if present.
        metadata: Metadata procedure, if present.
        data: Data procedure, if present.
        epilog: Epilog procedure, if present.
        parameters: Ordered list of declared parameter names.
        parameter_lines: Mapping of parameter name to source line number.
        variables: Ordered list of data-source variable names.
        variable_lines: Mapping of variable name to source line number.
        datasource_type: Data source type (e.g. ``ODBC``, ``ASCII``, ``None``)
            as declared in the process metadata, or ``None`` when the format
            carries no datasource metadata (plain ``.ti``).
        datasource_query: SQL query text for an ODBC data source, or ``None``.
        provider_data: Provider-specific persistence hints. This keeps the IR
            storage-agnostic while still allowing providers to round-trip
            source-specific details such as YAML indentation.
    """

    name: str
    prolog: Optional[ProcedureInfo] = None
    metadata: Optional[ProcedureInfo] = None
    data: Optional[ProcedureInfo] = None
    epilog: Optional[ProcedureInfo] = None
    parameters: list[str] = field(default_factory=list)
    parameter_lines: dict[str, int] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    variable_lines: dict[str, int] = field(default_factory=dict)
    datasource_type: Optional[str] = None
    datasource_query: Optional[str] = None
    provider_data: dict[str, Any] = field(default_factory=dict)


def extract_procedures(process: ProcessIR) -> dict[str, ProcedureInfo]:
    """Return only the non-``None`` procedures of *process*.

    This is a convenience helper used by the linting and auto-fix pipelines.
    """
    procedures = {
        "prolog": process.prolog,
        "metadata": process.metadata,
        "data": process.data,
        "epilog": process.epilog,
    }
    return {name: info for name, info in procedures.items() if info is not None}
