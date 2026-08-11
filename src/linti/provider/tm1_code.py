"""Decoder for TI procedure text as a TM1 server stores it.

TM1 wraps every procedure in a "generated statements" block and separates lines
with CRLF. Neither belongs in the text a rule sees:

- The generated block is server-owned boilerplate. Linting it produces noise,
  and a fix landing inside it would corrupt the process.
- A stray ``\\r`` reaches the lexer as trailing whitespace, so every single line
  of a server process would report F270.

:func:`decode_procedure` therefore splits a raw procedure into the part linti
lints and the part the server owns. Only the decode direction exists today —
linti does not write to a server yet. The pieces needed to write one back
(``prefix`` and ``newline``) are kept anyway: they fall out of decoding for
free, and they cannot be reconstructed later without re-reading from the
server. See the module invariant on :class:`TM1Code`.

This module knows nothing about TM1py or about ``ProcessIR``; it is pure text,
mirroring the split between :mod:`linti.provider.ti` and
:mod:`linti.provider.ti_regions`.
"""

from dataclasses import dataclass

# The real markers are asymmetric — three stars at BEGIN, four at END. Matching
# on the common prefix avoids encoding that asymmetry in two places and
# tolerates trailing whitespace.
GENERATED_BEGIN_PREFIX = "#****Begin: Generated Statements"
GENERATED_END_PREFIX = "#****End: Generated Statements"


@dataclass(frozen=True)
class TM1Code:
    """A server procedure split into its lintable code and the server's prefix.

    The following holds for every procedure, and is what a future write-back
    path will rely on::

        prefix + code.replace("\\n", newline) == raw

    with one deliberate exception: lone ``\\r`` line endings (classic Mac) are
    normalised, since TM1 never emits them.

    Attributes:
        code: The lintable text — generated block removed, newlines normalised
            to ``\\n``.
        first_line: TM1's own line number for line 1 of ``code``. Reported line
            numbers then match ``tm1.processes.compile()`` and the process
            editor.
        prefix: The removed leading text, byte-verbatim including its original
            line endings. Unused today; the write-back path hands it back
            unchanged so an unfixed section re-serialises to the exact bytes the
            server sent.
        newline: The line ending the procedure used (``\\r\\n`` or ``\\n``).
            Unused today; see ``prefix``.
    """

    code: str
    first_line: int
    prefix: str
    newline: str


def decode_procedure(raw: str) -> TM1Code:
    """Split a raw server procedure into lintable code and the server's prefix."""
    newline = "\r\n" if "\r\n" in raw else "\n"

    # split("\n"), not splitlines(): splitlines also breaks on \x0b, \x0c, \x85
    # and  . TM1 uses \x0c as a field separator in process metadata and TI
    # comments may contain anything, so only split("\n") is exactly reversible
    # through "\n".join. It also leaves each line's trailing \r in place, which
    # is what makes `prefix` below byte-verbatim without any re-encoding.
    raw_lines = raw.split("\n")

    committed = index = 0
    while True:
        # Skip blank lines only tentatively: they belong to the prefix when a
        # generated block follows (server procedures typically open with one),
        # but the blank line separating the block from real code must stay in
        # `code` or the line arithmetic below drifts.
        candidate = index
        while candidate < len(raw_lines) and raw_lines[candidate].strip() == "":
            candidate += 1

        if candidate >= len(raw_lines):
            break
        if not raw_lines[candidate].strip().startswith(GENERATED_BEGIN_PREFIX):
            break

        end = candidate + 1
        while end < len(raw_lines) and not raw_lines[end].strip().startswith(
            GENERATED_END_PREFIX
        ):
            end += 1
        if end >= len(raw_lines):
            # Unterminated BEGIN — strip nothing rather than swallow the whole
            # procedure. The block is then linted as ordinary comments, which is
            # noisy but recoverable; losing the code is not.
            break

        # Commit through the END line, then loop: a procedure can carry the
        # marker pair more than once.
        committed = index = end + 1

    # A block that ends the procedure without a trailing newline must not gain
    # one, or the invariant on TM1Code stops holding.
    terminated = committed < len(raw_lines)
    prefix = "\n".join(raw_lines[:committed]) + (
        "\n" if committed and terminated else ""
    )
    code = "\n".join(raw_lines[committed:])

    return TM1Code(
        code=code.replace("\r\n", "\n").replace("\r", "\n"),
        first_line=committed + 1,
        prefix=prefix,
        newline=newline,
    )
