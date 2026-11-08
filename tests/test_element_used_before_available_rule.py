"""C152: cube access to a provably new element whose buffered insert is pending."""

import pytest

from linti.cli.file_linter import linter_from_config
from linti.config import Config
from linti.linter.api import lint_process_model
from linti.linter.lint_issue import Severity
from linti.model.process_ir import ProcedureInfo, ProcessIR

GUARD = "IF(DIMIX('Product', vProduct) = 0);"
INSERT = "DimensionElementInsert('Product', '', vProduct, 'N');"
WRITE = "AttrPutS(vName, 'Product', vProduct, 'Caption');"


def _issues(metadata="", data="", prolog="", select="C152", config=None):
    process = ProcessIR(
        name="p",
        prolog=ProcedureInfo(code=prolog) if prolog else None,
        metadata=ProcedureInfo(code=metadata),
        data=ProcedureInfo(code=data) if data else None,
        variables=["vProduct", "vName"],
    )
    linter = linter_from_config(Config(rules=config or {}), select=select)
    return [issue for _, issue, _ in lint_process_model(process, linter)]


def _ids(*args, **kwargs):
    return [issue.rule_id for issue in _issues(*args, **kwargs)]


def test_write_after_guarded_insert_in_same_path():
    issues = _issues(f"{GUARD}\n  {INSERT}\n  {WRITE}\nENDIF;")
    assert len(issues) == 1
    issue = issues[0]
    assert issue.rule_id == "C152"
    assert issue.severity is Severity.ERROR
    assert issue.line == 3
    assert issue.message == (
        "AttrPutS uses element 'vProduct', inserted in line 2, before cubes can "
        "address it (after the Metadata phase); the write is lost. Write the "
        "attribute in Data, or insert the element with the Direct variant "
        "before any buffered insert into this dimension."
    )


@pytest.mark.parametrize(
    "guard",
    [
        "IF(DIMIX('Product', vProduct) = 0);",
        "IF(0 = DimIx('PRODUCT', vProduct));",
        "IF(ElementIndex('Product', 'Product', vProduct) = 0);",
        "IF(ElementIndex('Product', '', vProduct) = 0 & n > 1);",
        "IF(~(DIMIX('Product', vProduct) > 0));",
        "IF(~(DIMIX('Product', vProduct) <> 0 % n = 1));",
    ],
)
def test_recognized_absence_guards(guard):
    assert _ids(f"{guard}\n  {INSERT}\n  {WRITE}\nENDIF;") == ["C152"]


def test_else_branch_of_a_presence_test_proves_absence():
    code = (
        "IF(DIMIX('Product', vProduct) > 0);\n  n = 1;\n"
        f"ELSE;\n  {INSERT}\n  {WRITE}\nENDIF;"
    )
    assert _ids(code) == ["C152"]


def test_write_after_endif_when_both_paths_insert():
    code = f"{GUARD}\n  {INSERT}\nENDIF;\n{WRITE}"
    # The ELSE path (element exists) has nothing pending: not every path.
    assert _ids(code) == []


@pytest.mark.parametrize(
    "end", ["ItemSkip;", "ItemReject('exists');", "ProcessQuit;", "ProcessBreak;"]
)
def test_a_branch_that_ends_the_path_does_not_count(end):
    code = f"IF(DIMIX('Product', vProduct) > 0);\n  {end}\nENDIF;\n{INSERT}\n{WRITE}"
    assert _ids(code) == ["C152"]


def test_break_does_not_end_the_path():
    code = (
        "WHILE(n < 3);\n"
        "  IF(DIMIX('Product', vProduct) > 0);\n    Break;\n  ENDIF;\n"
        "  n = n + 1;\n"
        "END;\n"
        f"{INSERT}\n{WRITE}"
    )
    assert _ids(code) == []


def test_code_after_a_path_end_is_not_analyzed():
    code = f"{GUARD}\n  {INSERT}\n  ProcessQuit;\n  {WRITE}\nENDIF;"
    assert _ids(code) == []


@pytest.mark.parametrize(
    "write",
    [
        "AttrPutN(1, 'Product', vProduct, 'Weight');",
        "ElementAttrPutS(vName, 'Product', 'Product', vProduct, 'Caption');",
        "ElementAttrPutN(1, 'product', '', vProduct, 'Weight');",
        "CellPutS(vName, '}ElementAttributes_Product', vProduct, 'Caption');",
    ],
)
def test_write_variants(write):
    assert _ids(f"{GUARD}\n  {INSERT}\n  {write}\nENDIF;") == ["C152"]


