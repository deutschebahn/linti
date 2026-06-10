"""Base classes and data model for TM1 process loaders.

This module defines format-agnostic data structures used across all loaders
(YAML, plain ``.ti``, and future formats like ``.pro`` or JSON).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProcedureInfo:
    """Code of a single procedure section with source location information.

    Attributes:
        code: Raw TI code extracted from the source file.
        source_line: 1-based line number where the code starts in the
            original source file (YAML, .pro, …).  For plain ``.ti``
            files this is always ``1``.
        source_end_line: 1-based line number where the code ends in the
            original source file.
    """

    code: str
    source_line: int = 1
    source_end_line: int = 1


@dataclass
class TM1Process:
    """Format-agnostic representation of a loaded TM1 process.

    Every loader produces an instance of this class so the linting pipeline
    can operate identically regardless of the input format.

    Attributes:
        name: Process name (filename stem for ``.ti`` files).
        source_path: Absolute path to the file the process was loaded from.
        procedures: Mapping of block name (``prolog``, ``metadata``, ``data``,
            ``epilog``) to :class:`ProcedureInfo`, or ``None`` when the
            block is absent.
        parameters: Ordered list of declared parameter names.
        parameter_lines: Mapping of parameter name → source line number.
        variables: Ordered list of data-source variable names.
        variable_lines: Mapping of variable name → source line number.
        content_indent: Number of leading spaces to strip/add when
            reading/writing procedure code inside structured formats
            (e.g. 2 for legacy YAML, 6 for new YAML).  Always ``0``
            for plain ``.ti`` files.
    """

    name: str
    source_path: Path
    procedures: dict[str, Optional[ProcedureInfo]]
    parameters: list[str] = field(default_factory=list)
    parameter_lines: dict[str, int] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    variable_lines: dict[str, int] = field(default_factory=dict)
    content_indent: int = 0


class BaseLoader(ABC):
    """Abstract base class for TM1 process file loaders."""

    @abstractmethod
    def can_load(self, file_path: Path) -> bool:
        """Return ``True`` if this loader supports *file_path*."""
        ...

    @abstractmethod
    def load(self, file_path: Path) -> TM1Process:
        """Load *file_path* and return a :class:`TM1Process`."""
        ...


def extract_procedures(process: TM1Process) -> dict[str, ProcedureInfo]:
    """Return only the non-``None`` procedures of *process*.

    This is a convenience helper used by the linting and auto-fix pipelines.
    """
    return {name: info for name, info in process.procedures.items() if info is not None}
