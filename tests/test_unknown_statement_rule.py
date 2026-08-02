from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.errors.unknown_statement_rule import UnknownStatementRule


def _lint(code: str):
    tokens = Lexer(code).tokenize()
    linter = Linter(statement_rules=[UnknownStatementRule()])
    return linter.lint(tokens)


def test_well_formed_code_reports_nothing():
    assert _lint("nValue = 1;\nsDim = 'Region';") == []


def test_unparseable_statement_is_flagged():
    issues = _lint("nValue = 1;\nfoo bar baz\nnOther = 2;")
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "E110"
    assert "could not be parsed" in issue.message
    # Located on the offending line, not the surrounding valid statements.
    assert issue.line == 2


def test_multiple_unparseable_statements_each_reported():
    issues = _lint("foo bar\nnOk = 1;\nbaz qux quux")
    assert len(issues) == 2
    assert {i.line for i in issues} == {1, 3}


def test_unparseable_statement_inside_if_body_is_flagged():
    code = "IF(1 = 1);\n  foo bar baz\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].rule_id == "E110"
    assert issues[0].line == 2


def test_error_recovery_reports_the_statement_start_not_the_tail():
    # The parser consumes tokens before failing, so an UnknownStatement must
    # carry the whole statement — otherwise E110 lands on the wrong line.
    issues = _lint("nA = 1;\nnX = Foo(d, p")
    assert len(issues) == 1
    assert issues[0].line == 2
