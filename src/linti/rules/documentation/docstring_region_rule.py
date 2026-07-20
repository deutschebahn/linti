"""D110 – Docstring region rule.

Every process prolog must contain a ``#Region - Docstring`` section (the exact
name is configurable) before any executable code. The region must include
required comment headers. Processes whose names start with a *generic prefix*
(e.g. ``}core.``) must additionally contain extra headers.

Example config::

    rules:
      docstring_region:
        enabled: true
        region_name: "Docstring"
        required_headers:
          - "# Description"
        generic_prefixes:
          - "}core."
        generic_extra_headers:
          - "# Use Case"
"""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.rules.generic_process import is_generic_process
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class DocstringRegionRule(BaseRule):
    """Enforces a docstring region before the first executable statement."""

    CONFIG_KEY = "docstring_region"
    DEPRECATED_IDS = ["D410"]
    DEFAULT_ENABLED = False
    METADATA = RuleMetadata(
        name="Docstring Region",
        description="Enforces a docstring region before executable code in the prolog",
        auto_fix=False,
        explanation=(
            "Every process prolog must begin with a ``#Region - Docstring`` "
            "section (name is configurable) that appears before any executable "
            "statement (i.e. before the first ``;``). "
            "The region must contain at least a ``# Description`` header. "
            "Processes whose names start with a configured *generic prefix* "
            "(e.g. ``}core.``) must also contain the extra headers defined in "
            "``generic_extra_headers``."
        ),
        config_example=(
            "rules:\n"
            "  docstring_region:\n"
            "    enabled: true\n"
            "    region_name: Docstring\n"
            "    required_headers:\n"
            "      - '# Description'\n"
            "    generic_prefixes:\n"
            "      - '}core.'\n"
            "    generic_extra_headers:\n"
            "      - '# Use Case'"
        ),
        examples=[
            RuleExample(
                code=(
                    "#Region - Docstring\n"
                    "# Description:\n"
                    "# Does something useful\n"
                    "#EndRegion - Docstring\n"
                    "nVar = 1;"
                ),
                valid=True,
            ),
            RuleExample(
                code="nVar = 1;",
                description="No docstring region before code",
                valid=False,
            ),
        ],
    )

    def __init__(
        self,
        region_name: str = "Docstring",
        required_headers: list[str] | None = None,
        generic_prefixes: list[str] | None = None,
        generic_extra_headers: list[str] | None = None,
    ) -> None:
        self._region_name = region_name
        self._required_headers: list[str] = required_headers or ["# Description"]
        self._generic_prefixes: list[str] = generic_prefixes or []
        self._generic_extra_headers: list[str] = generic_extra_headers or ["# Use Case"]
        self._reset_state()

    def reset(self) -> None:
        self._reset_state()

    def _reset_state(self) -> None:
        self._state: str = "scanning"
        self._headers_found: list[str] = []

    def _region_start_lower(self) -> str:
        return f"#Region - {self._region_name}".lower()

    def _region_end_lower(self) -> str:
        return f"#EndRegion - {self._region_name}".lower()

    def _is_region_end(self, val_lower: str) -> bool:
        """Return True if *val_lower* closes the docstring region.

        Accepts both ``#EndRegion - <name>`` and plain ``#EndRegion``.
        """
        if val_lower.startswith(self._region_end_lower()):
            return True
        # Plain #EndRegion (no name) also closes the current region.
        stripped = val_lower.lstrip("#").strip()
        return stripped == "endregion"

    def _is_generic(self, process_name: str | None) -> bool:
        """Return True when the process name starts with a generic prefix."""
        return is_generic_process(process_name, self._generic_prefixes)

    def _normalize_header(self, value: str) -> str:
        """Normalize a header for exact comparison."""
        return value.strip().lower().rstrip(":").rstrip()

    def _header_present(self, required: str) -> bool:
        """Check whether *required* header was found inside the region."""
        required_header = self._normalize_header(required)
        return any(
            self._normalize_header(found) == required_header
            for found in self._headers_found
        )

    def _check_header_issues(self, context: LintContext, token) -> list[LintIssue]:
        """Return issues for any missing required headers at region close."""
        issues: list[LintIssue] = []

        for hdr in self._required_headers:
            if not self._header_present(hdr):
                issues.append(
                    LintIssue(
                        f"Docstring region is missing required header '{hdr}'",
                        token.line,
                        token.column,
                        token.position,
                        rule_id=self.RULE_ID,
                    )
                )

        if self._is_generic(context.process_name):
            for hdr in self._generic_extra_headers:
                if not self._header_present(hdr):
                    issues.append(
                        LintIssue(
                            f"Generic process docstring is missing required header '{hdr}'",
                            token.line,
                            token.column,
                            token.position,
                            rule_id=self.RULE_ID,
                        )
                    )

        return issues

    @property
    def RULE_ID(self) -> str:
        return "D110"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        return [
            cls(
                region_name=rule_cfg.get("region_name", "Docstring"),
                required_headers=rule_cfg.get("required_headers", ["# Description"]),
                generic_prefixes=rule_cfg.get("generic_prefixes", []),
                generic_extra_headers=rule_cfg.get(
                    "generic_extra_headers", ["# Use Case"]
                ),
            )
        ]

    def interested_in(self):
        return [TokenType.COMMENT, TokenType.SEMICOLON]

    def visit(self, token, window, context: LintContext):
        if context.block != "prolog":
            return []

        val_lower = token.value.strip().lower()

        if token.type == TokenType.COMMENT:
            if self._state == "scanning":
                if val_lower.startswith(self._region_start_lower()):
                    self._state = "in_region"

            elif self._state == "in_region":
                if self._is_region_end(val_lower):
                    self._state = "done"
                    return self._check_header_issues(context, token)
                self._headers_found.append(token.value.strip())

            return []

        if token.type == TokenType.SEMICOLON:
            if self._state in ("done", "reported"):
                return []

            prev_state = self._state
            self._state = "reported"

            if prev_state == "scanning":
                return [
                    LintIssue(
                        f"Expected '#Region - {self._region_name}' docstring "
                        "before executable code",
                        token.line,
                        token.column,
                        token.position,
                        rule_id=self.RULE_ID,
                    )
                ]

            return [
                LintIssue(
                    f"'#Region - {self._region_name}' docstring region "
                    "was not closed before executable code",
                    token.line,
                    token.column,
                    token.position,
                    rule_id=self.RULE_ID,
                )
            ]

        return []
