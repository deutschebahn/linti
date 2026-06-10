from linti.lexer.lexer import Lexer
from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.Rule import BaseRule


class _CountingRule(BaseRule):
    @property
    def RULE_ID(self) -> str:
        return "TEST"

    def __init__(self, interested):
        self._interested = list(interested)
        self.visited = []

    def interested_in(self):
        return self._interested

    def visit(self, token, window, context: LintContext):
        self.visited.append((token.type, token.position))
        return []


def test_linter_dispatches_only_to_interested_rules():
    tokens = Lexer("a = 1;").tokenize()

    equals_rule = _CountingRule([TokenType.EQUALS])
    semi_rule = _CountingRule([TokenType.SEMICOLON])

    linter = Linter([equals_rule, semi_rule])
    issues = linter.lint(tokens)

    assert issues == []
    assert equals_rule.visited == [(TokenType.EQUALS, 2)]
    assert semi_rule.visited == [(TokenType.SEMICOLON, 5)]
