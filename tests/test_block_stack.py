"""Tests for block_stack tracking in LintContext."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.parser.ast import Assignment
from linti.rules.Rule import BaseStatementRule


class BlockStackTrackingRule(BaseStatementRule):
    """Test rule that tracks block_stack states."""

    RULE_ID = "TEST_BLOCK_STACK"

    def __init__(self):
        self.recorded_states = []

    def interested_in(self):
        return [Assignment]

    def visit(self, statement, context: LintContext):
        """Record the current block_stack state."""
        self.recorded_states.append(
            {
                "stack": context.block_stack.copy(),
                "in_block": context.in_control_block(),
                "block_type": context.current_block_type(),
            }
        )
        return []


def test_block_stack_tracks_if_blocks():
    """Test that block_stack correctly tracks IF blocks."""
    code = """
    x = 1;
    IF (x > 0);
        y = 2;
    ENDIF;
    z = 3;
    """

    tokens = Lexer(code).tokenize()

    rule = BlockStackTrackingRule()
    linter = Linter(statement_rules=[rule])
    linter.lint(tokens)

    # Should have 3 assignments: x=1 (outside), y=2 (inside IF), z=3 (outside)
    assert len(rule.recorded_states) == 3

    # x = 1 (outside any block)
    assert rule.recorded_states[0]["stack"] == []
    assert rule.recorded_states[0]["in_block"] is False
    assert rule.recorded_states[0]["block_type"] is None

    # y = 2 (inside IF block)
    assert rule.recorded_states[1]["stack"] == ["if"]
    assert rule.recorded_states[1]["in_block"] is True
    assert rule.recorded_states[1]["block_type"] == "if"

    # z = 3 (outside any block)
    assert rule.recorded_states[2]["stack"] == []
    assert rule.recorded_states[2]["in_block"] is False
    assert rule.recorded_states[2]["block_type"] is None


def test_block_stack_tracks_else_blocks():
    """Test that block_stack correctly tracks ELSE blocks."""
    code = """
    x = 1;
    IF (x > 0);
        y = 2;
    ELSE;
        z = 3;
    ENDIF;
    a = 4;
    """

    tokens = Lexer(code).tokenize()

    rule = BlockStackTrackingRule()
    linter = Linter(statement_rules=[rule])
    linter.lint(tokens)

    # Should have 4 assignments
    assert len(rule.recorded_states) == 4

    # x = 1 (outside)
    assert rule.recorded_states[0]["stack"] == []

    # y = 2 (inside IF)
    assert rule.recorded_states[1]["stack"] == ["if"]
    assert rule.recorded_states[1]["block_type"] == "if"

    # z = 3 (inside ELSE, still tracked as "if")
    assert rule.recorded_states[2]["stack"] == ["if"]
    assert rule.recorded_states[2]["block_type"] == "if"

    # a = 4 (outside)
    assert rule.recorded_states[3]["stack"] == []


def test_lint_context_helpers():
    """Test LintContext helper methods."""
    context = LintContext()

    # Initially empty
    assert context.in_control_block() is False
    assert context.current_block_type() is None

    # Add IF block
    context.block_stack.append("if")
    assert context.in_control_block() is True
    assert context.current_block_type() == "if"

    # Nest ELSE inside IF (shouldn't happen in practice, but tests the logic)
    context.block_stack.append("else")
    assert context.in_control_block() is True
    assert context.current_block_type() == "else"  # Returns innermost

    # Pop back to IF
    context.block_stack.pop()
    assert context.current_block_type() == "if"

    # Pop back to empty
    context.block_stack.pop()
    assert context.in_control_block() is False
    assert context.current_block_type() is None
