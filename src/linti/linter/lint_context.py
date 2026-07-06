"""Context object for linting operations."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from linti.linter.constant_propagation import (
        ConstantPropagationIndex,
        PartialString,
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
            Rules read it through :meth:`constant_value`.
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

    def constant_value(self, name: str, line: int) -> Optional[Union[str, float]]:
        """Return the statically known value of *name* at *line*, or ``None``.

        *line* is 1-based and relative to the current block's code — the same
        coordinates rule tokens and AST nodes carry.  ``None`` means the value
        is unknown (dynamic, conditional, or never assigned) or no constant
        propagation index is available in this context.
        """
        if self.constants is None or self.block is None:
            return None
        return self.constants.value_at(name, self.block, line)

    def partial_value(self, name: str, line: int) -> Optional["PartialString"]:
        """Return the partially known value of *name* at *line*, or ``None``.

        Yields a :class:`~linti.linter.constant_propagation.PartialString` only
        when *name* holds a mix of known fragments and dynamic gaps (e.g.
        ``sName = 'prefix_' | pDyn;``).  Fully known values (use
        :meth:`constant_value`), fully unknown values, and contexts without a
        constant propagation index all return ``None``.
        """
        if self.constants is None or self.block is None:
            return None
        return self.constants.partial_value_at(name, self.block, line)

    def possible_values(self, name: str, line: int) -> "PossibleValues":
        """Return the set of values *name* may hold at *line*.

        Rules use
        :meth:`~linti.linter.constant_propagation.PossibleValues.all_of` (∀,
        every branch variant satisfies a predicate) and
        :meth:`~linti.linter.constant_propagation.PossibleValues.any_of` (∃, at
        least one variant does).  Returns the fully unknown value when *name* is
        dynamic, never assigned, or no constant propagation index is available.
        """
        from linti.linter.constant_propagation import TOP

        if self.constants is None or self.block is None:
            return TOP
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
