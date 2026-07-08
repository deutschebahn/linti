"""Context object for linting operations."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from linti.linter.constant_propagation import ConstantPropagationIndex
    from linti.linter.possible_values import PossibleValues
    from linti.model.process_ir import ProcedureInfo, ProcessIR


@dataclass
class LintContext:
    """
    Contains all contextual information for linting.

    This class encapsulates context that rules may need during linting,
    avoiding parameter proliferation in method signatures.

    Attributes:
        block: TM1 block context (prolog, metadata, data, epilog, or None)
        parameters: List of parameter names from YAML Parameters section
        parameter_lines: Dict mapping parameter names to their YAML line numbers
        variables: List of data source variable names from YAML Variables section
        block_stack: Stack tracking nested control flow blocks (IF/ELSE)
        tokens: Full token list of the procedure being linted (including
            whitespace and comments).  Statement rules that need source-level
            detail — e.g. to detect comments inside an otherwise empty block —
            read it here.
        source: Raw source text of the procedure being linted.  Used to slice
            the exact text span of an auto-fix; token values cannot be relied
            on for this because string literals are stored unquoted.
        constants: Process-wide ConstantPropagationIndex shared by all
            sections of the process, or None when none was supplied (e.g. a
            rule linted in isolation without a process model).
            Rules read it through :meth:`possible_values`.
        datasource_type: Data source type of the process (``ODBC``, ``ASCII``,
            ``None``, …), or None when the format carries no datasource metadata.
        datasource_query: SQL query of an ODBC data source, or None.
    """

    block: Optional[str] = None
    process_name: Optional[str] = None
    parameters: Optional[list[str]] = None
    parameter_lines: Optional[dict] = None  # {param_name: source_line}
    variables: Optional[list[str]] = None
    variable_lines: Optional[dict] = None  # {var_name: source_line}
    block_start_line: Optional[int] = None
    block_end_line: Optional[int] = None
    block_stack: list[str] = field(default_factory=list)
    tokens: Optional[list] = None
    source: Optional[str] = None
    constants: Optional["ConstantPropagationIndex"] = None
    datasource_type: Optional[str] = None
    datasource_query: Optional[str] = None

    @classmethod
    def for_procedure(
        cls,
        process: "ProcessIR",
        proc_name: str,
        proc_info: "ProcedureInfo",
        constants: Optional["ConstantPropagationIndex"] = None,
        *,
        track_block_end: bool = True,
    ) -> "LintContext":
        """Build the per-procedure context shared by the lint and auto-fix loops.

        Centralises the field mapping from a
        :class:`~linti.model.process_ir.ProcessIR` so the two call sites
        (:func:`~linti.linter.api.lint_process_model` and
        :func:`~linti.linter.fixer.auto_fix_process`) cannot drift — both wire
        the same process-wide metadata (parameters, datasource settings,
        constant propagation index) into every procedure's context.

        *track_block_end* stays ``True`` for a normal lint so
        :meth:`is_end_of_procedure` knows the procedure's last line.  The
        auto-fix loop passes ``False``: while fixing, a whole procedure may
        still be squashed onto one line, and a set ``block_end_line`` would make
        every statement on that line look final and suppress
        ``NewLinePerStatementRule`` (F320) — the very fix that splits them apart
        across passes.  The end-of-file check in that rule still stops a newline
        being demanded after the true final statement.
        """
        return cls(
            block=proc_name,
            process_name=process.name,
            parameters=process.parameters,
            parameter_lines=process.parameter_lines,
            variables=process.variables,
            variable_lines=process.variable_lines,
            block_start_line=proc_info.source_line,
            block_end_line=proc_info.source_end_line if track_block_end else None,
            constants=constants,
            datasource_type=process.datasource_type,
            datasource_query=process.datasource_query,
        )

    def possible_values(self, name: str, line: int) -> "PossibleValues":
        """Return what is statically known about *name* at *line*.

        The single entry point into constant propagation.  *line* is 1-based
        and relative to the current block's code — the same coordinates rule
        tokens and AST nodes carry.  The returned
        :class:`~linti.linter.possible_values.PossibleValues` is a
        cascade — read exactly the strength the rule needs:

        * ``pv.exact`` — the one fully known scalar, or ``None``.
        * ``pv.all_of(...)`` / ``pv.any_of(...)`` / ``pv.values`` — reason over
          every possible value; a single known value is the one-element case.
        * ``pv.all_contain(sub)`` / ``pv.any_contains(sub)`` — substring
          questions; a partially known variant counts when a known fragment
          proves it.
        * ``pv.partial`` — the known fragments of a half-dynamic string.
        * ``pv.assigned`` — whether *name* was written at all (e.g. a
          ``DatasourceQuery`` override), even when its value is dynamic.

        Without a constant propagation index in this context the variable
        reports as never assigned.
        """
        from linti.linter.possible_values import UNASSIGNED

        if self.constants is None or self.block is None:
            return UNASSIGNED
        return self.constants.possible_values_at(name, self.block, line)

    def in_control_block(self) -> bool:
        """
        Check if currently inside a control flow block (IF/ELSE).

        Returns:
            True if inside any control block, False otherwise.
        """
        return len(self.block_stack) > 0

    def current_block_type(self) -> Optional[str]:
        """
        Get the type of the current innermost control block.

        Returns:
            'if', 'else', or None if not in any control block.
        """
        return self.block_stack[-1] if self.block_stack else None

    def is_end_of_procedure(self, token_line: int) -> bool:
        """Check whether a token line maps to the end of the current procedure.

        Args:
            token_line: 1-based token line relative to the linted procedure text

        Returns:
            True if this token is on the last YAML line of the current procedure.
        """
        if self.block_start_line is None or self.block_end_line is None:
            return False
        absolute_line = self.block_start_line + token_line - 1
        return absolute_line >= self.block_end_line

    # Future extensibility examples:
    # file_path: Optional[Path] = None
    # process_name: Optional[str] = None
    # strict_mode: bool = False
