"""C151: TurboIntegrator function calls in a section LinTi discourages."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue, Severity
from linti.parser.ast import (
    EXPRESSION_CARRYING_STATEMENTS,
    Assignment,
    Identifier,
    IfStatement,
    WhileStatement,
    get_node_token,
    iter_expression_nodes,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.semantic.process_facts import iter_statements
from linti.rules.semantic.function_placement import (
    DISCOURAGED_HINTS,
    PROCEDURE_SECTIONS,
    Placement,
    iter_placements,
    join_or,
    repeats_per_record,
    valid_sections,
)


class DiscouragedFunctionPlacementRule(BaseStatementRule):
    """Warn about calls in a section where they are allowed but discouraged."""

    CONFIG_KEY = "discouraged_function_placement"
    METADATA = RuleMetadata(
        name="Discouraged Function Placement",
        description="Warns about TI functions in a procedure section where they are allowed but discouraged",
        severity=Severity.WARNING,
        explanation=(
            "Reports a placement that is allowed but recommended against. "
            "It shares the placement table of Invalid Function Placement (C150), "
            "which reports the documented restrictions as errors. "
            "`--select C15` runs both.\n\n"
            "- AttrPutS / AttrPutN / ElementAttrPutS / ElementAttrPutN: "
            "discouraged in Metadata. Buffered dimension changes become visible "
            "only after the Metadata procedure finishes, so writing attributes "
            "in Data avoids referring to elements still being created. Updating "
            "elements that already exist can be intentional in Metadata. When "
            "the element is provably new, Element Used Before Available (C152) "
            "reports the concrete error instead of this warning.\n"
            "- AddClient / DeleteClient / AddGroup / DeleteGroup / "
            "CellSecurityCubeCreate / CellSecurityCubeDestroy: discouraged in "
            "Data/Epilog. Their IBM references say that, like all functions "
            "that update metadata, they should not be used in the Data or "
            "Epilog tabs. Client and group changes take effect only after the "
            "Metadata procedure has finished.\n"
            "- DimensionUpdateDirect / HierarchyUpdateDirect: discouraged in "
            'Metadata/Data. IBM: the call "incurs an initial full-copy memory '
            'cost", which these sections pay once per source record.\n'
            "- DimensionDeleteAllElements / DimensionDeleteElements / "
            "HierarchyDeleteAllElements / HierarchyDeleteElements: valid in the "
            "Prolog only. Emptying a dimension per record or after the load "
            "discards what the process builds.\n"
            "- Once-per-process operations, discouraged in Metadata/Data because "
            "they run once per source record: CubeClearData, ViewZeroOut, "
            "CubeProcessFeeders, SecurityRefresh, SaveDataAll, CubeSaveData, "
            "CubeCreate/Destroy, DimensionCreate/Destroy, "
            "HierarchyCreate/Destroy, ViewCreate/Destroy, ViewCreateByMDX, "
            "SubsetCreate/Destroy, SubsetCreateByMDX, RefreshMdxHierarchy, "
            "CubeSetLogChanges, EnableBulkLoadMode, ASCIIDelete, "
            "DimensionSortOrder, HierarchySortOrder.\n"
            "- EnableMTQViewConstruct: discouraged in Metadata/Data. IBM: "
            '"You can enable EnableMTQViewConstruct in either the Prolog or '
            'Epilog section".\n'
            "- SetInputCharacterSet: valid in the Prolog only. It describes the "
            "data source, which is opened when the Prolog ends.\n\n"
            "The UpdateDirect, dimension-emptying and once-per-process entries "
            "are discouraged in Metadata/Data only because those sections "
            "repeat them per source record. A call inside an IF or ELSE body is "
            "not reported there when the condition can differ between records, "
            "because it then selects the records the call runs for (a header "
            "line, the first record). That needs a data source variable in the "
            "condition, or a variable Metadata or Data assign a value that is "
            "not provably constant, such as a record counter. A condition on "
            "parameters, constants or Prolog values is the same on every "
            "record and does not count. A call in the IF's own condition, or "
            "in a WHILE outside any IF, is still reported.\n\n"
            "The security, UpdateDirect and MTQ entries rest on the IBM "
            "references; the others are LinTi recommendations. See "
            "docs/function-placement.md.\n\n"
            "These recommendations used to be C150 errors. They are now "
            "warnings under their own ID, so a `# noqa: C150` no longer "
            "suppresses them; use `# noqa: C151`.\n\n"
            "allowed_functions exempts functions in every section. Unless this "
            "rule sets its own list, it uses rules.misplaced_function."
            "allowed_functions. The deprecated rules.misplaced_function."
            "report_not_recommended: false switches this rule off as long as "
            "rules.discouraged_function_placement.enabled is not set."
        ),
        config_example=(
            "rules:\n"
            "  discouraged_function_placement:\n"
            "    enabled: true\n"
            "    # Functions to exempt; unset falls back to\n"
            "    # rules.misplaced_function.allowed_functions.\n"
            "    allowed_functions: []"
        ),
        examples=[
            RuleExample(
                code="AttrPutS(vDescription, 'Product', vProduct, 'Description');",
                description="Data: write the attribute after Metadata completes",
                procedure="data",
            ),
            RuleExample(
                code="AddGroup('Planners');",
                description="Prolog: set security up before the load",
            ),
            RuleExample(
                code="AttrPutS(vDescription, 'Product', vProduct, 'Description');",
                description="Metadata: discouraged placement",
                valid=False,
                procedure="metadata",
            ),
            RuleExample(
                code="AddGroup(vGroup);",
                description="Data: runs once per source record",
                valid=False,
                procedure="data",
            ),
            RuleExample(
                code="ViewZeroOut('Sales', 'Zero');",
                description="Prolog: clear the target once before the load",
            ),
            RuleExample(
                code=(
                    "IF(SubsetExists(vDim, 'tmp') = 0);\n"
                    "    SubsetCreate(vDim, 'tmp');\n"
                    "ENDIF;"
                ),
                description="Data: the condition limits the call to some records",
                procedure="data",
                variables=["vDim"],
            ),
            RuleExample(
                code="ViewZeroOut('Sales', 'Zero');",
                description="Data: clears the view again for every record",
                valid=False,
                procedure="data",
            ),
            RuleExample(
                code="IF(pZero = 1);\n    ViewZeroOut('Sales', 'Zero');\nENDIF;",
                description="Data: a parameter is the same on every record",
                valid=False,
                procedure="data",
                parameters=["pZero"],
            ),
        ],
    )

    def __init__(self, allowed_functions: list[str] | None = None):
        """
        Args:
            allowed_functions: Functions to exempt in every section, matched
                case-insensitively.
        """
        self._allowed = {name.strip().lower() for name in allowed_functions or []}
        #: id(statement) -> conditions of the IFs whose body holds it.
        self._enclosing: dict[int, tuple] = {}
        #: Names assigned anywhere in the section being linted.
        self._assigned_here: set[str] = set()

    def reset(self) -> None:
        self._enclosing = {}
        self._assigned_here = set()

    def prepare(self, ast) -> None:
        self.reset()
        statements = getattr(ast, "statements", None) or []
        self._index_enclosing(statements, ())
        self._assigned_here = _assigned_names(statements)

    def _index_enclosing(self, statements, conditions: tuple) -> None:
        for stmt in statements:
            if conditions:
                self._enclosing[id(stmt)] = conditions
            if isinstance(stmt, IfStatement):
                inner = (*conditions, stmt.condition)
                self._index_enclosing(stmt.then_body, inner)
                self._index_enclosing(stmt.else_body or [], inner)
            elif isinstance(stmt, WhileStatement):
                self._index_enclosing(stmt.body, conditions)

    def _limited_to_some_records(self, statement, context: LintContext) -> bool:
        """Whether an enclosing IF condition can differ between source records.

        A condition reading only parameters, constants or Prolog values is the
        same on every record, so the call still runs every time. It limits the
        call only when it reads a data source variable, or a variable Metadata
        or Data assign a value that is not provably constant (a record counter,
        ``sDim = vDim``).
        """
        conditions = self._enclosing.get(id(statement))
        if not conditions:
            return False
        per_record = {name.lower() for name in context.variables or []}
        assigned = set(self._assigned_here)
        facts = context.process_facts
        if facts is not None:
            for section in _RECORD_SECTIONS:
                ast = facts.section_ast(section)
                if ast is not None:
                    assigned |= _assigned_names(ast.statements)
        for condition in conditions:
            for node in iter_expression_nodes(condition):
                if not isinstance(node, Identifier):
                    continue
                name = node.name.lower()
                if name in per_record:
                    return True
                if name in assigned:
                    token = get_node_token(node)
                    line = token.line if token else 0
                    if context.possible_values(node.name, line).exact is None:
                        return True
        return False

    @classmethod
    def resolve_config(cls, rules, rule_cfg):
        from linti.config import resolve_discouraged_placement

        return resolve_discouraged_placement(rules)

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [cls(allowed_functions=rule_cfg.get("allowed_functions") or [])]

    @property
    def RULE_ID(self) -> str:
        return "C151"

    def interested_in(self):
        return list(EXPRESSION_CARRYING_STATEMENTS)

    def visit(self, statement, context: LintContext):
        section = (context.block or "").lower()
        if section not in PROCEDURE_SECTIONS:
            return []

        issues = []
        limited = None  # computed on the first call that needs it
        for call, placements in iter_placements(
            statement, section, Placement.DISCOURAGED, self._allowed
        ):
            if repeats_per_record(call.name, section):
                if limited is None:
                    limited = self._limited_to_some_records(statement, context)
                if limited:
                    continue
            hint = DISCOURAGED_HINTS.get(call.name.lower())
            if hint is None:
                valid = valid_sections(placements)
                hint = f"Consider using it in {join_or(valid)}." if valid else ""
            message = f"{call.name} in {section.title()} is discouraged. {hint}"
            token = get_node_token(call)
            issues.append(
                LintIssue(
                    message=message.strip(),
                    line=token.line if token else 0,
                    column=token.column if token else 0,
                    position=token.position if token else 0,
                    rule_id=self.RULE_ID,
                )
            )
        return issues


_RECORD_SECTIONS = ("metadata", "data")


def _assigned_names(statements) -> set[str]:
    return {
        stmt.left.name.lower()
        for stmt in iter_statements(statements)
        if isinstance(stmt, Assignment) and isinstance(stmt.left, Identifier)
    }
