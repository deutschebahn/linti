"""Loader for plain TI (``.ti``) process files.

A ``.ti`` file contains raw TI code without any structured metadata.  The
entire file content is treated as the *prolog* procedure.
"""

from pathlib import Path

from linti.loader.base import BaseLoader, ProcedureInfo, TM1Process


class TiLoader(BaseLoader):
    """Loader for plain ``.ti`` files."""

    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".ti"

    def load(self, file_path: Path) -> TM1Process:
        """Load a plain ``.ti`` file as a TM1 process.

        The entire file content is placed into the ``prolog`` procedure.
        No parameters, variables, or other metadata are available.
        """
        code = file_path.read_text()
        line_count = code.count("\n") + (1 if code and not code.endswith("\n") else 0)

        return TM1Process(
            name=file_path.stem,
            source_path=file_path.resolve(),
            procedures={
                "prolog": ProcedureInfo(
                    code=code,
                    source_line=1,
                    source_end_line=max(line_count, 1),
                ),
                "metadata": None,
                "data": None,
                "epilog": None,
            },
            content_indent=0,
        )
