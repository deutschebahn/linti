"""Rule C430 – Do not use undocumented TurboIntegrator functions.

A number of TI functions exist in the engine but are absent from IBM's
documentation: ``DimensionElementInsertByAlias``, ``LockOn``, ``Hex`` and
others.  They work, and some of them solve problems no documented function
solves, but relying on them in production code is a bet: IBM makes no
compatibility promise for them, they can change behaviour or disappear in any
release, and support will not help when they do.

The rule reports every call to one of the names in ``UNDOCUMENTED_FUNCTIONS``.
Deliberate use is silenced either inline (``# noqa: C430``, also available
region- and procedure-wide) or project-wide by listing the function under the
rule's ``allowed_functions`` setting.

Like C510, the rule inspects the AST rather than the token stream: TI makes the
parentheses optional on a no-argument call, so ``LockOn;`` and ``LockOn();`` are
the same call and the parser normalises both to a ``FunctionCall`` — while a
plain variable read (``nX = IsNull + 2``) stays an identifier and is left alone.
"""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import (
    EXPRESSION_CARRYING_STATEMENTS,
    UnknownStatement,
    get_node_token,
    iter_function_calls,
    statement_expression,
)
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

#: Functions that exist in TM1 but are not part of IBM's documented API.
#: Matching is case-insensitive, so the set holds lower-cased names while the
#: tuple keeps the canonical casing for readability.
UNDOCUMENTED_FUNCTIONS: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # Cube handling
        "AddAllRuleBasedDependencies",
        "BatchCellIncrement",
        "CreateMultiHierarchyTestCubes",
        "CubeLockOverride",
        "CubeProcReduceDims",
        "CubeSetIsVirtual",
        "CubeSetLockStatus",
        "CubeSetSlicerMembers",
        "SetCubeGroupsSecurity",
        "DataSpread",
        # Dimension handling
        "DimensionEditingAliasSet",
        "DimensionElementInsertByAlias",
        "DimensionElementSetLockStatus",
        "DimensionSetLockStatus",
        "SwapAliasWithPrincipalName",
        # Locking
        "LockBreather",
        "LockOff",
        "LockOn",
        # Date and time
        "DatFM",
        "DyS",
        "MilliTime",
        "MoS",
        "YrS",
        # Debugging and server internals
        "AllowExternalRequests",
        "DebugUtility",
        "DebugUtilityEx",
        "EnablePersonalWorkspace",
        "EncodePassword",
        "ReturnCSVTableHandle",
        # Miscellaneous
        "Hex",
        "IsNull",
        "this",
    )
)

#: How a finding is phrased. ``{name}`` is filled with the call's original casing.
_MESSAGE = (
    "'{name}' is an undocumented TM1 function (not officially supported by IBM); "
    "avoid it in production code"
)


class DoNotUseUndocumentedFunctionsRule(BaseStatementRule):
    """Reports calls to TI functions IBM does not document or support."""

    CONFIG_KEY = "do_not_use_undocumented_functions"
    METADATA = RuleMetadata(
        name="Do Not Use Undocumented Functions",
        description=(
            "Reports calls to TurboIntegrator functions that are not officially "
            "documented or supported by IBM"
        ),
        auto_fix=False,
        explanation=(
            "Some TI functions exist in the engine but are missing from IBM's "
            "documentation — for example DimensionElementInsertByAlias, LockOn or "
            "Hex. They are occasionally useful, but they come with no compatibility "
            "guarantee: behaviour can change or the function can vanish in any "
            "release, and IBM support does not cover them. Production code should "
            "rely on the documented API instead.\n\n"
            "Matching is case-insensitive, and calls are found wherever they "
            "appear — including inside IF/WHILE conditions and nested arguments. "
            "Because TI makes the parentheses optional on a no-argument call, "
            "`LockOn;` is reported just like `LockOn();`. A name merely read as a "
            "variable is not a call and is never reported.\n\n"
            "When the use is intentional, suppress the finding inline with "
            "`# noqa: C430` (region- and procedure-level suppression works too), or "
            "list the function under `allowed_functions` to permit it across the "
            "whole project."
        ),
        config_example=(
            "rules:\n"
            "  do_not_use_undocumented_functions:\n"
            "    enabled: true\n"
            "    # Functions the project knowingly relies on (case-insensitive):\n"
            "    # allowed_functions:\n"
            "    #   - DimensionElementInsertByAlias"
        ),
        examples=[
            RuleExample(
                code="DimensionElementInsertByAlias('Product', '', 'Alias', 'N');",
                description="Undocumented: not part of IBM's supported API",
                valid=False,
            ),
            RuleExample(
                code="LockOn;",
                description=(
                    "Reported without parentheses too — TI makes them optional on a "
                    "no-argument call"
                ),
                valid=False,
            ),
            RuleExample(
                code="DimensionElementInsertDirect('Product', '', 'Element', 'N');",
                description="The documented equivalent is always allowed",
                valid=True,
            ),
            RuleExample(
                code="DataSpread;",
                description=(
                    "Allowed once the function is listed under `allowed_functions`"
                ),
                valid=True,
            ),
        ],
    )

    def __init__(self, allowed_functions: list[str] | None = None) -> None:
        self.allowed_functions = frozenset(
            str(name).lower() for name in (allowed_functions or [])
        )
        # Precomputed once per instance so each visited call costs a single
        # lookup; an allowed function is simply absent from the set.
        self._reported = UNDOCUMENTED_FUNCTIONS - self.allowed_functions

    @property
    def RULE_ID(self) -> str:
        return "C430"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [cls(allowed_functions=rule_cfg.get("allowed_functions") or [])]

    def interested_in(self):
        # Every statement that can carry a call — the linter's walk recurses into
        # IF/WHILE bodies, so nested statements arrive here too and only the
        # expression *within* each statement still needs traversing. Statements
        # the parser could not read are covered separately (see _visit_unknown).
        return [*EXPRESSION_CARRYING_STATEMENTS, UnknownStatement]

    def visit(self, statement, context: LintContext):
        if isinstance(statement, UnknownStatement):
            return self._visit_unknown(statement)

        expr = statement_expression(statement)
        if expr is None:
            return []

        return [
            self._issue(call.name, get_node_token(call))
            for call in iter_function_calls(expr)
            if call.name.lower() in self._reported
        ]

    def _visit_unknown(self, statement) -> list:
        """Best-effort scan of a statement the parser could not read.

        No AST exists here, so the token stream is matched by name: an
        identifier is reported when it is directly followed by ``(``, or when it
        stands alone as the statement (TI makes the parentheses optional on a
        no-argument call). P110 already reports the statement itself as
        unparseable; this only recovers the C430 finding hiding inside it.
        """
        tokens = [
            tok
            for tok in statement.tokens
            if tok.type not in (TokenType.WHITESPACE, TokenType.NEWLINE)
        ]
        issues = []
        for index, token in enumerate(tokens):
            if token.type != TokenType.IDENTIFIER:
                continue
            if token.value.lower() not in self._reported:
                continue
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            # Anything else (an operator, '=', a comma) means the name is being
            # used as a value, not called — skip it rather than guess.
            if following is not None and following.type not in (
                TokenType.LPAREN,
                TokenType.SEMICOLON,
            ):
                continue
            issues.append(self._issue(token.value, token))
        return issues

    def _issue(self, name: str, token) -> LintIssue:
        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )
        return LintIssue(
            rule_id=self.RULE_ID,
            message=_MESSAGE.format(name=name),
            line=line,
            column=column,
            position=position,
        )
