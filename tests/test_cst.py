"""Tests for the concrete syntax tree.

The CST's whole value is that it is *lossless*: every token falls inside
exactly one node and any subtree renders back to its exact source text.  Those
two invariants are what the layout rules and the reflow fixer stand on, so most
of this file checks them structurally across a corpus rather than asserting on
one hand-picked tree.
"""

from pathlib import Path

import pytest

from linti.cst.node import CstKind, CstNode
from linti.lexer.lexer import Lexer
from linti.parser.parser import Parser

#: Sources spanning every construct the parser builds a node for, plus the
#: shapes that historically lose information: desugared ELSEIF, dropped
#: grouping parens, discarded commas, and unparseable statements.
CORPUS = {
    "empty": "",
    "assignment": "nA = 1;\n",
    "call": "sX = CellGetS( 'Cube', 'E1', 'E2' );\n",
    "empty_call": "ProcessBreak();\n",
    "bare_call": "ProcessBreak;\n",
    "nested_call": "sX = Outer( Inner( 'a', 'b' ), 'c' );\n",
    "if_else": "IF( nA = 1 );\n    nB = 2;\nELSE;\n    nB = 3;\nENDIF;\n",
    "elseif": "IF( nA = 1 );\n  nB=1;\nELSEIF( nA = 2 );\n  nB=2;\nELSE;\n  nB=3;\nENDIF;\n",
    "while": "WHILE( nA < 10 );\n    nA = nA + 1;\nEND;\n",
    "grouping_parens": "nX = (1 + 2) * 3;\n",
    "unary": "nX = -1;\nnY = ~nA;\n",
    "element_ref": "sX = CellGetS( 'Cube', pHier:vEle, 'E2' );\n",
    "quoted_string": "sX = 'it''s';\n",
    "comments": "# lead\nnA = 1;  # trail\n\n# tail\n",
    "broken_statement": "nA = ;\nnB = 2;\n",
    "broken_inside_if": "IF( nA = 1 );\n  garbage %% ;\nENDIF;\n",
    "empty_block": "IF( nA = 1 );\nENDIF;\n",
    "multiline_call": "sX = CellGetS(\n    'Cube',\n    'E1'\n);\n",
    "trailing_blank_lines": "nA = 1;   \n\n",
    "no_trailing_newline": "nA = 1;",
}


def _parse(source):
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    return program, tokens


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", CORPUS.values(), ids=list(CORPUS))
def test_root_spans_the_entire_token_stream(source):
    """Leading and trailing trivia must be inside the tree, not beside it."""
    program, tokens = _parse(source)

    assert (program.cst.start, program.cst.end) == (0, len(tokens))


@pytest.mark.parametrize("source", CORPUS.values(), ids=list(CORPUS))
def test_every_token_resolves_to_a_node(source):
    program, tokens = _parse(source)

    for index in range(len(tokens)):
        assert program.cst.covering_node(index) is not None


@pytest.mark.parametrize("source", CORPUS.values(), ids=list(CORPUS))
def test_children_are_ordered_non_overlapping_and_contained(source):
    program, _ = _parse(source)

    for node in program.cst.walk():
        boundary = node.start
        for child in node.children:
            assert child.start >= boundary, f"{child.kind} overlaps its left sibling"
            assert child.end <= node.end, f"{child.kind} escapes {node.kind}"
            assert child.parent is node
            boundary = child.end


@pytest.mark.parametrize("source", CORPUS.values(), ids=list(CORPUS))
def test_node_text_is_the_exact_source_slice(source):
    program, tokens = _parse(source)

    assert program.cst.text(source, tokens) == source
    for node in program.cst.walk():
        span = node.span(tokens)
        if span is not None:
            assert node.text(source, tokens) == source[span[0] : span[1]]


def test_node_text_survives_quote_escaping():
    """Rendering must slice source, not join token values."""
    source = "sX = 'it''s';\n"
    program, tokens = _parse(source)

    string_node = next(n for n in program.cst.walk() if n.kind is CstKind.STRING)
    assert string_node.text(source, tokens) == "'it''s'"


# ---------------------------------------------------------------------------
# What the AST drops but the CST keeps
# ---------------------------------------------------------------------------


def test_argument_list_keeps_parens_and_commas():
    source = "sX = CellGetS( 'Cube', 'E1' );\n"
    program, tokens = _parse(source)

    arg_list = next(n for n in program.cst.walk() if n.kind is CstKind.ARG_LIST)
    assert arg_list.text(source, tokens) == "( 'Cube', 'E1' )"

    arguments = [n for n in arg_list.walk() if n.kind is CstKind.ARGUMENT]
    assert [a.text(source, tokens) for a in arguments] == ["'Cube'", "'E1'"]


def test_grouping_parens_survive_as_a_paren_group():
    """The AST returns the inner expression; the CST still shows the parens."""
    source = "nX = (1 + 2) * 3;\n"
    program, tokens = _parse(source)

    group = next(n for n in program.cst.walk() if n.kind is CstKind.PAREN_GROUP)
    assert group.text(source, tokens) == "(1 + 2)"


def test_elseif_is_a_clause_in_the_cst_though_the_ast_nests_it():
    source = "IF( nA = 1 );\n  nB=1;\nELSEIF( nA = 2 );\n  nB=2;\nENDIF;\n"
    program, tokens = _parse(source)

    # AST: a nested IfStatement inside else_body.
    outer_if = program.statements[0]
    assert type(outer_if.else_body[0]).__name__ == "IfStatement"

    # CST: an ELSEIF_CLAUSE, the construct actually written.
    clause = next(n for n in program.cst.walk() if n.kind is CstKind.ELSEIF_CLAUSE)
    assert clause.text(source, tokens).startswith("ELSEIF( nA = 2 );")