def test_hierarchy_insert_and_element_attribute_write():
    code = (
        "IF(ElementIndex('Product', 'Reporting', vProduct) = 0);\n"
        "  HierarchyElementInsert('Product', 'Reporting', '', vProduct, 'N');\n"
        "  ElementAttrPutS(vName, 'Product', 'Reporting', vProduct, 'Caption');\n"
        "  AttrPutS(vName, 'Product', vProduct, 'Caption');\n"
        "ENDIF;"
    )
    # Only the write to the same hierarchy is proven to miss the element.
    assert [issue.line for issue in _issues(code)] == [3]


def test_literal_resolved_through_constant_evaluation():
    code = (
        "sDim = 'Product';\nsEl = 'P100';\n"
        "IF(DIMIX(sDim, 'P100') = 0);\n"
        "  DimensionElementInsert('Product', '', sEl, 'N');\n"
        "  AttrPutS('x', sDim, 'p100', 'Caption');\n"
        "ENDIF;"
    )
    issues = _issues(code)
    assert len(issues) == 1
    assert "'p100'" in issues[0].message


@pytest.mark.parametrize(
    "code",
    [
        # No proof that the element is new.
        f"{INSERT}\n{WRITE}",
        # Guard proves a different element absent.
        f"IF(DIMIX('Product', vOther) = 0);\n  {INSERT}\n  {WRITE}\nENDIF;",
        # Guard about another dimension.
        f"IF(DIMIX('Region', vProduct) = 0);\n  {INSERT}\n  {WRITE}\nENDIF;",
        # Insert and write in separate branches.
        f"{GUARD}\n  {INSERT}\nELSE;\n  {WRITE}\nENDIF;",
        # A Direct insert makes the element addressable at once.
        f"{GUARD}\n  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\nENDIF;",
        # The buffered insert ran on one path only, so the Direct insert after
        # the IF is not proven to wait.
        f"IF(DIMIX('Product', 'Total') = 0);\n"
        "  DimensionElementInsert('Product', '', 'Total', 'C');\nENDIF;\n"
        f"{GUARD}\n  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\nENDIF;",
        # A buffered insert into another dimension does not block this one.
        "IF(DIMIX('Region', 'R1') = 0 & DIMIX('Product', vProduct) = 0);\n"
        "  DimensionElementInsert('Region', '', 'R1', 'N');\n"
        "  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\nENDIF;",
        # Element variable reassigned between insert and write.
        f"{GUARD}\n  {INSERT}\n  vProduct = 'X';\n  {WRITE}\nENDIF;",
        # Unresolvable argument.
        f"{GUARD}\n  {INSERT}\n  AttrPutS(vName, 'Product', vProduct | 'x', 'C');\nENDIF;",
        # Cube with unknown dimension order.
        f"{GUARD}\n  {INSERT}\n  CellPutS(vName, 'Sales', vProduct, 'Caption');\nENDIF;",
        # Write before the insert.
        f"{GUARD}\n  {WRITE}\n  {INSERT}\nENDIF;",
    ],
)
def test_unproven_cases_stay_silent(code):
    assert _ids(code) == []


def test_write_in_data_after_metadata_insert_is_fine():
    assert _ids(f"{GUARD}\n  {INSERT}\nENDIF;", data=WRITE) == []


def test_prolog_is_analyzed_like_metadata():
    code = f"{GUARD}\n  {INSERT}\n  {WRITE}\nENDIF;"
    issues = _issues(metadata="", prolog=code)
    assert [issue.rule_id for issue in issues] == ["C152"]
    assert "inserted in line 2" in issues[0].message


def test_data_and_epilog_are_not_analyzed():
    code = f"{GUARD}\n  {INSERT}\n  {WRITE}\nENDIF;"
    assert _ids(metadata="", data=code) == []


def test_direct_insert_after_buffered_insert_still_waits():
    """Measured: after a buffered insert, a Direct one is not addressable either."""
    code = (
        "IF(DIMIX('Product', 'Total') = 0 & DIMIX('Product', vProduct) = 0);\n"
        "  DimensionElementInsert('Product', '', 'Total', 'C');\n"
        "  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\nENDIF;"
    )
    issues = _issues(code)
    assert [issue.rule_id for issue in issues] == ["C152"]
    assert "inserted in line 3" in issues[0].message


