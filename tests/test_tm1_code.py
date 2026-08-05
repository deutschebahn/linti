"""Tests for the TM1 server procedure codec."""

import json
from pathlib import Path

import pytest

from linti.provider.tm1_code import decode_procedure, encode_procedure

BEGIN = "#****Begin: Generated Statements***"
END = "#****End: Generated Statements****"

# (id, raw procedure, expected prefix_lines, expected code)
CASES = [
    (
        "single_block",
        f"{BEGIN}\r\n{END}\r\nnValue = 1;\r\n",
        2,
        "nValue = 1;\n",
    ),
    (
        "leading_blank_line",
        # How every real server procedure starts.
        f"\r\n{BEGIN}\r\n{END}\r\n\r\nnValue = 1;\r\n",
        3,
        "\nnValue = 1;\n",
    ),
    (
        "doubled_block",
        f"{BEGIN}\r\n{END}\r\n\r\n{BEGIN}\r\n{END}\r\nnValue = 1;\r\n",
        5,
        "nValue = 1;\n",
    ),
    (
        "no_block",
        "nValue = 1;\r\nnOther = 2;\r\n",
        0,
        "nValue = 1;\nnOther = 2;\n",
    ),
    (
        "marker_mentioned_later",
        # A comment naming the markers further down must not be stripped.
        f"{BEGIN}\r\n{END}\r\n# see {END} above\r\nnValue = 1;\r\n",
        2,
        f"# see {END} above\nnValue = 1;\n",
    ),
    (
        "unterminated_begin",
        # Strip nothing rather than swallow the procedure.
        f"{BEGIN}\r\nnValue = 1;\r\n",
        0,
        f"{BEGIN}\nnValue = 1;\n",
    ),
    (
        "block_without_trailing_newline",
        f"{BEGIN}\r\n{END}",
        2,
        "",
    ),
    (
        "empty",
        "",
        0,
        "",
    ),
    (
        "only_blank_lines",
        "\r\n\r\n",
        0,
        "\n\n",
    ),
    (
        "lf_only_server",
        f"{BEGIN}\n{END}\nnValue = 1;\n",
        2,
        "nValue = 1;\n",
    ),
    (
        "generated_content_inside_block",
        f"{BEGIN}\r\nDatasourceNameForServer = 'x';\r\n{END}\r\nnValue = 1;\r\n",
        3,
        "nValue = 1;\n",
    ),
]


@pytest.mark.parametrize(
    "raw,prefix_lines,expected_code",
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_decode_splits_prefix_from_code(raw, prefix_lines, expected_code):
    decoded = decode_procedure(raw)
    assert decoded.prefix_lines == prefix_lines
    assert decoded.code == expected_code


@pytest.mark.parametrize(
    "raw", [case[1] for case in CASES], ids=[case[0] for case in CASES]
)
def test_round_trip_is_byte_exact(raw):
    decoded = decode_procedure(raw)
    assert encode_procedure(decoded.code, decoded.prefix, decoded.newline) == raw


@pytest.mark.parametrize(
    "raw", [case[1] for case in CASES], ids=[case[0] for case in CASES]
)
def test_code_never_carries_carriage_returns(raw):
    # A stray \r reaches the lexer as trailing whitespace and makes F270 fire on
    # every line of every server process.
    assert "\r" not in decode_procedure(raw).code


def test_prefix_keeps_original_line_endings():
    decoded = decode_procedure(f"{BEGIN}\r\n{END}\r\nnValue = 1;\r\n")
    assert decoded.prefix == f"{BEGIN}\r\n{END}\r\n"
    assert decoded.newline == "\r\n"


def test_lone_carriage_returns_are_repaired_not_preserved():
    # Classic-Mac endings are the one deliberate exception to byte-exactness;
    # TM1 never emits them.
    decoded = decode_procedure("nValue = 1;\rnOther = 2;\r")
    assert decoded.code == "nValue = 1;\nnOther = 2;\n"
    assert decoded.newline == "\n"
    assert encode_procedure(decoded.code, decoded.prefix, decoded.newline) == (
        "nValue = 1;\nnOther = 2;\n"
    )


def test_form_feed_does_not_split_lines():
    # splitlines() would break on \x0c, which TM1 uses as a field separator.
    raw = f"{BEGIN}\r\n{END}\r\nsUi = 'a\x0cb';\r\n"
    decoded = decode_procedure(raw)
    assert decoded.prefix_lines == 2
    assert decoded.code == "sUi = 'a\x0cb';\n"
    assert encode_procedure(decoded.code, decoded.prefix, decoded.newline) == raw


def test_encode_without_prefix_leaves_code_alone():
    assert encode_procedure("nValue = 1;\n", "", "\r\n") == "nValue = 1;\r\n"


TM1PY_FIXTURES = sorted(
    Path(__file__).resolve().parents[1].glob("tmp/tm1py/Tests/resources/Bedrock*.json")
)


@pytest.mark.skipif(not TM1PY_FIXTURES, reason="TM1py reference checkout not present")
@pytest.mark.parametrize(
    "fixture", TM1PY_FIXTURES, ids=[path.stem for path in TM1PY_FIXTURES]
)
def test_real_server_processes_round_trip(fixture):
    """Guard the codec against procedures exported from a real TM1 server."""
    payload = json.loads(fixture.read_text())
    for section in ("Prolog", "Metadata", "Data", "Epilog"):
        raw = payload[f"{section}Procedure"]
        decoded = decode_procedure(raw)
        assert encode_procedure(decoded.code, decoded.prefix, decoded.newline) == raw
        assert "\r" not in decoded.code
        assert decoded.prefix_lines >= 2
