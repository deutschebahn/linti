"""Parse and apply ``# noqa`` suppression directives.

Supported formats (TI uses ``#`` for comments):

1. **Inline (trailing) comment** – suppresses rules for the current line::

    nVar=1;  # noqa: F220

2. **Standalone comment** – suppresses rules for the *next* code line::

       # noqa: F110
       if(nVar = 1);

3. **Procedure-level** – the *first* ``# noqa`` comment in a procedure
   (before any code) suppresses rules for the **entire** procedure/file::

       # noqa: X110,C310
       ExecuteCommand(sCmd, 1);
       RunProcess(pProcess);

4. **Region begin / end** – suppresses rules for all lines in between::

       # noqa-begin: F110
       if(nVar = 1);
       endif;
       # noqa-end: F110
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from linti.lexer.token import Token, TokenType
from linti.linter.lint_issue import LintIssue

# Patterns (case-insensitive)
_NOQA_INLINE_RE = re.compile(r"#\s*noqa\s*:\s*([A-Za-z0-9,\s]+)", re.IGNORECASE)
_NOQA_BEGIN_RE = re.compile(r"#\s*noqa-begin\s*:\s*([A-Za-z0-9,\s]+)", re.IGNORECASE)
_NOQA_END_RE = re.compile(r"#\s*noqa-end\s*:\s*([A-Za-z0-9,\s]+)", re.IGNORECASE)


def _parse_rule_ids(raw: str) -> set[str]:
    """Parse comma-separated rule IDs into a canonical, upper-cased set.

    Deprecated rule IDs (e.g. ``S220``) are resolved to their canonical form
    (``C220``) so suppression matches the canonical ID diagnostics carry, and a
    deprecation warning is emitted for each deprecated ID used.
    """
    # Imported lazily to avoid importing the whole rules package at module load.
    from linti.rules.rule_ids import resolve_and_warn

    return {resolve_and_warn(r.strip()) for r in raw.split(",") if r.strip()}


def _is_standalone_comment(tokens: list[Token], comment_index: int) -> bool:
    """Check if the comment token is on a line by itself (no code before it).

    A comment is standalone when everything before it on the same line is
    either whitespace or the beginning of the token stream.
    """
    for j in range(comment_index - 1, -1, -1):
        tok = tokens[j]
        if tok.type == TokenType.NEWLINE:
            return True
        if tok.type == TokenType.WHITESPACE:
            continue
        # Any non-whitespace, non-newline token on the same line means inline
        return False
    # Reached start of stream → standalone (first line)
    return True


@dataclass
class NoqaDirectives:
    """Stores parsed noqa suppression information.

    Attributes:
        line_suppressions: Mapping of line number → set of suppressed rule IDs.
        global_suppressions: Rule IDs suppressed for the entire procedure/file.
    """

    line_suppressions: dict[int, set[str]] = field(default_factory=dict)
    global_suppressions: set[str] = field(default_factory=set)

    def is_suppressed(self, rule_id: str, line: int) -> bool:
        """Return ``True`` if *rule_id* is suppressed on *line*."""
        rule_upper = rule_id.upper()
        if rule_upper in self.global_suppressions:
            return True
        suppressed = self.line_suppressions.get(line)
        if suppressed and rule_upper in suppressed:
            return True
        return False

    def _suppress_line(self, line: int, rule_ids: set[str]) -> None:
        self.line_suppressions.setdefault(line, set()).update(rule_ids)


def parse_noqa(tokens: list[Token]) -> NoqaDirectives:
    """Scan *tokens* and build :class:`NoqaDirectives`.

    Algorithm:
    1. Walk through every ``COMMENT`` token.
    2. Check for ``noqa-begin`` / ``noqa-end`` region markers first.
    3. Then check for plain ``# noqa: …`` directives.
       - If the comment is *standalone* (nothing but whitespace before it on
         the line), it suppresses the **next code line**.
       - If the comment is *trailing* (code precedes it on the line),
         it suppresses the **current line**.
    4. The first standalone ``# noqa: …`` that appears before any non-comment,
       non-whitespace, non-newline token is treated as a **procedure-level**
       suppression covering **all** lines.
    """
    directives = NoqaDirectives()

    # Track open region suppressions: rule_id → start line (for validation)
    open_regions: dict[str, int] = {}

    # Determine whether we have seen real code yet (for procedure-level detection)
    seen_code = False

    for i, token in enumerate(tokens):
        # Track whether we have seen code (anything other than comment/ws/newline)
        if token.type not in (
            TokenType.COMMENT,
            TokenType.WHITESPACE,
            TokenType.NEWLINE,
        ):
            seen_code = True
            continue

        if token.type != TokenType.COMMENT:
            continue

        comment_text = token.value

        # --- Region begin ---
        m_begin = _NOQA_BEGIN_RE.search(comment_text)
        if m_begin:
            rule_ids = _parse_rule_ids(m_begin.group(1))
            for rid in rule_ids:
                open_regions[rid] = token.line
            continue

        # --- Region end ---
        m_end = _NOQA_END_RE.search(comment_text)
        if m_end:
            rule_ids = _parse_rule_ids(m_end.group(1))
            for rid in rule_ids:
                start_line = open_regions.pop(rid, None)
                if start_line is not None:
                    # Suppress all lines from (start_line) to (current line)
                    # We include start_line+1 through end_line-1 (the code lines)
                    # but also include start and end lines themselves for safety
                    for line_no in range(start_line, token.line + 1):
                        directives._suppress_line(line_no, {rid})
            continue

        # --- Plain noqa ---
        m_inline = _NOQA_INLINE_RE.search(comment_text)
        if m_inline:
            rule_ids = _parse_rule_ids(m_inline.group(1))
            standalone = _is_standalone_comment(tokens, i)

            if standalone and not seen_code:
                # Procedure-level suppression (first comment before any code)
                directives.global_suppressions.update(rule_ids)
            elif standalone:
                # Standalone comment → suppress next code line
                next_code_line = _find_next_code_line(tokens, i)
                if next_code_line is not None:
                    directives._suppress_line(next_code_line, rule_ids)
            else:
                # Trailing (inline) comment → suppress current line
                directives._suppress_line(token.line, rule_ids)

    # Any still-open regions extend to end-of-file — suppress remaining lines
    if open_regions:
        max_line = max(t.line for t in tokens) if tokens else 0
        for rid, start_line in open_regions.items():
            for line_no in range(start_line, max_line + 1):
                directives._suppress_line(line_no, {rid})

    return directives


def _find_next_code_line(tokens: list[Token], start_index: int) -> int | None:
    """Find the line number of the next non-comment, non-whitespace token."""
    for j in range(start_index + 1, len(tokens)):
        tok = tokens[j]
        if tok.type not in (
            TokenType.COMMENT,
            TokenType.WHITESPACE,
            TokenType.NEWLINE,
        ):
            return tok.line
    return None


def filter_issues(
    issues: list[LintIssue], directives: NoqaDirectives
) -> list[LintIssue]:
    """Remove issues that are suppressed by *directives*."""
    return [
        issue
        for issue in issues
        if not directives.is_suppressed(issue.rule_id, issue.line)
    ]