def test_buffered_insert_after_direct_insert_does_not_block_it():
    """Measured: a Direct element written before the first buffered insert lands."""
    code = (
        "IF(DIMIX('Product', 'Total') = 0 & DIMIX('Product', vProduct) = 0);\n"
        "  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\n"
        "  DimensionElementInsert('Product', '', 'Total', 'C');\n"
        "ENDIF;"
    )
    assert _ids(code) == []


def test_prolog_insert_is_still_pending_in_metadata():
    """Measured: the phase, not the procedure, is the boundary."""
    prolog = (
        "IF(DIMIX('Product', 'P100') > 0);\n"
        "  ProcessQuit;\n"
        "ENDIF;\n"
        "DimensionElementInsert('Product', '', 'P100', 'N');"
    )
    metadata = "AttrPutS(vName, 'Product', 'P100', 'Caption');"
    issues = _issues(metadata=metadata, prolog=prolog)
    assert [(issue.rule_id, issue.line) for issue in issues] == [("C152", 1)]
    # The Prolog line is not named: the reporter shifts "line N" by the
    # current section's offset.
    assert "inserted in the Prolog" in issues[0].message
    assert "line" not in issues[0].message.split("inserted in")[1].split(",")[0]


def test_prolog_insert_in_one_branch_only_does_not_carry():
    # The ELSE path (element exists) reaches Metadata with nothing pending.
    prolog = (
        "IF(DIMIX('Product', 'P100') = 0);\n"
        "  DimensionElementInsert('Product', '', 'P100', 'N');\n"
        "ENDIF;"
    )
    metadata = "AttrPutS(vName, 'Product', 'P100', 'Caption');"
    assert _ids(metadata=metadata, prolog=prolog) == []


@pytest.mark.parametrize(
    "metadata,expected",
    [
        # The variable keeps its Prolog value in every record.
        ("AttrPutS(vName, 'Product', sNew, 'Caption');", ["C152"]),
        # Metadata reassigns it, so a later record may address another element.
        ("AttrPutS(vName, 'Product', sNew, 'Caption');\nsNew = vProduct;", []),
        # An unparseable statement might reassign anything.
        ("AttrPutS(vName, 'Product', sNew, 'Caption');\nthis is not ti ;", []),
    ],
)
def test_carried_variables_must_be_stable_across_records(metadata, expected):
    prolog = (
        "IF(DIMIX('Product', sNew) <> 0);\n"
        "  ProcessError;\n"
        "ENDIF;\n"
        "DimensionElementInsert('Product', '', sNew, 'N');"
    )
    assert _ids(metadata=metadata, prolog=prolog) == expected


def test_data_source_variables_do_not_carry_from_prolog():
    prolog = f"IF(DIMIX('Product', vProduct) > 0);\n  ProcessQuit;\nENDIF;\n{INSERT}"
    assert _ids(metadata=WRITE, prolog=prolog) == []


def test_prolog_absence_does_not_carry():
    """An earlier record may already have inserted the element Direct."""
    prolog = "IF(DIMIX('Product', 'P100') = 0);\n  n = 1;\nENDIF;"
    metadata = (
        "DimensionElementInsert('Product', '', 'P100', 'N');\n"
        "AttrPutS(vName, 'Product', 'P100', 'Caption');"
    )
    assert _ids(metadata=metadata, prolog=prolog) == []


@pytest.mark.parametrize(
    "read",
    [
        "s = AttrS('Product', vProduct, 'Caption');",
        "n = AttrN('Product', vProduct, 'Weight');",
        "s = ElementAttrS('Product', '', vProduct, 'Caption');",
        "n = ElementAttrN('Product', 'Product', vProduct, 'Weight');",
        "s = CellGetS('}ElementAttributes_Product', vProduct, 'Caption');",
        "IF(CellGetN('}ElementAttributes_Product', vProduct, 'Weight') > 0); ENDIF;",
    ],
)
def test_reads_are_reported(read):
    issues = _issues(f"{GUARD}\n  {INSERT}\n  {read}\nENDIF;")
    assert [issue.rule_id for issue in issues] == ["C152"]
    assert "the read returns no value. Read it in Data." in issues[0].message


def test_existence_probes_are_not_accesses():
    code = (
        f"{GUARD}\n  {INSERT}\n"
        "  IF(DIMIX('Product', vProduct) > 0); n = 1; ENDIF;\n"
        "  b = DimensionElementExists('Product', vProduct);\n"
        "ENDIF;"
    )
    assert _ids(code) == []


