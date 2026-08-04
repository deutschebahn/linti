"""End-to-end safety net for the formatting rules as a group.

Individual rule tests check that each rule does its own job.  These check the
properties that only hold when all of them run together, which is how users
actually run them:

* auto-fix converges — a second pass changes nothing;
* the fixed output lints clean, so no pair of rules can quietly fight;
* nothing but layout changes — the token stream survives.

The last one is the real guard.  F330 rewrites code rather than whitespace, so
a bug there could silently drop an argument; comparing token streams catches
that where comparing text never would.
"""

from pathlib import Path

import pytest

from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.rule_factory import create_rules

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example"

#: Sources chosen for the ways they stress the layout rules against each other:
#: mangled spacing, hand-wrapped calls, deep nesting, and the constructs the
#: fixer must refuse to touch.
CORPUS = {
    "clean": "nA = 1;\nnB = 2;\n",
    "mangled_spacing": "iF(a=1);\nsX=CellGetS('Cube','E1','E2');\nendif;\n",
    "hand_aligned_call": (
        "IF( nA = 1 );\n"
        "    sValue = CellGetS( 'Cube',\n"
        "                       'Elem' );\n"
        "ENDIF;\n"
    ),
    "canonical_wrapped": ("sValue = CellGetS(\n    'Cube',\n    'Elem'\n);\n"),
    "over_wrapped": (
        "sValue = CellGetS(\n"
        "              'Cube',\n"
        "                    'Elem'\n"
        "                );\n"
    ),
    "long_call": "sValue = CellGetS( 'Cube', 'AAAA', 'BBBB', 'CCCC', 'DDDD' );\n",
    "long_condition": (
        "IF( nA = 1 & nB = 2 & nC = 3 & nD = 4 & nE = 5 );\n    nX = 1;\nENDIF;\n"
    ),
    "nested_calls": (
        "IF( a );\n    sX = Outer( Inner( 'aaaa', 'bbbb' ), 'cccc', 'dddd' );\nENDIF;\n"
    ),
    "elseif_chain": (
        "IF( a = 1 );\n"
        "    nX = 1;\n"
        "ELSEIF( a = 2 );\n"
        "    nX = 2;\n"
        "ELSE;\n"
        "    nX = 3;\n"
        "ENDIF;\n"
    ),
    "while_loop": "WHILE( nA < 10 );\n    nA = nA + 1;\nEND;\n",
    "deep_nesting": (
        "IF( a );\nIF( b );\nWHILE( c );\nnX = 1;\nEND;\nENDIF;\nENDIF;\n"
    ),
    "comments": "# header\nnA = 1;  # trailing\n\n# footer\n",
    "multiline_string": "sM = 'line1\nline2';\nnA = 1;\n",
    "quoted_string": "sX = Concat( 'it''s', 'a  b' );\n",
    "element_reference": "sX = CellGetS( 'Cube', pHier:vEle, 'E2' );\n",
    "operator_chain": "sX = 'aaaaaaaaaa' | 'bbbbbbbbbb' | 'cccccccccc';\n",
    "broken_statement": "nA = ;\nnB = 2;\n",
    "blank_lines": "nA = 1;\n\n\nnB = 2;\n",
    "no_trailing_newline": "IF( a );\nnX = 1;\nENDIF;",
}


def _format_linter(limit: int = 40) -> Linter:
    cfg = Config()
    cfg.rules.max_line_length.limit = limit
    return Linter(*create_rules(cfg, select="F"))


def _significant_tokens(source: str):
    """The token stream with layout removed — what the code actually says.

    Casing is normalised for everything but literals, because recasing
    keywords (F110) and identifiers (N120) is a change these rules are
    supposed to make.  A literal that changed case would be a real defect.
    """
    return [
        (
            token.type,
            token.value
            if token.type.name in ("STRING", "NUMBER")
            else token.value.upper(),
        )
        for token in Lexer(source).tokenize()
        if token.type.name not in ("WHITESPACE", "NEWLINE")
    ]


def _sources():
    yield from CORPUS.items()
    for path in sorted(EXAMPLE_DIR.glob("*.ti")):
        yield f"example/{path.name}", path.read_text()


ALL_SOURCES = list(_sources())
ALL_IDS = [name for name, _ in ALL_SOURCES]


@pytest.mark.parametrize("source", [s for _, s in ALL_SOURCES], ids=ALL_IDS)
def test_auto_fix_converges(source):
    linter = _format_linter()
    once, _ = apply_fixes_iteratively(source, linter)
    twice, count = apply_fixes_iteratively(once, linter)

    assert twice == once
    assert count == 0


@pytest.mark.parametrize("source", [s for _, s in ALL_SOURCES], ids=ALL_IDS)
def test_fixed_output_lints_clean(source):
    """Whatever auto-fix leaves behind must have no fixable issue left."""
    linter = _format_linter()
    fixed, _ = apply_fixes_iteratively(source, linter)

    remaining = [
        issue
        for issue in linter.lint(Lexer(fixed).tokenize(), source=fixed)
        if issue.fix is not None
    ]
    assert remaining == [], [(i.rule_id, i.message) for i in remaining]


@pytest.mark.parametrize("source", [s for _, s in ALL_SOURCES], ids=ALL_IDS)
def test_auto_fix_only_changes_layout(source):
    """Formatting may move code around; it may never change what it says."""
    fixed, _ = apply_fixes_iteratively(source, _format_linter())

    assert _significant_tokens(fixed) == _significant_tokens(source)


@pytest.mark.parametrize("source", [s for _, s in ALL_SOURCES], ids=ALL_IDS)
def test_fixed_output_still_lexes_losslessly(source):
    fixed, _ = apply_fixes_iteratively(source, _format_linter())
    tokens = Lexer(fixed).tokenize()

    assert "".join(t.raw_text(fixed) for t in tokens) == fixed


@pytest.mark.parametrize("source", [s for _, s in ALL_SOURCES], ids=ALL_IDS)
def test_every_rule_group_converges_together(source):
    """Not just the F rules — the whole default rule set."""
    linter = Linter(*create_rules(Config()))
    once, _ = apply_fixes_iteratively(source, linter)
    twice, _ = apply_fixes_iteratively(once, linter)

    assert twice == once
    assert _significant_tokens(once) == _significant_tokens(source)
