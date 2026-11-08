# Function placement (C150, C151): IBM sources

Reviewed on 2026-09-20 against the IBM Planning Analytics function reference,
extended on 2026-11-08.
The rule matches individual function names, case-insensitively. It does not
infer placement from a prefix such as `Dimension`, `Hierarchy` or `Element`,
or from a suffix such as `Insert` or `Direct`.

Two kinds of finding are separated here, and they share one placement table:

- **Invalid Function Placement (C150)**, an error: a restriction IBM documents.
- **Discouraged Function Placement (C151)**, a warning: a placement LinTi
  recommends against.

`--select C15` runs both. Each rule is configured and suppressed on its own
(`rules.misplaced_function`, `rules.discouraged_function_placement`;
`# noqa: C150`, `# noqa: C151`).

## Migrating from the combined C150

Before C151 existed, C150 reported the recommendations below as errors.

- They now appear as **warnings under C151**. With the default `fail_on: error`
  they no longer fail the run.
- An existing `# noqa: C150` no longer suppresses them. Use `# noqa: C151`
  (or `# noqa: C150,C151`).
- `--select C150` no longer shows them. Use `--select C15`.
- `rules.misplaced_function.report_not_recommended: false` is deprecated. It
  still switches C151 off, as long as
  `rules.discouraged_function_placement.enabled` is not set.
- `rules.misplaced_function.allowed_functions` also applies to C151, as long as
  `rules.discouraged_function_placement.allowed_functions` is not set.
- `rules.misplaced_function.severity` applies to C150 only.

## Documented restrictions

