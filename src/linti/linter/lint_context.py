"""Context object for linting operations."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from linti.linter.constant_propagation import (
        ConstantPropagationIndex,
        PossibleValues,
    )


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
            sections of the process, or None (e.g. in the auto-fix pass).
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

    def possible_values(self, name: str, line: int) -> "PossibleValues":
        """Return what is statically known about *name* at *line*.

        The single entry point into constant propagation.  *line* is 1-based
        and relative to the current block's code — the same coordinates rule
        tokens and AST nodes carry.  The returned
        :class:`~linti.linter.constant_propagation.PossibleValues` is a
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
        from linti.linter.constant_propagation import UNASSIGNED

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
