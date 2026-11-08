"""C153: effective data source vs. executable Metadata/Data code."""

import pytest

from linti.cli.file_linter import linter_from_config
from linti.config import Config
from linti.linter.api import lint_process_model
from linti.linter.lint_issue import Severity
from linti.linter.parse_cache import SectionParseCache
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.semantic.constant_evaluation import ConstantEvaluationIndex
from linti.semantic.process_facts import DataSourceState, ProcessFacts

SKIPPED = "will be skipped because the effective data source is None."
UNUSED = (
    "A data source is configured, but neither Metadata nor Data contains "
    "executable statements."
)


RUNTIME = (
    "DatasourceType turns on a data source at run time, but the process is "
    "saved without one and declares no variables, so Metadata and Data cannot "
    "read the record columns. Save the process with its data source and "
    "variables."
)


def _process(
    source, prolog="", metadata="", data="", epilog="", parameters=(), variables=()
):
    return ProcessIR(
        name="p",
        prolog=ProcedureInfo(code=prolog),
        metadata=ProcedureInfo(code=metadata),
        data=ProcedureInfo(code=data),
        epilog=ProcedureInfo(code=epilog),
        datasource_type=source,
        parameters=list(parameters),
        variables=list(variables),
    )


def _findings(process, config=None):
    linter = linter_from_config(Config(rules=config or {}), select="C153")
    return [(proc, issue) for proc, issue, _ in lint_process_model(process, linter)]


def _messages(process, config=None):
    return [issue.message for _, issue in _findings(process, config)]


# -- the four combinations ---------------------------------------------------


def test_source_and_code_is_fine():
    assert _messages(_process("ASCII", data="n = n + 1;")) == []


def test_no_source_and_no_code_is_fine():
    assert _messages(_process("None", prolog="ExecuteProcess('x');")) == []


def test_no_source_with_code_in_both_sections():
    findings = _findings(
        _process("None", metadata="\n\nn = 1;", data="AsciiOutput(f, v);")
    )
    assert len(findings) == 1
    proc, issue = findings[0]
    assert proc == "metadata"
    assert (issue.line, issue.column) == (3, 1)
    assert issue.message == f"Metadata and Data {SKIPPED}"
    assert issue.severity is Severity.WARNING


def test_no_source_with_code_only_in_data():
    findings = _findings(_process("None", data="# comment\n  IF(1 = 1); ENDIF;"))
    assert [(proc, issue.message, issue.line) for proc, issue in findings] == [
        ("data", f"Data {SKIPPED}", 2)
    ]


def test_source_without_code_is_unused():
    findings = _findings(_process("ASCII", prolog="n = 1;", epilog="n = 2;"))
    assert [(proc, issue.message, issue.line) for proc, issue in findings] == [
        ("prolog", UNUSED, 1)
    ]


# -- Prolog overrides ----------------------------------------------------------


def test_prolog_sets_up_a_source_for_the_code():
    prolog = "DatasourceType = 'CHARACTERDELIMITED';\nDatasourceNameForServer = f;"
    process = _process("None", prolog=prolog, data="n = 1;", variables=["v1"])
    assert _messages(process) == []


# -- data source turned on in Prolog without variables ----------------------


def test_runtime_source_without_variables_is_reported_at_the_assignment():
    prolog = "n = 1;\nDatasourceType = 'CHARACTERDELIMITED';"
    findings = _findings(_process("None", prolog=prolog, data="n = n + 1;"))
    assert [(proc, issue.line) for proc, issue in findings] == [("prolog", 2)]
    assert findings[0][1].message == RUNTIME


@pytest.mark.parametrize(
    "source,variables",
    [
        # Saved with a data source: Prolog only switches it.
        ("ASCII", ()),
        # Saved without one, but with variables to read the columns into.
        ("None", ("v1",)),
        # No process properties at all (plain .ti): nothing is known.
        (None, ()),
    ],
)
def test_runtime_source_needs_a_sourceless_saved_definition(source, variables):
    prolog = "DatasourceType = 'CHARACTERDELIMITED';"
    process = _process(source, prolog=prolog, data="n = 1;", variables=variables)
    assert RUNTIME not in _messages(process)


