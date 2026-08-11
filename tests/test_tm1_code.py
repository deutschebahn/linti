"""Tests for the server-procedure decoder."""

import pytest

from linti.provider.tm1_code import decode_procedure

CRLF = "\r\n"

# name -> raw procedure text as a server would hand it over
CASES = {
    "crlf_with_block": (
        CRLF
        + "#****Begin: Generated Statements***"
        + CRLF
        + "NULL;"
        + CRLF
        + "#****End: Generated Statements****"
        + CRLF
        + "sTest = 'x';"
        + CRLF
        + "nFoo = 1;"
        + CRLF
    ),
    "lf_with_block": (
        "\n#****Begin: Generated Statements***\n"
        "NULL;\n"
        "#****End: Generated Statements****\n"
        "\nsTest = 'x';\n"
    ),
    "no_block": "sTest = 'x';" + CRLF + "nFoo = 1;" + CRLF,
    "empty": "",
    "unterminated_block": (
        "#****Begin: Generated Statements***"
        + CRLF
        + "NULL;"
        + CRLF
        + "sTest='x';"
        + CRLF
    ),
    "two_blocks": (
        "#****Begin: Generated Statements***"
        + CRLF
        + "A;"
        + CRLF
        + "#****End: Generated Statements****"
        + CRLF
        + "#****Begin: Generated Statements***"
        + CRLF
        + "B;"
        + CRLF
        + "#****End: Generated Statements****"
        + CRLF
        + "sTest='x';"
        + CRLF
    ),
    "block_without_trailing_newline": (
        "#****Begin: Generated Statements***"
        + CRLF
        + "NULL;"
        + CRLF
        + "#****End: Generated Statements****"
    ),
    "form_feed_in_code": "sA='x\x0cy';" + CRLF + "sB=2;" + CRLF,
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_roundtrip_invariant(name):
    """``prefix + code.replace("\\n", newline)`` reproduces the input byte for byte.

    Nothing depends on this yet — linti does not write to a server. It is
    asserted now because a future write-back path relies on it, and a silent
    break while the property is unused would only surface as corrupted process
    code much later.
    """
    raw = CASES[name]
    decoded = decode_procedure(raw)
    assert decoded.prefix + decoded.code.replace("\n", decoded.newline) == raw


def test_generated_block_is_stripped_and_lines_offset():
    decoded = decode_procedure(CASES["crlf_with_block"])
    assert decoded.code == "sTest = 'x';\nnFoo = 1;\n"
    # Blank line, BEGIN, NULL;, END occupy TM1 lines 1-4.
    assert decoded.first_line == 5


def test_crlf_is_normalised_so_no_line_looks_like_trailing_whitespace():
    decoded = decode_procedure(CASES["no_block"])
    assert "\r" not in decoded.code
    assert decoded.newline == CRLF
    assert decoded.first_line == 1


def test_blank_line_after_the_block_stays_in_code():
    """Otherwise the reported line numbers would drift by one."""
    decoded = decode_procedure(CASES["lf_with_block"])
    assert decoded.code == "\nsTest = 'x';\n"
    assert decoded.first_line == 5


def test_unterminated_block_strips_nothing():
    """Noisy output beats silently swallowing the whole procedure."""
    decoded = decode_procedure(CASES["unterminated_block"])
    assert decoded.first_line == 1
    assert "sTest='x';" in decoded.code
    assert "Begin: Generated Statements" in decoded.code


def test_repeated_blocks_are_all_stripped():
    decoded = decode_procedure(CASES["two_blocks"])
    assert decoded.code == "sTest='x';\n"
    assert decoded.first_line == 7


def test_form_feed_does_not_split_a_line():
    """splitlines() would break on \\x0c, which TM1 uses as a field separator."""
    decoded = decode_procedure(CASES["form_feed_in_code"])
    assert decoded.code == "sA='x\x0cy';\nsB=2;\n"


def test_lone_carriage_returns_are_normalised():
    """The one deliberate exception to the roundtrip invariant."""
    decoded = decode_procedure("sA='x';\rsB=2;\r")
    assert decoded.code == "sA='x';\nsB=2;\n"
    assert decoded.newline == "\n"


def test_empty_procedure():
    decoded = decode_procedure("")
    assert decoded.code == ""
    assert decoded.first_line == 1
    assert decoded.prefix == ""