| Function / IBM reference | Prolog | Metadata | Data | Epilog |
| --- | --- | --- | --- | --- |
| [DimensionElementInsert](https://www.ibm.com/docs/SSD29G_2.0.0/com.ibm.swg.ba.cognos.tm1_prism_gs.2.0.0.doc/r_tm1_ref_tifun_dimensionelementinsert.html) | Valid | Valid | Error | Error |
| [HierarchyElementInsert](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyelementinsert) | Valid | Valid | Error | Error |
| [DimensionElementComponentAdd](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-dimensionelementcomponentadd) | Valid | Valid | Valid | Error |
| [HierarchyElementComponentAdd](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyelementcomponentadd) | Valid | Valid | Valid | Error |
| [DisableBulkLoadMode](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-disablebulkloadmode) | Error | Error | Error | Valid |
| [AddInfoCubeRestriction](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-addinfocuberestriction) | Valid | Error | Error | Error |
| [DisableMTQViewConstruct](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-disablemtqviewconstruct) | Valid | Error | Error | Valid |

ComponentAdd documents an Epilog restriction only. LinTi does not extend the
Insert functions' Data restriction to ComponentAdd.

### AddInfoCubeRestriction and DisableMTQViewConstruct

AddInfoCubeRestriction: "This function must be placed in the Prolog."

DisableMTQViewConstruct has two statements that read differently: it "must
appear in the Prolog, it has no effect in any other procedure", and after
EnableMTQViewConstruct "it can only be disabled on the last line in the Epilog
section … anywhere else in the process, the process will not compile". Both
readings rule out Metadata and Data, so C150 reports those. The Epilog stays
valid for the second case; whether the call is the last line is not checked.

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

## Attribute-write recommendations (C151)

These functions are valid in Prolog, Data and Epilog, and are reported as
**discouraged** in Metadata:

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
particular element already exists. When an element is provably new, Element
Used Before Available (C152) reports the concrete error at that call instead.
Use `rules.discouraged_function_placement` (`enabled`, `allowed_functions`) or
`# noqa: C151` to suppress these recommendations where appropriate.

## Administrative changes in Data and Epilog (C151)

These functions are valid in Prolog and Metadata, and are reported as
**discouraged** in Data and Epilog:

- [AddClient](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-addclient) /
  [DeleteClient](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-deleteclient)
- [AddGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-addgroup) /
  [DeleteGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-deletegroup)
- [CellSecurityCubeCreate](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-cellsecuritycubecreate) /
  [CellSecurityCubeDestroy](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-cellsecuritycubedestroy)

Each of these references says: "This function, like all functions that
update metadata, should not be used in the Data or Epilog tabs of a process."
That is a recommendation rather than a prohibition, so C151 reports it as a
warning, not C150 as an error. The AddClient, DeleteClient, AddGroup and
DeleteGroup references add that their changes do not take effect until the
Metadata procedure has completed. The references do not name a preferred tab;
LinTi accepts Prolog and Metadata.

## UpdateDirect in Metadata and Data (C151)

[DimensionUpdateDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=dmtf-dimensionupdatedirect)
"can optionally be used after directly editing a dimension" and "incurs an
initial full-copy memory cost". Metadata and Data run once per source record,
so a call there pays that full copy for every record. C151 discourages it in
Metadata and Data; Prolog and Epilog remain valid.
[HierarchyUpdateDirect](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=hmtf-hierarchyupdatedirect-1)
is classified the same way.

## Emptying a dimension (C151)

DimensionDeleteAllElements, DimensionDeleteElements, HierarchyDeleteAllElements
and HierarchyDeleteElements are valid in the Prolog only. A LinTi
recommendation: the references name no section. In Metadata and Data the
dimension is emptied once per source record; in the Epilog the call discards
what the process has just built.

## Once-per-process operations (C151)

These operations are discouraged in Metadata and Data, where they would run
once per source record. A LinTi recommendation: the references checked
(CubeClearData, ViewZeroOut, SubsetCreate, SecurityRefresh, …) name no section.

CubeClearData, ViewZeroOut, CubeProcessFeeders, SecurityRefresh, SaveDataAll,
CubeSaveData, CubeCreate, CubeDestroy, DimensionCreate, DimensionDestroy,
HierarchyCreate, HierarchyDestroy, ViewCreate, ViewDestroy, ViewCreateByMDX,
SubsetCreate, SubsetDestroy, SubsetCreateByMDX, RefreshMdxHierarchy,
CubeSetLogChanges, EnableBulkLoadMode, ASCIIDelete, DimensionSortOrder,
HierarchySortOrder.

DisableBulkLoadMode keeps its stricter C150 entry above.

### Calls under a condition

The once-per-process operations, UpdateDirect and the dimension-emptying
functions are discouraged in Metadata and Data only because those sections
repeat them for every source record. Inside an IF or ELSE body whose condition
can differ between records, the condition decides which records run the call
(a header line, the first record), so C151 does not report them there. The
condition has to read a data source variable, or a variable that Metadata or
Data assign a value that is not provably constant, such as a record counter.
A condition on parameters, constants or Prolog values is the same on every
record, so the call still runs every time and is reported. A call in the IF's
own condition, or in a WHILE outside any IF, is still reported too. The other
C151 entries (attribute writes, security, MTQ, input character set) are
reported whatever the nesting, because their reason is not the repetition.

## MTQ and the input character set (C151)

- [EnableMTQViewConstruct](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-enablemtqviewconstruct):
  "You can enable EnableMTQViewConstruct in either the Prolog or Epilog
  section". C151 discourages Metadata and Data.
- [SetInputCharacterSet](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-setinputcharacterset)
  describes the input file, the data source, which is opened when the Prolog
  ends. C151 discourages Metadata, Data and Epilog. A LinTi recommendation:
  the reference names no section.

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

UpdateDirect is listed separately above: it is discouraged in Metadata and
Data, but not restricted to the Epilog.

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
- [AssignClientToGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-assignclienttogroup),
  [RemoveClientFromGroup](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-removeclientfromgroup)
  and [SetElementGroupsSecurity](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-setelementgroupssecurity):
  unlike AddClient or AddGroup, their references do not carry the "should not
  be used in the Data or Epilog tabs" sentence.
- [ProcessBreak](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-processbreak):
  the reference only says it "proceeds to the Epilog"; what a call in the
  Epilog does is not documented.

Reviewed and deliberately left out because the documentation is contradictory,
outdated or not specific enough to justify a section restriction:

- [ExecuteProcess](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-executeprocess)
- [ItemReject](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-itemreject)
- [GetProcessErrorFileDirectory / GetProcessErrorFilename](https://www.ibm.com/docs/en/planning-analytics/2.0.0?topic=functions-getprocesserrorfilename):
  in Data it cannot tell whether Data itself writes errors, but it is the
  documented way to check the tabs before, so a call there is not wrong.

An older [TM1 10.2 APAR](https://www.ibm.com/support/pages/apar/PI13436)
reports DimensionElementComponentDelete not working in Epilog. That historical,
version-specific report is insufficient for a universal restriction when the
Planning Analytics function reference does not repeat it.

Here, *valid* or *unrestricted* means C150 has no finding based solely on the
procedure section. It does not assert that object existence, data dependencies,
or combinations of buffered and direct edits are correct.

The existing ItemSkip classification is unchanged: Metadata/Data are valid,
Prolog/Epilog produce errors.
