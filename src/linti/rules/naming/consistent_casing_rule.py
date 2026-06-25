"""Rule N230: Variables Consistent Casing."""

from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class VariablesConsistentCasingRule(BaseRule):
    """
    Enforces consistent casing for variable references within a process.

    TM1 variables are case-insensitive, but using multiple casings for the
    same variable reduces readability. This rule detects variables referenced
    with different casings and suggests using a single, consistent form.

    For parameters and data source variables, the casing from the YAML
    declaration is canonical. For script variables, the first occurrence
    in code defines the canonical casing.
    """

    CONFIG_KEY = "variable_consistent_casing"
    METADATA = RuleMetadata(
        name="Variables Consistent Casing",
        description="Enforces consistent casing for variable references within a process",
        auto_fix=True,
        explanation=(
            "TM1 variables are case-insensitive, meaning `vYear`, `vyear`, and "
            "`VYEAR` all refer to the same variable. While technically valid, "
            "inconsistent casing reduces readability and breaks PAW variable "
            "highlighting when navigating code.\n\n"
            "For parameters and data source variables, the casing from the metadata "
            "declaration is used as the canonical form. For script variables, the "
            "first occurrence in code defines the canonical casing.\n\n"
            "The autofix replaces all inconsistent references with the canonical form."
        ),
        config_example=("rules:\n  variable_consistent_casing:\n    enabled: true"),
        examples=[
            RuleExample(
                code="sName = 'hello';\nIF(sName @= 'hello');",
                description="Consistent casing throughout",
                valid=True,
            ),
            RuleExample(
                code="sName = 'hello';\nIF(sname @= 'hello');",
                description="Inconsistent casing for the same variable",
                valid=False,
            ),
        ],
    )

    def __init__(self):
        self._canonical: dict[str, str] = {}
        self._initialized = False

    @property
    def RULE_ID(self) -> str:
        return "N230"

    def reset(self):
        self._canonical = {}
        self._initialized = False

    def interested_in(self):
        return [TokenType.IDENTIFIER]

    def visit(self, token, window, context: LintContext):
        if not self._initialized:
            self._initialized = True
            if context.parameters:
                for name in context.parameters:
                    self._canonical[name.lower()] = name
            if context.variables:
                for name in context.variables:
                    self._canonical[name.lower()] = name

        key = token.value.lower()
        if key not in self._canonical:
            self._canonical[key] = token.value
            return []

        expected = self._canonical[key]
        if token.value != expected:
            return [
                LintIssue(
                    rule_id=self.RULE_ID,
                    message=f"Inconsistent casing: '{token.value}' should be '{expected}'",
                    line=token.line,
                    column=token.column,
                    position=token.position,
                    fix=Fix(
                        position=token.position,
                        old_value=token.value,
                        new_value=expected,
                    ),
                )
            ]
        return []