def test_else_clause_is_its_own_node():
    source = "IF( nA = 1 );\n  nB=1;\nELSE;\n  nB=2;\nENDIF;\n"
    program, tokens = _parse(source)

    clause = next(n for n in program.cst.walk() if n.kind is CstKind.ELSE_CLAUSE)
    assert clause.text(source, tokens) == "ELSE;\n  nB=2;"


def test_headers_cover_the_condition_and_its_semicolon():
    source = "WHILE( nA < 10 );\n  nA = nA + 1;\nEND;\n"
    program, tokens = _parse(source)

    header = next(n for n in program.cst.walk() if n.kind is CstKind.WHILE_HEADER)
    assert header.text(source, tokens) == "WHILE( nA < 10 );"


def test_element_reference_is_its_own_node():
    source = "sX = CellGetS( 'Cube', pHier:vEle );\n"
    program, tokens = _parse(source)

    ref = next(n for n in program.cst.walk() if n.kind is CstKind.ELEMENT_REF)
    assert ref.text(source, tokens) == "pHier:vEle"


# ---------------------------------------------------------------------------
# AST <-> CST wiring
# ---------------------------------------------------------------------------


def test_ast_nodes_carry_a_cst_back_pointer():
    source = "IF( nA = 1 );\n    sX = CellGetS( 'Cube' );\nENDIF;\n"
    program, tokens = _parse(source)

    if_statement = program.statements[0]
    assert if_statement.cst.kind is CstKind.IF_STATEMENT

    assignment = if_statement.then_body[0]
    assert assignment.cst.kind is CstKind.ASSIGNMENT
    assert assignment.cst.text(source, tokens) == "sX = CellGetS( 'Cube' );"

    assert assignment.right.cst.kind is CstKind.CALL
    assert assignment.left.cst.kind is CstKind.IDENTIFIER


def test_ast_nodes_default_to_no_cst_when_built_by_hand():
    from linti.parser.ast import Identifier

    assert Identifier("nA").cst is None


def test_desugared_bare_call_keeps_the_identifier_span():
    """`ProcessBreak;` has no parens, so its call node is the identifier."""
    source = "ProcessBreak;\n"
    program, tokens = _parse(source)

    call = program.statements[0].expression
    assert call.cst.text(source, tokens) == "ProcessBreak"


# ---------------------------------------------------------------------------
# Resilience — parity with tests/test_resilient.py
# ---------------------------------------------------------------------------


def test_unparseable_statement_still_yields_a_covering_node():
    source = "nA = ;\nnB = 2;\n"
    program, tokens = _parse(source)

    unknown = next(n for n in program.cst.walk() if n.kind is CstKind.UNKNOWN_STATEMENT)
    assert unknown.text(source, tokens) == "nA = ;"
    # The failed parse leaves no half-built children behind.
    assert unknown.children == []


def test_broken_statement_does_not_break_the_surrounding_tree():
    source = "IF( nA = 1 );\n  garbage %% ;\n  nB = 2;\nENDIF;\n"
    program, tokens = _parse(source)

    assert (program.cst.start, program.cst.end) == (0, len(tokens))
    assert any(n.kind is CstKind.IF_STATEMENT for n in program.cst.walk())
    assert any(n.kind is CstKind.UNKNOWN_STATEMENT for n in program.cst.walk())


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------


def test_covering_node_returns_the_innermost_node():
    source = "sX = CellGetS( 'Cube' );\n"
    program, tokens = _parse(source)

    cube_index = next(i for i, t in enumerate(tokens) if t.value == "Cube")
    assert program.cst.covering_node(cube_index).kind is CstKind.STRING


def test_covering_node_resolves_trivia_to_its_enclosing_node():
    """No child claims whitespace, so it belongs to the node around it."""
    source = "sX = CellGetS( 'Cube' );\n"
    program, tokens = _parse(source)

    # The space between '(' and 'Cube' sits inside the argument list.
    space_index = next(
        i for i, t in enumerate(tokens) if t.value == " " and tokens[i - 1].value == "("
    )
    assert program.cst.covering_node(space_index).kind is CstKind.ARG_LIST


def test_covering_node_returns_none_outside_the_span():
    node = CstNode(CstKind.PROGRAM, 0, 3, [])

    assert node.covering_node(5) is None


def test_enclosing_statement_walks_up_to_the_statement():
    source = "sX = CellGetS( 'Cube' );\n"
    program, tokens = _parse(source)

    cube_index = next(i for i, t in enumerate(tokens) if t.value == "Cube")
    string_node = program.cst.covering_node(cube_index)

    assert string_node.enclosing_statement().kind is CstKind.ASSIGNMENT


def test_significant_token_helpers_skip_trivia():
    source = "IF( nA = 1 );\n    nB = 2;\nENDIF;\n"
    program, tokens = _parse(source)

    if_node = program.statements[0].cst
    assert if_node.first_significant(tokens).value == "IF"
    assert if_node.last_significant(tokens).value == ";"
    assert all(
        t.type.name not in ("WHITESPACE", "NEWLINE", "COMMENT")
        for t in if_node.significant_tokens(tokens)
    )


def test_empty_node_has_no_span_and_renders_as_nothing():
    node = CstNode(CstKind.BLOCK, 4, 4, [])

    assert node.span([]) is None
    assert node.text("nA = 1;", []) == ""


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def test_example_files_produce_a_lossless_tree():
    example_dir = Path(__file__).resolve().parent.parent / "example"
    paths = sorted(example_dir.glob("*.ti"))
    assert paths, "expected .ti files in example/ to parse against"

    for path in paths:
        source = path.read_text()
        program, tokens = _parse(source)
        assert program.cst.text(source, tokens) == source, path.name
