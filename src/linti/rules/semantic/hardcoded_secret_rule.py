"""Rule X130: Report hardcoded literal secrets assigned to secret-looking variables."""

from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Assignment, FunctionCall, Identifier, Number, String
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

# Name fragments that mark a variable as holding a credential. The presets are
# cumulative: each level adds to the one below it.
_RELAXED: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
    }
)

_STANDARD: frozenset[str] = _RELAXED | {
    "apikey",
    "api_key",
    "token",
    "credential",
}

# `key` and `auth` are common enough in ordinary TI code (sKey, sAuthority) that
# they only belong in the opt-in level.
_STRICT: frozenset[str] = _STANDARD | {
    "key",
    "auth",
    "cert",
    "salt",
    "signature",
}

# Fragments precise enough that a numeric literal is still worth flagging
# (a PIN-style "password"). The strict-only fragments (`key`, `auth`, `cert`,
# `salt`, `signature`) stay string-only: they are common names for ordinary
# integers (dimension keys, permission levels, ...), so treating a number
# assigned to one of those as a secret would be a steady source of false
# positives. Custom `secret_names` are just as generic by default, so they
# stay string-only too.
_NUMERIC_SECRET_PATTERNS: frozenset[str] = _STANDARD

_DEFAULT_MODE = "standard"

#: Mode name → the fragments it contributes. ``custom`` contributes nothing, so
#: the configured ``secret_names`` become the whole list.
_PRESETS: dict[str, frozenset[str]] = {
    "relaxed": _RELAXED,
    "standard": _STANDARD,
    "strict": _STRICT,
    "custom": frozenset(),
}

#: Functions that read a value out of a cube. Attribute lookups belong here too:
#: attributes live in ``}ElementAttributes_*`` cubes, so they sit in the same
#: files on disk.
_CUBE_READ_FUNCTIONS: frozenset[str] = frozenset(
    name.lower()
    for name in (
        "CellGetS",
        "CellGetN",
        "AttrS",
        "AttrN",
        "ElementAttrS",
        "ElementAttrN",
    )
)

#: Internal source name → how the finding is phrased. ``{name}`` is the
#: variable's original casing and ``{func}`` the reading function; the assigned
#: value and the cube coordinates are deliberately never echoed. Adding a
#: further source (ODBC, file, …) means an entry here plus a branch in
#: :meth:`HardcodedSecretRule._source_of`.
_MESSAGES: dict[str, str] = {
    "literal": (
        "'{name}' is assigned a hardcoded literal secret; "
        "pass the value in as a process parameter instead"
    ),
    "cube": (
        "'{name}' reads a secret from a cube via {func}(); TM1 cube files are "
        "unencrypted unless data-directory encryption is enabled, so pass the "
        "value in as a process parameter instead"
    ),
}


