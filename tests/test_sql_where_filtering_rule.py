"""Tests for SqlWhereFilteringRule (S340)."""

from linti.linter.api import lint_process_model
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules.semantic.sql_where_filtering_rule import SqlWhereFilteringRule


def _lint(
    code: str,
    block: str = "data",
    datasource_type: str = "ODBC",
    datasource_query: str = "SELECT amount, region FROM sales",
    prolog: str = None,
):
    linter = Linter(statement_rules=[SqlWhereFilteringRule()])
    sections = {block: ProcedureInfo(code=code)}
    if prolog is not None:
        sections["prolog"] = ProcedureInfo(code=prolog)
    process = ProcessIR(
        name="test_process",
        datasource_type=datasource_type,
        datasource_query=datasource_query,
        **sections,
    )
    return [issue for _, issue, _ in lint_process_model(process, linter)]


# --- ItemSkip without WHERE ---


def test_itemskip_without_where_is_flagged():
    code = "IF(vRegion @= 'EMEA');\n  ItemSkip();\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 1
    assert issues[0].rule_id == "S340"
    assert "ItemSkip()" in issues[0].message


def test_unconditional_itemskip_is_flagged():
    issues = _lint("ItemSkip();")
    assert len(issues) == 1
    assert "ItemSkip()" in issues[0].message


def test_itemskip_with_where_clause_is_ignored():
    code = "IF(vRegion @= 'EMEA');\n  ItemSkip();\nENDIF;"
    assert (
        _lint(code, datasource_query="SELECT amount FROM sales WHERE region = ?") == []
    )


def test_where_matching_is_case_insensitive():
    code = "ItemSkip();"
    assert (
        _lint(code, datasource_query="select amount from sales where region = 1") == []
    )


# --- all-conditional writes without WHERE ---


def test_all_conditional_writes_are_flagged():
    code = "IF(vRegion @= 'EMEA');\n  CellPutN(vAmount, 'Sales', vRegion);\nENDIF;"
    issues = _lint(code)
    assert len(issues) == 1
    assert "conditional" in issues[0].message


def test_unconditional_write_is_not_flagged():
    code = (
        "CellPutN(vAmount, 'Sales', vRegion);\n"
        "IF(vRegion @= 'EMEA');\n"
        "  CellPutS('x', 'Note', vRegion);\n"
        "ENDIF;"
    )
    assert _lint(code) == []


def test_write_in_loop_without_if_is_unconditional():
    code = (
        "WHILE(nI < 5);\n  CellPutN(vAmount, 'Sales', vRegion);\n  nI = nI + 1;\nEND;"
    )
    assert _lint(code) == []


def test_write_in_if_inside_loop_is_conditional():
    code = (
        "WHILE(nI < 5);\n"
        "  IF(vRegion @= 'EMEA');\n"
        "    CellPutN(vAmount, 'Sales', vRegion);\n"
        "  ENDIF;\n"
        "  nI = nI + 1;\n"
        "END;"
    )
    issues = _lint(code)
    assert len(issues) == 1
    assert "conditional" in issues[0].message


def test_cell_increment_counts_as_a_write():
    code = "IF(vRegion @= 'EMEA');\n  CellIncrementN(1, 'Sales', vRegion);\nENDIF;"
    assert len(_lint(code)) == 1


def test_itemskip_and_conditional_writes_report_both():
    code = (
        "IF(vRegion @= 'EMEA');\n"
        "  CellPutN(vAmount, 'Sales', vRegion);\n"
        "ELSE;\n"
        "  ItemSkip();\n"
        "ENDIF;"
    )
    issues = _lint(code)
    assert len(issues) == 2
    messages = " ".join(i.message for i in issues)
    assert "ItemSkip()" in messages
    assert "conditional" in messages


# --- gating: block, datasource type, missing query ---


def test_ignored_outside_metadata_and_data():
    code = "IF(x = 1);\n  ItemSkip();\nENDIF;"
    assert _lint(code, block="prolog") == []
    assert _lint(code, block="epilog") == []


def test_metadata_block_is_checked():
    code = "IF(x = 1);\n  ItemSkip();\nENDIF;"
    assert len(_lint(code, block="metadata")) == 1


def test_non_odbc_datasource_is_ignored():
    code = "ItemSkip();"
    assert _lint(code, datasource_type="ASCII") == []
    assert _lint(code, datasource_type="None") == []


def test_missing_query_is_ignored():
    code = "ItemSkip();"
    assert _lint(code, datasource_query=None) == []


def test_no_writes_and_no_itemskip_is_ignored():
    code = "nTotal = nTotal + vAmount;"
    assert _lint(code) == []


# --- Prolog overrides of DatasourceQuery / DatasourceType ---


def test_prolog_query_override_with_where_suppresses():
    # Metadata query has no WHERE, but the Prolog override adds one.
    issues = _lint(
        "ItemSkip();",
        prolog="DatasourceQuery = 'SELECT amount FROM sales WHERE region = 1';",
    )
    assert issues == []


def test_prolog_query_override_without_where_is_used_over_metadata():
    # Metadata query HAS a WHERE, but the Prolog override removes it — the
    # override wins, so the pattern is flagged.
    issues = _lint(
        "ItemSkip();",
        datasource_query="SELECT amount FROM sales WHERE region = 1",
        prolog="DatasourceQuery = 'SELECT amount FROM sales';",
    )
    assert len(issues) == 1
    assert "ItemSkip()" in issues[0].message


def test_prolog_type_override_to_non_odbc_suppresses():
    issues = _lint("ItemSkip();", prolog="DatasourceType = 'ASCII';")
    assert issues == []


def test_prolog_type_override_to_odbc_enables():
    # Metadata type is not ODBC, but the Prolog sets it to ODBC.
    issues = _lint(
        "ItemSkip();",
        datasource_type="None",
        prolog="DatasourceType = 'ODBC';",
    )
    assert len(issues) == 1


def test_dynamic_query_override_is_not_flagged():
    # Overridden to a value that cannot be read statically: stay silent rather
    # than trust the stale metadata query.
    issues = _lint("ItemSkip();", prolog="DatasourceQuery = GetProcessName();")
    assert issues == []


def test_partial_query_override_is_not_flagged():
    # A partially known query (dynamic tail) can't be proven WHERE-free.
    issues = _lint(
        "ItemSkip();",
        prolog="DatasourceQuery = 'SELECT amount FROM sales ' | pFilter;",
    )
    assert issues == []