def test_runtime_source_without_code_is_only_unused():
    prolog = "DatasourceType = 'VIEW';"
    assert _messages(_process("None", prolog=prolog)) == [UNUSED]


def test_check_runtime_source_false_drops_only_that_finding():
    config = {"data_source_usage": {"check_runtime_source": False}}
    prolog = "DatasourceType = 'CHARACTERDELIMITED';"
    process = _process("None", prolog=prolog, data="n = 1;")
    assert _messages(process, config) == []


def test_prolog_set_up_source_without_code_is_unused_and_located():
    prolog = "n = 1;\nDatasourceType = 'VIEW';"
    findings = _findings(_process("None", prolog=prolog))
    assert [(proc, issue.line) for proc, issue in findings] == [("prolog", 2)]
    assert findings[0][1].message == UNUSED


def test_prolog_removes_the_source_before_the_code():
    prolog = "DataSourceType = 'NULL';"
    assert _messages(_process("ASCII", prolog=prolog, data="n = 1;")) == [
        f"Data {SKIPPED}"
    ]


# -- unknown states stay silent ------------------------------------------------


@pytest.mark.parametrize(
    "prolog",
    [
        "DatasourceType = pType;",
        "IF(pMode = 1);\n  DatasourceType = 'NULL';\nENDIF;",
        "IF(pMode = 1);\n  DatasourceType = 'NULL';\nELSE;\n  DatasourceType = 'ASCII';\nENDIF;",
    ],
)
def test_dynamic_prolog_override_is_unknown(prolog):
    process = _process("ASCII", prolog=prolog, parameters=["pType", "pMode"])
    assert _messages(process) == []
    process = _process("ASCII", prolog=prolog, data="n = 1;", parameters=["pType"])
    assert _messages(process) == []


def test_format_without_data_source_metadata_is_unknown():
    assert _messages(_process(None, data="n = 1;")) == []
    assert _messages(_process(None, prolog="n = 1;")) == []


# -- what counts as empty -----------------------------------------------------


def test_comments_and_section_markers_are_empty():
    generated = (
        "#****Begin: Generated Statements***\n"
        "#****End: Generated Statements****\n\n"
        "# nothing to do\n"
    )
    process = _process("ASCII", prolog="n = 1;", metadata=generated, data=generated)
    assert _messages(process) == [UNUSED]
    process = _process("None", metadata=generated, data=generated)
    assert _messages(process) == []


def test_generated_statements_count_as_code():
    data = (
        "#****Begin: Generated Statements***\n"
        "CellPutN(vValue, 'Sales', vRegion, vMonth);\n"
        "#****End: Generated Statements****"
    )
    assert _messages(_process("None", data=data)) == [f"Data {SKIPPED}"]


@pytest.mark.parametrize(
    "call",
    [
        "ReturnSQLTableHandle;",
        "ReturnViewHandle('Sales', 'Drill');",
        "ReturnCSVTableHandle;",
    ],
)
def test_drillthrough_use_counts_as_use(call):
    assert _messages(_process("ODBC", epilog=call)) == []


def test_unused_source_without_prolog_is_reported_at_the_first_section():
    process = ProcessIR(
        name="p", epilog=ProcedureInfo(code="n = 1;"), datasource_type="ASCII"
    )
    assert [proc for proc, _ in _findings(process)] == ["epilog"]


# -- configuration and suppression ---------------------------------------------


def test_check_unused_source_false_drops_only_that_finding():
    config = {"data_source_usage": {"check_unused_source": False}}
    assert _messages(_process("ASCII", prolog="n = 1;"), config) == []
    assert _messages(_process("None", data="n = 1;"), config) == [f"Data {SKIPPED}"]


