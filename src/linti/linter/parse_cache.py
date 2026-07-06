"""Per-lint-run cache of lexed and parsed process sections.

Both the lint loop (:func:`linti.linter.api.lint_process_model`) and the
:class:`~linti.linter.constant_propagation.ConstantPropagationIndex` need the
token stream and AST of each TI section.  Without coordination every section
would be lexed and parsed twice — once to lint it, once when a rule first
queries the index for a cross-section value.

``SectionParseCache`` lexes and parses each section at most once per lint run
and hands the shared result to both consumers.  It is intentionally *not*
stored on the :class:`~linti.model.process_ir.ProcessIR`: a fresh cache is
created per lint run so nothing leaks between runs.
"""

from dataclasses import dataclass
from typing import Optional

from linti.lexer.lexer import Lexer
from linti.lexer.token import Token
from linti.model.process_ir import ProcessIR
from linti.parser.ast import Program
from linti.parser.parser import (
    DEFAULT_MAX_NESTING_DEPTH,
    NestingDepthExceeded,
    Parser,
)


@dataclass
class ParsedSection:
    """Lex/parse result for a single section.

    Attributes:
        tokens: The section's token stream.
        ast: The parsed program, or ``None`` when parsing raised
            :class:`NestingDepthExceeded`.
        error: The nesting-depth error when parsing failed, else ``None``.
    """

    tokens: list[Token]
    ast: Optional[Program]
    error: Optional[NestingDepthExceeded] = None


class SectionParseCache:
    """Lexes and parses each section of one process at most once.

    Keyed by section name (``prolog``, ``metadata``, ``data``, ``epilog``).
    Missing (``None``) sections are cached as an empty parse so repeated
    lookups stay cheap.
    """

    def __init__(
        self,
        process: ProcessIR,
        max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH,
    ) -> None:
        self._process = process
        self._max_nesting_depth = max_nesting_depth
        self._cache: dict[str, ParsedSection] = {}

    def get(self, section: str) -> ParsedSection:
        """Return the lex/parse result for *section*, computing it on first use."""
        cached = self._cache.get(section)
        if cached is not None:
            return cached

        proc_info = getattr(self._process, section, None)
        code = proc_info.code if proc_info is not None else ""
        tokens = Lexer(code).tokenize()
        try:
            ast = Parser(tokens, max_nesting_depth=self._max_nesting_depth).parse()
            parsed = ParsedSection(tokens=tokens, ast=ast)
        except NestingDepthExceeded as exc:
            parsed = ParsedSection(tokens=tokens, ast=None, error=exc)

        self._cache[section] = parsed
        return parsed
