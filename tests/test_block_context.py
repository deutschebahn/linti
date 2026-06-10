"""Tests for block context awareness in linting."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.parser.ast import Assignment
from linti.rules.Rule import BaseStatementRule


class BlockAwareTestRule(BaseStatementRule):
    """Test rule that tracks which blocks it visits."""

    @property
    def RULE_ID(self) -> str:
        return "TEST001"

    def __init__(self):
        self.visited_blocks = []

    def interested_in(self):
        return [Assignment]

    def visit(self, statement, context: LintContext):
        self.visited_blocks.append(context.block if context else None)
        return []


def test_linter_passes_block_context_to_rules():
    """Test that block context is passed to rules."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = BlockAwareTestRule()
    linter = Linter(statement_rules=[rule])

    # Lint without block context
    linter.lint(tokens, None)
    assert rule.visited_blocks[-1] is None

    # Lint with block context
    rule.visited_blocks = []
    linter.lint(tokens, LintContext(block="prolog"))
    assert rule.visited_blocks[-1] == "prolog"

    # Lint with different block context
    rule.visited_blocks = []
    linter.lint(tokens, LintContext(block="epilog"))
    assert rule.visited_blocks[-1] == "epilog"


def test_linter_passes_block_to_multiple_statements():
    """Test that block context is passed to all statements."""
    code = """
    nValue1 = 5;
    nValue2 = 10;
    nValue3 = 15;
    """
    tokens = Lexer(code).tokenize()

    rule = BlockAwareTestRule()
    linter = Linter(statement_rules=[rule])

    linter.lint(tokens, LintContext(block="metadata"))

    # Should have visited 3 assignments, all with "metadata" block
    assert len(rule.visited_blocks) == 3
    assert all(block == "metadata" for block in rule.visited_blocks)


def test_linter_without_block_context_passes_none():
    """Test backward compatibility - linter works without block context."""
    code = "nValue = 5;"
    tokens = Lexer(code).tokenize()

    rule = BlockAwareTestRule()
    linter = Linter(statement_rules=[rule])

    # Lint without specifying block (backward compatible)
    linter.lint(tokens)

    assert len(rule.visited_blocks) == 1
    assert rule.visited_blocks[0] is None
