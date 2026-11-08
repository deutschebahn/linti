"""Shared section-placement table for C150 and C151.

Not a rule module: it declares no rule class, so the registry walk imports it
without registering anything. C150 (Invalid Function Placement) reports the
``INVALID`` entries, C151 (Discouraged Function Placement) the ``DISCOURAGED``
ones. Keeping both levels in one table means a function's classification is
reviewed in one place, and the two rules can never disagree about which
sections are fine.
"""

from collections.abc import Iterator
from enum import Enum

from linti.parser.ast import (
    FunctionCall,
    iter_function_calls,
    statement_expression,
)


class Placement(Enum):
    VALID = "valid"
    INVALID = "invalid"
    DISCOURAGED = "discouraged"


PROCEDURE_SECTIONS = ("prolog", "metadata", "data", "epilog")

#: Operations meant to run once per process, not once per source record.
ONCE_PER_PROCESS = (
    "cubecleardata",
    "viewzeroout",
    "cubeprocessfeeders",
    "securityrefresh",
    "savedataall",
    "cubesavedata",
    "cubecreate",
    "cubedestroy",
    "dimensioncreate",
    "dimensiondestroy",
    "hierarchycreate",
    "hierarchydestroy",
    "viewcreate",
    "viewdestroy",
    "viewcreatebymdx",
    "subsetcreate",
    "subsetdestroy",
    "subsetcreatebymdx",
    "refreshmdxhierarchy",
    "cubesetlogchanges",
    "enablebulkloadmode",
    "asciidelete",
    "dimensionsortorder",
    "hierarchysortorder",
)

# Unlisted functions and missing sections are unrestricted. Match exact names:
# a Direct variant must never inherit restrictions from its non-Direct sibling.
# IBM sources and the reasoning behind each family are in
# docs/function-placement.md (reviewed 2026-09-20).
FUNCTION_PLACEMENTS: dict[str, dict[str, Placement]] = {
    # IBM explicitly excludes Data and Epilog for these two insert functions.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.INVALID,
            "epilog": Placement.INVALID,
        }
        for name in ("dimensionelementinsert", "hierarchyelementinsert")
    },
    # ComponentAdd documents only an Epilog exclusion, not a Data exclusion.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.VALID,
            "epilog": Placement.INVALID,
        }
        for name in ("dimensionelementcomponentadd", "hierarchyelementcomponentadd")
    },
    # Bulk load mode has to stay on for the whole process, so the disable call
    # belongs in the Epilog. Whether it is that section's *last* statement is
    # not checked: the position would need its own section-wide analysis, and
    # bulk load mode only exists on v11.
    "disablebulkloadmode": {
        "prolog": Placement.INVALID,
        "metadata": Placement.INVALID,
        "data": Placement.INVALID,
        "epilog": Placement.VALID,
    },
    # IBM: "This function must be placed in the Prolog."
    "addinfocuberestriction": {
        "prolog": Placement.VALID,
        "metadata": Placement.INVALID,
        "data": Placement.INVALID,
        "epilog": Placement.INVALID,
    },
    # IBM: it "must appear in the Prolog, it has no effect in any other
    # procedure", except that after EnableMTQViewConstruct it may only close
    # the Epilog ("anywhere else in the process, the process will not
    # compile"). Metadata and Data are wrong under both readings; the Epilog
    # position is not checked.
    "disablemtqviewconstruct": {
        "prolog": Placement.VALID,
        "metadata": Placement.INVALID,
        "data": Placement.INVALID,
        "epilog": Placement.VALID,
    },
    # Advisory, not an IBM prohibition: write attributes after the Metadata
    # pass commits newly created elements. Existing elements can be updated
    # in Metadata, so this is a C151 warning rather than a C150 error.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.DISCOURAGED,
            "data": Placement.VALID,
            "epilog": Placement.VALID,
        }
        for name in ("attrputs", "attrputn", "elementattrputs", "elementattrputn")
    },
    # Security functions update metadata. Their IBM references say they should
    # not be used in the Data or Epilog tabs (a recommendation, not an error).
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.VALID,
            "data": Placement.DISCOURAGED,
            "epilog": Placement.DISCOURAGED,
        }
        for name in (
            "addclient",
            "deleteclient",
            "addgroup",
            "deletegroup",
            "cellsecuritycubecreate",
            "cellsecuritycubedestroy",
        )
    },
    # Direct edits act on the actual dimension; IBM explicitly describes Data
    # loads with an empty Metadata section. No blanket Metadata warning or
    # Data/Epilog ban is documented.
    **{
        name: dict.fromkeys(PROCEDURE_SECTIONS, Placement.VALID)
        for name in (
            "dimensionelementinsertdirect",
            "dimensionelementdeletedirect",
            "dimensionelementcomponentadddirect",
            "dimensionelementcomponentdeletedirect",
            "dimensiontopelementinsertdirect",
            "hierarchyelementinsertdirect",
            "hierarchyelementdeletedirect",
            "hierarchyelementcomponentadddirect",
            "hierarchyelementcomponentdeletedirect",
            "hierarchytopelementinsertdirect",
        )
    },
    # IBM: UpdateDirect "can optionally be used after directly editing a
    # dimension" and "incurs an initial full-copy memory cost". Called in
    # Metadata or Data, that full copy is paid once per source record.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.DISCOURAGED,
            "data": Placement.DISCOURAGED,
            "epilog": Placement.VALID,
        }
        for name in ("dimensionupdatedirect", "hierarchyupdatedirect")
    },
    # LinTi recommendation: emptying a dimension once per source record
    # (Metadata, Data) or after the load (Epilog) discards what the process
    # builds. The references name no section.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.DISCOURAGED,
            "data": Placement.DISCOURAGED,
            "epilog": Placement.DISCOURAGED,
        }
        for name in (
            "dimensiondeleteallelements",
            "dimensiondeleteelements",
            "hierarchydeleteallelements",
            "hierarchydeleteelements",
        )
    },
    # LinTi recommendation: once-per-process operations repeat for every
    # source record in Metadata and Data. The references name no section.
    # DisableBulkLoadMode has its own, stricter entry above.
    **{
        name: {
            "prolog": Placement.VALID,
            "metadata": Placement.DISCOURAGED,
            "data": Placement.DISCOURAGED,
            "epilog": Placement.VALID,
        }
        for name in ONCE_PER_PROCESS
    },
    # IBM: "You can enable EnableMTQViewConstruct in either the Prolog or
    # Epilog section", ideally as the Prolog's first statement.
    "enablemtqviewconstruct": {
        "prolog": Placement.VALID,
        "metadata": Placement.DISCOURAGED,
        "data": Placement.DISCOURAGED,
        "epilog": Placement.VALID,
    },
    # LinTi recommendation: the input character set describes the data
    # source, which is opened when the Prolog ends.
    "setinputcharacterset": {
        "prolog": Placement.VALID,
        "metadata": Placement.DISCOURAGED,
        "data": Placement.DISCOURAGED,
        "epilog": Placement.DISCOURAGED,
    },
    "itemskip": {
        "prolog": Placement.INVALID,
        "metadata": Placement.VALID,
        "data": Placement.VALID,
        "epilog": Placement.INVALID,
    },
}

