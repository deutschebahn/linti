"""A rule's SUPERSEDES drops another rule's finding at the same position."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.linter.linter import Linter
from linti.parser.ast import ExpressionStatement, get_node_token, iter_function_calls
from linti.rules.Rule import BaseStatementRule


class _CallRule(BaseStatementRule):
    """Report every call to *name*; no CONFIG_KEY, so it stays unregistered."""

    def __init__(self, rule_id, name):
        self._rule_id = rule_id
        self._name = name

    @property
    def RULE_ID(self):
        return self._rule_id

    def interested_in(self):
        return [ExpressionStatement]

    def visit(self, statement, context):
        issues = []
        for call in iter_function_calls(statement.expression):
            if call.name.lower() == self._name:
                token = get_node_token(call)
                issues.append(
                    LintIssue(
                        message=self._rule_id,
                        line=token.line,
                        column=token.column,
                        position=token.position,
                        rule_id=self._rule_id,
                    )
                )
        return issues


class _Concrete(_CallRule):
    SUPERSEDES = ("G100",)


def _ids(code, rules):
    issues = Linter(statement_rules=rules).lint(
        Lexer(code).tokenize(), LintContext(block="metadata")
    )
    return sorted(issue.rule_id for issue in issues)


def test_superseding_finding_replaces_the_general_one_at_the_same_call():
    rules = [_CallRule("G100", "f"), _Concrete("S100", "f")]
    assert _ids("f();", rules) == ["S100"]


def test_other_positions_are_untouched():
    rules = [_CallRule("G100", "f"), _Concrete("S100", "g")]
    assert _ids("f(); g();", rules) == ["G100", "S100"]


def test_suppressed_superseding_finding_lets_the_general_one_through():
    rules = [_CallRule("G100", "f"), _Concrete("S100", "f")]
    assert _ids("# noqa: S100\nf();", rules) == ["G100"]
    assert _ids("# noqa: G100\nf();", rules) == ["S100"]
