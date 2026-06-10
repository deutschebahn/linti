from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.constant_rule import ConstantAssignmentRule
from linti.rules.naming.naming_rule import VariablePrefixRule


def _lint(code: str, statement_rules):
    tokens = Lexer(code).tokenize()
    linter = Linter(statement_rules=statement_rules)
    return linter.lint(tokens)


def test_constant_prefix_allowed_for_number_and_string():
    code = "cNum = 1; cStr = 'a';"
    issues = _lint(
        code,
        [VariablePrefixRule(allow_constant_prefix=True)],
    )
    assert issues == []


def test_constant_prefix_rejected_when_disabled():
    code = "cNum = 1; cStr = 'a';"
    issues = _lint(
        code,
        [VariablePrefixRule(allow_constant_prefix=False)],
    )
    assert len(issues) == 2


def test_constant_reassignment_reports_issue():
    code = "cVal = 1; cVal = 2;"
    issues = _lint(
        code,
        [ConstantAssignmentRule()],
    )
    assert len(issues) == 1
    assert "assigned only once" in issues[0].message
