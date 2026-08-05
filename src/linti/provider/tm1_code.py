"""Codec for TI procedure text as a TM1 server stores it.

TM1 wraps every procedure in a "generated statements" block and separates lines
with CRLF. Neither belongs in the text a rule sees:

- The generated block is server-owned boilerplate. Linting it produces noise,
  and letting a fix land inside it would corrupt the process.
- A stray ``\\r`` reaches the lexer as trailing whitespace, so every single line
  of a server process reports F270. Auto-fixing that strips the carriage
  returns, the write-back restores them, and the next run reports them all over
  again — a loop that never converges.

:func:`decode_procedure` therefore splits a raw procedure into the part linti
lints and the part it must hand back untouched; :func:`encode_procedure`
reassembles them. The pair round-trips byte for byte, so a procedure that
picked up no fixes re-serialises to exactly the bytes the server sent.

This module knows nothing about TM1py or about ``ProcessIR``; it is pure text,
mirroring the split between :mod:`linti.provider.ti` and
:mod:`linti.provider.ti_regions`.
"""

from dataclasses import dataclass

# The real markers are asymmetric — three stars at BEGIN, four at END. Matching
# on the common prefix avoids encoding that asymmetry in two places and tolerates
# trailing whitespace.
GENERATED_BEGIN_PREFIX = "#****Begin: Generated Statements"
GENERATED_END_PREFIX = "#****End: Generated Statements"


@dataclass(frozen=True)
class TM1Code:
    """A server procedure split into its lintable code and its fixed prefix.

    Attributes:
        code: The lintable text — generated block removed, newlines normalised
            to ``\\n``.
        prefix: The removed leading text, byte-verbatim including its original
            line endings. Handed back unchanged on write.
        prefix_lines: Number of lines the prefix occupies. ``code`` line 1 is
            TM1 line ``prefix_lines + 1``.
        newline: The line ending the procedure used (``\\r\\n`` or ``\\n``),
            restored on write.
    """

    code: str
    prefix: str
    prefix_lines: int
    newline: str


def decode_procedure(raw: str) -> TM1Code:
    """Split a raw server procedure into lintable code and its fixed prefix."""
    newline = "\r\n" if "\r\n" in raw else "\n"

    # split("\n"), not splitlines(): splitlines also breaks on \x0b, \x0c, \x85
    # and \u2028. TM1 uses \x0c as a field separator in process metadata and TI
    # comments may contain anything, so only split("\n") is exactly reversible
    # through "\n".join.
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
    # one, or the round-trip stops being byte-exact.
    terminated = committed < len(raw_lines)
    prefix = "\n".join(raw_lines[:committed]) + (
        "\n" if committed and terminated else ""
    )
    code = "\n".join(raw_lines[committed:])

    return TM1Code(
        code=code.replace("\r\n", "\n").replace("\r", "\n"),
        prefix=prefix,
        prefix_lines=committed,
        newline=newline,
    )


def encode_procedure(code: str, prefix: str, newline: str) -> str:
    """Reassemble a server procedure from lintable *code* and its *prefix*.

    ``encode_procedure(c.code, c.prefix, c.newline)`` reproduces the input of
    :func:`decode_procedure` byte for byte, with one deliberate exception:
    lone ``\\r`` line endings (classic Mac) are normalised. TM1 never emits
    them, so repairing them is preferable to preserving them.
    """
    return prefix + code.replace("\n", newline)