class HardcodedSecretRule(BaseStatementRule):
    """Reports secret-looking variables fed from a literal or from a cube.

    A literal is found by two independent detectors whose results are unioned,
    so an assignment yields at most one issue:

    * :meth:`_source_of` — the right-hand side *is* a string (or, for the
      precise fragments in :data:`_NUMERIC_SECRET_PATTERNS`, a number)
      literal. Works without a process model, and still sees a literal inside
      a ``WHILE`` body (constant evaluation deliberately forgets loop values).
    * :meth:`_proves_literal` — constant evaluation proves the variable holds
      a non-empty string (or, again gated by
      :data:`_NUMERIC_SECRET_PATTERNS`, a number) at this line. This is what
      catches a folded concatenation (``'let' | 'mein'``) and a literal routed
      through another variable, neither of which is a literal node on the
      right-hand side.

    Cube reads stay purely syntactic: constant evaluation reports every
    function call as dynamic, so it cannot tell ``CellGetS`` from a parameter.
    Only a *direct* call on the right-hand side counts —
    ``sPassword = Trim(CellGetS(...));`` is not reported. Widening that means
    swapping the ``isinstance`` check in :meth:`_source_of` for
    ``iter_function_calls`` (``parser/ast.py``).
    """

    CONFIG_KEY = "hardcoded_secret"
    METADATA = RuleMetadata(
        name="No Hardcoded Secrets",
        description=(
            "Reports variables whose name looks like a credential being fed from a "
            "hardcoded string literal or read out of a cube"
        ),
        auto_fix=False,
        explanation=(
            "A credential written straight into the source ships with the process. "
            "Once the process is committed, the value is in version control for "
            "good — rotating it later does not remove it from the history. Pass "
            "secrets in as process parameters instead, so the value lives in the "
            "caller (or a secure store) rather than in the script.\n\n"
            "Keeping the credential in a control cube and reading it back with "
            "CellGetS() is reported for the same reason. Cube values — attributes "
            "included, since they live in `}ElementAttributes_*` cubes — are held "
            "in the TM1 data directory. That directory *can* be encrypted, but in "
            "practice almost never is, so anyone with file access to the server, a "
            "backup or a snapshot reads the value without needing a TM1 login. Set "
            "`allow_secrets_in_cubes: true` if your deployment accepts that risk.\n\n"
            "A variable is considered secret-looking when its name contains one of "
            "the configured fragments, matched case-insensitively (so `sPassword`, "
            "`vApiKey` and `sPwd_Prod` all qualify). It is reported when the value "
            "is provably a non-empty string — whether written directly, folded "
            "from a concatenation (`'let' | 'mein'`) or carried over from another "
            "variable that holds a literal — or when it comes from a direct cube "
            "read. For the most unambiguous fragments (`password`, `apikey`, "
            "`token`, ... — the `standard` preset) a numeric literal such as "
            "`sPassword = 12345;` counts too, since a PIN is still a hardcoded "
            "secret; the generic `strict`-only fragments (`key`, `auth`, `cert`, "
            "...) and custom `secret_names` stay string-only, since those names "
            "are just as commonly an ordinary integer. Whatever cannot be resolved "
            "statically is left alone: parameters, datasource variables and other "
            "function results. So are half-known values such as "
            "`sPassword = 'prefix_' | pDyn;`, where the secret itself may well be "
            "dynamic, and the common `sPassword = '';` initialisation.\n\n"
            "Neither the value nor the cube coordinates ever appear in linti's "
            "output — reports often end up in CI logs. Widen or narrow the name "
            "detection with `mode`, extend it with `secret_names`, or suppress a "
            "single finding inline with `# noqa: X130`."
        ),
        config_example=(
            "rules:\n"
            "  hardcoded_secret:\n"
            "    enabled: true\n"
            "    # relaxed | standard | strict | custom\n"
            "    mode: standard\n"
            "    # Extra name fragments (the whole list when mode is 'custom'):\n"
            "    # secret_names:\n"
            "    #   - kennwort\n"
            "    # Set to true to accept credentials stored in a cube:\n"
            "    allow_secrets_in_cubes: false"
        ),
        examples=[
            RuleExample(
                code="sPassword = 'hunter2';",
                description="Hardcoded credential — ships with the process",
                valid=False,
            ),
            RuleExample(
                code="sPassword = 'let' | 'mein';",
                description="Split across a concatenation — folded back together",
                valid=False,
            ),
            RuleExample(
                code="sPassword = 12345;",
                description="A numeric PIN is still a hardcoded secret",
                valid=False,
            ),
            RuleExample(
                code="sApiKey = CellGetS('Config', 'Api', 'Key');",
                description=(
                    "Stored in a cube — readable by anyone with file access to the "
                    "TM1 data directory"
                ),
                valid=False,
            ),
            RuleExample(
                code="sPassword = pPassword;",
                description="Passed in as a process parameter",
                valid=True,
            ),
            RuleExample(
                code="sPassword = 'prefix_' | pDyn;",
                description="Only half known — the secret itself may be dynamic",
                valid=True,
            ),
            RuleExample(
                code="sPassword = '';",
                description="Empty-string initialisation is a common no-op",
                valid=True,
            ),
            RuleExample(
                code="sCustomer = CellGetS('Sales', '2026', 'Customer');",
                description="Ordinary cube read — the name is not secret-looking",
                valid=True,
            ),
        ],
    )

    def __init__(
        self,
        mode: str = _DEFAULT_MODE,
        secret_names: list[str] | None = None,
        allow_secrets_in_cubes: bool = False,
    ) -> None:
        self.mode = str(mode).lower() if mode else _DEFAULT_MODE
        if self.mode not in _PRESETS:
            self.mode = _DEFAULT_MODE
        self.secret_names = frozenset(
            str(name).lower() for name in (secret_names or [])
        )
        # Preset plus the configured extras, resolved once per instance so each
        # visited assignment only scans a flat set of fragments.
        self.patterns = _PRESETS[self.mode] | self.secret_names
        self.allow_secrets_in_cubes = bool(allow_secrets_in_cubes)

    @property
    def RULE_ID(self) -> str:
        return "X130"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [
            cls(
                mode=rule_cfg.get("mode", _DEFAULT_MODE),
                secret_names=rule_cfg.get("secret_names") or [],
                allow_secrets_in_cubes=rule_cfg.get("allow_secrets_in_cubes", False),
            )
        ]

    def interested_in(self):
        return [Assignment]

    def visit(self, statement, context: LintContext):
        target = statement.left
        if not isinstance(target, Identifier):
            return []

        name = target.name
        lowered = name.lower()
        if not any(pattern in lowered for pattern in self.patterns):
            return []
        numeric_allowed = any(
            pattern in lowered for pattern in _NUMERIC_SECRET_PATTERNS
        )

        token = target.token
        source = self._source_of(statement.right, numeric_allowed)
        if source is None and self._proves_literal(
            name, token, context, numeric_allowed
        ):
            source = ("literal", "")
        if source is None:
            return []

        origin, func = source
        if origin == "cube" and self.allow_secrets_in_cubes:
            return []

        line, column, position = (
            (token.line, token.column, token.position) if token else (0, 0, 0)
        )

        return [
            LintIssue(
                message=_MESSAGES[origin].format(name=name, func=func),
                line=line,
                column=column,
                position=position,
                rule_id=self.RULE_ID,
            )
        ]

    @staticmethod
    def _source_of(value, numeric_allowed: bool) -> tuple[str, str] | None:
        """Classify where an assigned secret comes from.

        Returns ``(source, function_name)`` for a reportable source, else
        ``None``. Anything resolved at runtime — a parameter, another variable,
        an unrelated function call — is not a source. *numeric_allowed* says
        whether the matched name fragment is precise enough (see
        :data:`_NUMERIC_SECRET_PATTERNS`) that a numeric literal also counts.
        """
        if isinstance(value, String):
            # `sPassword = '';` (or a blank placeholder) initialises rather
            # than leaks.
            return ("literal", "") if value.value.strip() else None
        if numeric_allowed and isinstance(value, Number):
            return ("literal", "")
        if (
            isinstance(value, FunctionCall)
            and value.name.lower() in _CUBE_READ_FUNCTIONS
        ):
            return ("cube", value.name)
        return None

    @staticmethod
    def _proves_literal(
        name: str, token, context: LintContext, numeric_allowed: bool
    ) -> bool:
        """Whether constant evaluation proves *name* holds a literal secret here.

        Asks the existential ``any_of`` (see
        :class:`~linti.semantic.possible_values.PossibleValues`)
        rather than reading ``exact``: an assignment inside an ``IF`` is shadowed
        by the branch-join event, which the index records on the construct's last
        line — often the assignment's own line — and a join is never ``complete``,
        so ``exact`` would be ``None`` there. "At least one provable value is a
        non-empty string" holds in both shapes.

        The predicate only ever sees fully known values, so a partially known
        concatenation (``'prefix_' | pDyn``) is never proof. Numbers only count
        when *numeric_allowed* is set — see :data:`_NUMERIC_SECRET_PATTERNS`.
        """
        if token is None:
            return False
        possible = context.possible_values(name, token.line)
        return possible.any_of(
            lambda value: (isinstance(value, str) and value.strip())
            or (numeric_allowed and isinstance(value, float))
        )