#: Functions discouraged in Metadata/Data only because those sections repeat
#: them for every source record. Inside an IF the call runs only for the
#: records the condition selects (a header line, the first record, a missing
#: subset), so C151 does not report it there; see ``repeats_per_record``.
REPEATS_PER_RECORD = frozenset(
    {
        *ONCE_PER_PROCESS,
        "dimensionupdatedirect",
        "hierarchyupdatedirect",
        "dimensiondeleteallelements",
        "dimensiondeleteelements",
        "hierarchydeleteallelements",
        "hierarchydeleteelements",
    }
)

_RECORD_SECTIONS = ("metadata", "data")


def repeats_per_record(func_name: str, section: str) -> bool:
    """Whether *func_name* is discouraged in *section* only for repeating."""
    return section in _RECORD_SECTIONS and func_name.lower() in REPEATS_PER_RECORD


#: A more specific fix hint than "use it in <sections>" for a discouraged
#: placement. Unlisted functions fall back to the generic wording.
DISCOURAGED_HINTS: dict[str, str] = {
    **dict.fromkeys(
        ("attrputs", "attrputn", "elementattrputs", "elementattrputn"),
        "Consider writing attributes in Data.",
    ),
    **dict.fromkeys(
        ONCE_PER_PROCESS,
        "Metadata and Data run it once per source record; "
        "consider the Prolog or the Epilog.",
    ),
    **dict.fromkeys(
        ("dimensionupdatedirect", "hierarchyupdatedirect"),
        "Each call rewrites the whole dimension, here once per source record; "
        "consider the Prolog or the Epilog.",
    ),
    **dict.fromkeys(
        (
            "dimensiondeleteallelements",
            "dimensiondeleteelements",
            "hierarchydeleteallelements",
            "hierarchydeleteelements",
        ),
        "Empty the dimension in the Prolog, before the data source is read.",
    ),
}


def valid_sections(placements: dict[str, Placement]) -> list[str]:
    """The sections a function does belong in, in execution order, titled."""
    return [
        name.title()
        for name in PROCEDURE_SECTIONS
        if placements.get(name, Placement.VALID) is Placement.VALID
    ]


def join_or(names: list[str]) -> str:
    """``['A']`` → ``A``; ``['A', 'B', 'C']`` → ``A, B or C``."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"


def iter_placements(
    statement, section: str, level: Placement, allowed: set[str]
) -> Iterator[tuple[FunctionCall, dict[str, Placement]]]:
    """Yield every call in *statement* whose placement in *section* is *level*.

    *allowed* holds lower-cased names a project exempts. A section the table
    leaves out carries no restriction, so an incomplete entry stays a silent
    no-op instead of a KeyError.
    """
    for call in iter_function_calls(statement_expression(statement)):
        func_name = call.name.lower()
        placements = FUNCTION_PLACEMENTS.get(func_name)
        if placements is None or func_name in allowed:
            continue
        if placements.get(section, Placement.VALID) is level:
            yield call, placements
