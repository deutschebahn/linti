"""C154: data source variables assigned after the data source was opened."""

import pytest

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Severity
from linti.linter.linter import Linter
from linti.rules.semantic.data_source_assigned_after_prolog_rule import (
    DataSourceAssignedAfterPrologRule,
)


def _lint(code, block):
    linter = Linter(statement_rules=[DataSourceAssignedAfterPrologRule()])
    return linter.lint(Lexer(code).tokenize(), LintContext(block=block))


@pytest.mark.parametrize("block", ["metadata", "data", "epilog"])
def test_assignment_after_prolog_is_an_error(block):
    (issue,) = _lint("n = 1;\nDatasourceQuery = 'SELECT 1';", block)
    assert issue.rule_id == "C154"
    assert issue.severity is Severity.ERROR
    assert (issue.line, issue.column) == (2, 1)
    assert issue.message == (
        f"DatasourceQuery is assigned in {block.title()}, but the data source is "
        "opened when the Prolog ends, so this does not change it. Assign it in "
        "the Prolog."
    )


def test_prolog_assignment_is_fine():
    assert _lint("DatasourceQuery = 'SELECT 1';", "prolog") == []


@pytest.mark.parametrize(
    "name",
    [
        "DATASOURCETYPE",
        "datasourcenameforserver",
        "DatasourceNameForClient",
        "DatasourceCubeview",
        "DatasourceDimensionSubset",
        "DatasourceUsername",
        "DatasourcePassword",
        "DatasourceJsonRootPointer",
    ],
)
def test_every_data_source_variable_counts(name):
    assert len(_lint(f"{name} = 'x';", "data")) == 1


def test_nested_assignment_is_found():
    code = "IF(n = 1);\n  WHILE(i < 2);\n    DatasourceType = 'NULL';\n  END;\nENDIF;"
    assert [issue.line for issue in _lint(code, "metadata")] == [3]


@pytest.mark.parametrize(
    "code",
    [
        "IF(DatasourceType @= 'ODBC'); n = 1; ENDIF;",
        "sName = DatasourceNameForServer;",
        "DatasourceQueryText = 'x';",
        "vDatasource = 'x';",
    ],
)
def test_reads_and_other_names_are_fine(code):
    assert _lint(code, "data") == []


@pytest.mark.parametrize("block", ["metadata", "data", "epilog"])
@pytest.mark.parametrize(
    "name",
    [
        "DatasourceASCIIDelimiter",
        "DatasourceAsciiQuoteCharacter",
        "DATASOURCEASCIIDECIMALSEPARATOR",
        "DatasourceASCIIThousandSeparator",
        "DatasourceASCIIHeaderRecords",
    ],
)
def test_ascii_settings_are_not_reported(name, block):
    # ASCIIOutput/TextOutput also read these, so late assignments are legitimate.
    assert _lint(f"{name} = '';\nTextOutput('out.csv', 'a');", block) == []


def test_unknown_section_is_ignored():
    assert _lint("DatasourceQuery = 'x';", None) == []
