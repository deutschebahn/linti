# Function placement (C150): IBM sources

Reviewed on 2026-09-20 against the IBM Planning Analytics function reference.
The rule matches individual function names, case-insensitively. It does not
infer placement from a prefix such as `Dimension`, `Hierarchy` or `Element`,
or from a suffix such as `Insert` or `Direct`.

Two kinds of finding are separated here — a restriction IBM documents, and a
placement LinTi recommends against — but both carry the rule's severity and
fail the run. `report_not_recommended: false` keeps only the documented
restrictions.

## Documented restrictions

| Function / IBM reference | Prolog | Metadata | Data | Epilog |
| --- | --- | --- | --- | --- |
| [DimensionElementInsert](https://www.ibm.com/docs/SSD29G_2.0.0/com.ibm.swg.ba.cognos.tm1_prism_gs.2.0.0.doc/r_tm1_ref_tifun_dimensionelementinsert.html) | Valid | Valid | Error | Error |
| [HierarchyElementInsert](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyelementinsert) | Valid | Valid | Error | Error |
| [DimensionElementComponentAdd](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementcomponentadd) | Valid | Valid | Valid | Error |
| [HierarchyElementComponentAdd](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyelementcomponentadd) | Valid | Valid | Valid | Error |
| [DisableBulkLoadMode](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-disablebulkloadmode) | Error | Error | Error | Valid |

ComponentAdd documents an Epilog restriction only. LinTi does not extend the
Insert functions' Data restriction to ComponentAdd.

### Bulk load mode

[DisableBulkLoadMode](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-disablebulkloadmode)
belongs in the **Epilog**. Bulk load mode dedicates the server to the running
process, so disabling it earlier returns the server to normal operation while
the process is still working. C150 reports an error for a call in Prolog,
Metadata or Data.

IBM asks for the call in the Epilog's *last line*. C150 does not check that
position: deciding whether a statement is the section's last needs a
section-wide analysis of its own, and bulk load mode exists only on v11 — not
worth that machinery in a rule that otherwise answers one question per call.
An Epilog call with further statements after it is therefore accepted. Its
counterpart
[EnableBulkLoadMode](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-enablebulkloadmode)
is left unrestricted: its reference names no section, and where the mode is
switched on is a scoping decision, not a documented error.

IBM's general [process-editing guidance](https://www.ibm.com/docs/en/planning-analytics/2.1.0?topic=basics-creating-editing-turbointegrator-processes)
also says functions can be used in any procedure. Where that general statement
conflicts with an explicit restriction in an individual function reference,
C150 follows the function-specific reference.

## Attribute-write recommendations

These functions are valid in Prolog, Data and Epilog, and are reported as
**not recommended** in Metadata:

- [AttrPutS](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=amtf-attrputs)
- [AttrPutN](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-attrputn)
- [ElementAttrPutS](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-elementattrputs)
- [ElementAttrPutN](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-elementattrputn)

This is a LinTi recommendation inferred from the
[procedure lifecycle](https://www.ibm.com/docs/en/planning-analytics/2.1.0?topic=basics-creating-editing-turbointegrator-processes),
not a section prohibition in the attribute function references. Buffered
dimension changes become available after the procedure finishes. Loading
attributes in Data avoids referring to elements still being created in
Metadata. Updating existing elements, including elements created through direct
edits, can be intentional in Metadata. The rule does not analyze whether a
particular element already exists. Use `report_not_recommended: false` or
`allowed_functions` to suppress these recommendations where appropriate.

## Administrative changes in Data and Epilog

These functions are valid in Prolog and Metadata, and are reported as **not
recommended** in Data and Epilog:

- [AddClient](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-addclient) /
  [DeleteClient](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-deleteclient)
- [AddGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-addgroup) /
  [DeleteGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-deletegroup)
- [CellSecurityCubeCreate](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-cellsecuritycubecreate) /
  [CellSecurityCubeDestroy](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-cellsecuritycubedestroy)

Also a LinTi recommendation rather than a documented prohibition. These
functions change server-wide security objects; the references do not restrict
them to a section. Running them in Data repeats the change for every source
record, and in Epilog they rebuild security after the load the process just
performed. Setting security up in Prolog — or in Metadata, alongside the
objects it applies to — keeps that out of the record loop.

## Direct edits

All four procedure sections are classified as valid for the following reviewed
functions. Their references do not impose a section restriction. IBM explicitly
describes direct edits in Data with an empty Metadata procedure, as well as
small changes to large dimensions. Using a Direct function in Metadata alone
is not enough evidence for a finding.

| Dimension function / IBM reference | Hierarchy function / IBM reference |
| --- | --- |
| [DimensionElementInsertDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementinsertdirect) | [HierarchyElementInsertDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchyelementinsertdirect) |
| [DimensionElementDeleteDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementdeletedirect) | [HierarchyElementDeleteDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchyelementdeletedirect) |
| [DimensionElementComponentAddDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementcomponentadddirect) | [HierarchyElementComponentAddDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchyelementcomponentadddirect) |
| [DimensionElementComponentDeleteDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementcomponentdeletedirect) | [HierarchyElementComponentDeleteDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchyelementcomponentdeletedirect) |
| [DimensionTopElementInsertDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensiontopelementinsertdirect) | [HierarchyTopElementInsertDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchytopelementinsertdirect) |
| [DimensionUpdateDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=dmtf-dimensionupdatedirect) | [HierarchyUpdateDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyupdatedirect-1) |

UpdateDirect compacts a dimension or hierarchy after direct edits. Its reference
does not require Epilog; LinTi does not impose that restriction.

## Reviewed without adding restrictions

The following function references do not state a procedure restriction. They
remain unlisted and unrestricted rather than inheriting the Insert or
ComponentAdd restrictions:

- [DimensionElementDelete](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=dmtf-dimensionelementdelete)
- [HierarchyElementDelete](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchyelementdelete)
- [DimensionElementComponentDelete](https://www.ibm.com/docs/en/planning-analytics/2.1.0?topic=functions-dimensionelementcomponentdelete)
- [HierarchyElementComponentDelete](https://www.ibm.com/docs/en/planning-analytics/2.1.0?topic=hmtf-hierarchyelementcomponentdelete)
- [DimensionTopElementInsert](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensiontopelementinsert)
- [HierarchyTopElementInsert](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-hierarchytopelementinsert)
- [ElementAttrInsert](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=amtf-elementattrinsert-1)

Reviewed and deliberately left out because the documentation is contradictory,
outdated or not specific enough to justify a section restriction:

- [EnableMTQViewConstruct](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-enablemtqviewconstruct) /
  [DisableMTQViewConstruct](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-disablemtqviewconstruct)
- [ExecuteProcess](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-executeprocess)
- [ItemReject](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-itemreject)
- [GetProcessErrorFileDirectory / GetProcessErrorFilename](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-getprocesserrorfilename)

An older [TM1 10.2 APAR](https://www.ibm.com/support/pages/apar/PI13436)
reports DimensionElementComponentDelete not working in Epilog. That historical,
version-specific report is insufficient for a universal restriction when the
Planning Analytics function reference does not repeat it.

Here, *valid* or *unrestricted* means C150 has no finding based solely on the
procedure section. It does not assert that object existence, data dependencies,
or combinations of buffered and direct edits are correct.

The existing ItemSkip classification is unchanged: Metadata/Data are valid,
Prolog/Epilog produce errors.