def test_noqa_suppresses_the_finding():
    assert _messages(_process("None", data="# noqa: C153\nn = 1;")) == []


def test_select_c15_includes_the_rule():
    linter = linter_from_config(Config(), select="C15")
    issues = lint_process_model(_process("None", data="n = 1;"), linter)
    assert [issue.rule_id for _, issue, _ in issues] == ["C153"]


# -- ProcessFacts ----------------------------------------------------------------


def _facts(process):
    cache = SectionParseCache(process)
    return ProcessFacts(process, cache, ConstantEvaluationIndex(process, cache=cache))


@pytest.mark.parametrize(
    "stored,prolog,expected",
    [
        ("None", "", DataSourceState.NONE),
        ("ASCII", "", DataSourceState.PRESENT),
        (None, "", DataSourceState.UNKNOWN),
        ("ASCII", "DatasourceType = 'NULL';", DataSourceState.NONE),
        ("None", "DatasourceType = 'ODBC';", DataSourceState.PRESENT),
        ("None", "DatasourceType = pType;", DataSourceState.UNKNOWN),
    ],
)
def test_effective_data_source(stored, prolog, expected):
    process = _process(stored, prolog=prolog, parameters=["pType"])
    assert _facts(process).effective_data_source is expected


def test_absent_sections_have_no_code():
    process = ProcessIR(name="p", data=ProcedureInfo(code="n = 1;"))
    facts = _facts(process)
    assert facts.present_sections() == ["data"]
    assert not facts.has_code("metadata")
    assert facts.has_code("data")


# -- review regressions -------------------------------------------------------


def test_unparseable_prolog_statement_mentioning_the_source_is_unknown():
    prolog = "DatasourceType = = 'VIEW';"
    process = _process("None", prolog=prolog, data="n = 1;")
    assert _facts(process).effective_data_source is DataSourceState.UNKNOWN
    assert _messages(process) == []


def test_unrelated_unparseable_prolog_statement_keeps_the_answer():
    process = _process("None", prolog="n = = 1;", data="n = 1;")
    assert _messages(process) == [f"Data {SKIPPED}"]


def test_prolog_assignment_settles_a_source_the_format_does_not_store():
    process = _process(None, prolog="DatasourceType = 'NULL';", data="n = 1;")
    assert _messages(process) == [f"Data {SKIPPED}"]
    process = _process(None, prolog="DatasourceType = 'ASCII';")
    assert _messages(process) == [UNUSED]
    # Inside a branch it is not provable without a stored starting value.
    prolog = "IF(pMode = 1);\n  DatasourceType = 'NULL';\nENDIF;"
    process = _process(None, prolog=prolog, data="n = 1;", parameters=["pMode"])
    assert _messages(process) == []


def _deep(depth):
    return "IF(1 = 1);\n" * depth + "n = 1;\n" + "ENDIF;\n" * depth


def test_finding_moves_past_an_unparseable_section():
    process = _process("None", metadata=_deep(4), data="n = 1;")
    linter = linter_from_config(Config(max_nesting_depth=2), select="C153")
    issues = [
        (proc, issue)
        for proc, issue, _ in lint_process_model(process, linter)
        if issue.rule_id == "C153"
    ]
    assert [(proc, issue.message) for proc, issue in issues] == [
        ("data", f"Metadata and Data {SKIPPED}")
    ]


def test_unparseable_prolog_makes_the_source_unknown():
    # The unreadable Prolog could change DatasourceType, so nothing is claimed.
    process = _process("ASCII", prolog=_deep(4), epilog="n = 1;")
    linter = linter_from_config(Config(max_nesting_depth=2), select="C153")
    issues = [
        proc
        for proc, issue, _ in lint_process_model(process, linter)
        if issue.rule_id == "C153"
    ]
    assert issues == []