def test_while_body_forgets_reassigned_variables():
    code = (
        f"{GUARD}\n  {INSERT}\n"
        "  WHILE(n < 3);\n"
        f"    {WRITE}\n"
        "    vProduct = 'Next';\n"
        "  END;\n"
        "ENDIF;"
    )
    assert _ids(code) == []
    code = (
        f"{GUARD}\n  {INSERT}\n"
        f"  WHILE(n < 3);\n    {WRITE}\n    n = n + 1;\n  END;\n"
        "ENDIF;"
    )
    assert _ids(code) == ["C152"]


def test_unparseable_statement_clears_knowledge():
    code = f"{GUARD}\n  {INSERT}\n  this is not ti ;\n  {WRITE}\nENDIF;"
    assert "C152" not in _ids(code, select="C152")


def test_c152_replaces_c151_for_the_same_call():
    code = f"{GUARD}\n  {INSERT}\n  {WRITE}\n  {WRITE}\nENDIF;"
    assert _ids(code, select="C15") == ["C152", "C152"]
    # A plain Metadata attribute write still gets the general warning.
    assert _ids(WRITE, select="C15") == ["C151"]


def test_noqa_on_c152_lets_c151_through():
    code = f"{GUARD}\n  {INSERT}\n  # noqa: C152\n  {WRITE}\nENDIF;"
    assert _ids(code, select="C15") == ["C151"]


def test_disabled_c152_leaves_c151_in_place():
    code = f"{GUARD}\n  {INSERT}\n  {WRITE}\nENDIF;"
    config = {"element_used_before_available": {"enabled": False}}
    linter_ids = [
        issue.rule_id
        for issue in _issues(code, select=None, config=config)
        if issue.rule_id.startswith("C15")
    ]
    assert linter_ids == ["C151"]


def test_zero_greater_than_probe_proves_nothing():
    # 0 > DIMIX(...) is never true, so its ELSE branch runs for existing
    # elements too and proves nothing about absence.
    code = (
        "IF(0 > DIMIX('Product', vProduct));\n  n = 1;\n"
        f"ELSE;\n  {INSERT}\n  {WRITE}\nENDIF;"
    )
    assert _ids(code) == []
    # 0 < DIMIX(...) means present; its ELSE branch does prove absence.
    code = code.replace("0 > DIMIX", "0 < DIMIX")
    assert _ids(code) == ["C152"]


@pytest.mark.parametrize(
    "direct",
    [
        "n = DimensionElementInsertDirect('Product', '', vProduct, 'N');",
        "IF(DimensionElementInsertDirect('Product', '', vProduct, 'N') = 0); ENDIF;",
    ],
)
def test_direct_insert_outside_an_expression_statement_counts(direct):
    # Recognized as a Direct insert, it ends the proven absence, so the
    # buffered insert after it no longer counts as inserting a new element.
    code = f"{GUARD}\n  {direct}\n  {INSERT}\n  {WRITE}\nENDIF;"
    assert _ids(code) == []


def test_direct_insert_in_loop_assignment_resets_loop_entry():
    code = (
        f"{GUARD}\n  {INSERT}\n"
        "  WHILE(n < 3);\n"
        f"    {WRITE}\n"
        "    n = DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        "  END;\n"
        "ENDIF;"
    )
    assert _ids(code) == []


def test_prolog_buffered_insert_keeps_a_later_metadata_direct_insert_pending():
    prolog = (
        "IF(DIMIX('Product', 'Total') <> 0);\n  ProcessQuit;\nENDIF;\n"
        "DimensionElementInsert('Product', '', 'Total', 'C');"
    )
    metadata = (
        "IF(DIMIX('Product', vProduct) = 0);\n"
        "  DimensionElementInsertDirect('Product', '', vProduct, 'N');\n"
        f"  {WRITE}\nENDIF;"
    )
    issues = _issues(metadata, prolog=prolog)
    assert [(i.rule_id, i.line) for i in issues] == [("C152", 3)]


def test_prolog_buffered_dimension_named_by_a_metadata_variable_does_not_carry():
    prolog = (
        "IF(DIMIX(sDim, 'Total') <> 0);\n  ProcessQuit;\nENDIF;\n"
        "DimensionElementInsert(sDim, '', 'Total', 'C');"
    )
    metadata = (
        "sDim = vName;\n"
        "IF(DIMIX(sDim, vProduct) = 0);\n"
        "  DimensionElementInsertDirect(sDim, '', vProduct, 'N');\n"
        "  AttrPutS(vName, sDim, vProduct, 'Caption');\nENDIF;"
    )
    assert _issues(metadata, prolog=prolog) == []
