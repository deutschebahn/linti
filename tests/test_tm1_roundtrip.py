"""End-to-end auto-fix against a TM1 server.

The case that matters: a server process uses CRLF, so every line looks like it
has trailing whitespace. If the carriage returns reached the lexer, F270 would
fire on every line, --auto-fix would strip them, the write-back would restore
them, and the next run would report the same issues again — forever.
"""

from tm1_fakes import (
    BEGIN_GENERATED_STATEMENTS,
    END_GENERATED_STATEMENTS,
    FakeProcess,
    FakeTM1,
)

from linti.config import Config
from linti.linter.api import lint_all, lint_process
from linti.linter.linter import Linter
from linti.provider.tm1 import TM1Provider
from linti.rules.rule_factory import create_rules

# Lowercase keywords, tight parentheses and no indentation give the auto-fixer
# real work (F110, F250, F310).
CRLF_PROLOG = "\r\nif(nValue = 1);\r\nnOther = 2;\r\nendif;\r\n"
CRLF_PROLOG_FIXED = "\r\nIF( nValue = 1 );\r\n    nOther = 2;\r\nENDIF;\r\n"


def new_linter():
    cfg = Config()
    token_rules, statement_rules = create_rules(cfg)
    return Linter(
        rules=token_rules,
        statement_rules=statement_rules,
        max_nesting_depth=cfg.max_nesting_depth,
        max_file_size=cfg.max_file_size,
        max_values_per_variable=cfg.max_values_per_variable,
    )


def test_crlf_does_not_produce_trailing_whitespace_issues():
    tm1 = FakeTM1(FakeProcess("MyProcess", prolog_procedure=CRLF_PROLOG))
    issues = lint_process(TM1Provider(tm1), "MyProcess", new_linter())["MyProcess"]
    assert not [issue for _, issue, _ in issues if issue.rule_id == "F270"]


def test_auto_fix_writes_back_with_line_endings_and_prefix_intact():
    process = FakeProcess("MyProcess", prolog_procedure=CRLF_PROLOG)
    original = process.prolog_procedure
    tm1 = FakeTM1(process)
    provider = TM1Provider(tm1)

    lint_process(provider, "MyProcess", new_linter(), auto_fix=True)

    assert len(tm1.processes.updated) == 1
    written = tm1.processes.updated[0].prolog_procedure

    prefix = f"{BEGIN_GENERATED_STATEMENTS}\r\n{END_GENERATED_STATEMENTS}\r\n"
    # The generated block came back byte for byte...
    assert original.startswith(prefix)
    assert written.startswith(prefix)
    # ...server line endings were restored, with no bare LF smuggled in...
    assert "\n" not in written.replace("\r\n", "")
    # ...and nothing beyond the fixes changed.
    assert written == prefix + CRLF_PROLOG_FIXED


def test_clean_process_is_never_written():
    process = FakeProcess("MyProcess", prolog_procedure=CRLF_PROLOG_FIXED)
    tm1 = FakeTM1(process)
    lint_process(TM1Provider(tm1), "MyProcess", new_linter(), auto_fix=True)
    assert tm1.processes.updated == []


def test_auto_fix_is_idempotent():
    process = FakeProcess("MyProcess", prolog_procedure=CRLF_PROLOG)
    tm1 = FakeTM1(process)
    provider = TM1Provider(tm1)

    lint_process(provider, "MyProcess", new_linter(), auto_fix=True)
    assert len(tm1.processes.updated) == 1

    # A second run has nothing left to do and must not touch the server again.
    lint_process(provider, "MyProcess", new_linter(), auto_fix=True)
    assert len(tm1.processes.updated) == 1


def test_lint_all_covers_every_process():
    tm1 = FakeTM1(
        FakeProcess("Alpha", prolog_procedure=CRLF_PROLOG),
        FakeProcess("Beta", prolog_procedure=CRLF_PROLOG),
        FakeProcess("}Control", prolog_procedure=CRLF_PROLOG),
    )
    results = lint_all(TM1Provider(tm1), new_linter())

    assert sorted(results) == ["Alpha", "Beta"]
    for issues in results.values():
        assert any(issue.rule_id == "F110" for _, issue, _ in issues)


def test_reported_lines_point_at_the_stored_procedure():
    process = FakeProcess("MyProcess", prolog_procedure=CRLF_PROLOG)
    tm1 = FakeTM1(process)
    issues = lint_process(TM1Provider(tm1), "MyProcess", new_linter())["MyProcess"]

    stored = process.prolog_procedure.replace("\r\n", "\n").split("\n")
    expected_line = stored.index("if(nValue = 1);") + 1

    keyword_issues = [
        (issue, source_line)
        for _, issue, source_line in issues
        if issue.rule_id == "F110"
    ]
    assert keyword_issues
    issue, source_line = keyword_issues[0]
    assert source_line + issue.line - 1 == expected_line
