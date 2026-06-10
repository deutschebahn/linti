from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.rules.Rule import BaseRule, RuleExample, RuleMetadata


class KeywordCasingRule(BaseRule):
    """
    Enforces consistent keyword casing.

    Supported styles:
    - 'uppercase': IF, WHILE, END
    - 'lowercase': if, while, end
    - 'camelcase': If, While, End
    - 'consistent': Auto-detect from first keyword and enforce consistency
    """

    CONFIG_KEY = "keyword_casing"
    METADATA = RuleMetadata(
        name="Keyword Casing",
        description="Enforces consistent keyword casing (uppercase/lowercase/camelcase/consistent)",
        auto_fix=True,
        explanation=(
            "Enforces consistent casing for TM1 keywords (IF, ENDIF, ELSE, ELSEIF, WHILE, END).\n\n"
            "Supported styles:\n"
            "- uppercase: IF, ENDIF, ELSE, WHILE, END\n"
            "- lowercase: if, endif, else, while, end\n"
            "- camelcase: If, Endif, Else, While, End\n"
            "- consistent: Auto-detect from first keyword and enforce consistency"
        ),
        config_example=(
            "rules:\n"
            "  keyword_casing:\n"
            "    enabled: true\n"
            "    style: uppercase  # or lowercase, camelcase, consistent"
        ),
        examples=[
            RuleExample(
                code="IF (x = 1);\n    nResult = 10;\nENDIF;",
                description="uppercase style",
                valid=True,
            ),
            RuleExample(
                code="if (x = 1);\n    nResult = 10;\nendif;",
                description="lowercase style",
                valid=True,
            ),
            RuleExample(
                code="IF (x = 1);\n    nResult = 10;\nendif;",
                description="Mixed casing",
                valid=False,
            ),
        ],
    )

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        style = (
            rule_cfg.get("style", "uppercase")
            if isinstance(rule_cfg, dict)
            else getattr(rule_cfg, "style", "uppercase")
        )
        return [cls(style=style)]

    @property
    def RULE_ID(self) -> str:
        return "F110"

    def __init__(self, style: str = "uppercase"):
        """
        Initialize the rule with a casing style.

        Args:
            style: One of 'uppercase', 'lowercase', 'camelcase', or 'consistent'.
        """
        if style not in ("uppercase", "lowercase", "camelcase", "consistent"):
            raise ValueError(
                f"Invalid style: {style}. Must be 'uppercase', 'lowercase', 'camelcase', or 'consistent'"
            )
        self.style = style
        # For 'consistent' style, track detected style
        self.detected_style = None
        self.first_keyword_token = None

    def interested_in(self):
        """Only interested in keyword tokens."""
        return [
            TokenType.IF,
            TokenType.ELSE,
            TokenType.ELSEIF,
            TokenType.ENDIF,
            TokenType.WHILE,
            TokenType.END,
        ]

    def visit(self, token, window, context: LintContext):
        """
        Check that keyword matches the configured casing style.

        Args:
            token: The keyword token being visited.
            window: TokenWindow for accessing surrounding tokens.
            context: LintContext with block, parameters, variables.

        Returns:
            List of LintIssue objects.
        """
        keyword = token.value

        # Handle 'consistent' style - auto-detect from first keyword
        if self.style == "consistent":
            current_style = self._detect_style(keyword)

            # First keyword sets the expected style
            if self.detected_style is None:
                self.detected_style = current_style
                self.first_keyword_token = token
                return []

            # Check consistency with detected style
            if current_style != self.detected_style:
                return [
                    LintIssue(
                        message=(
                            f"Inconsistent keyword casing: expected {self.detected_style} "
                            f"(like '{self.first_keyword_token.value}' at line {self.first_keyword_token.line}), "
                            f"found {current_style} '{keyword}'"
                        ),
                        line=token.line,
                        column=token.column,
                        position=token.position,
                        rule_id=self.RULE_ID,
                    )
                ]
            return []

        # Handle explicit styles (uppercase, lowercase, camelcase)
        expected = self._get_expected_form(keyword)

        if keyword != expected:
            return [
                LintIssue(
                    message=f"Keyword should be '{expected}' ({self.style}), found '{keyword}'",
                    line=token.line,
                    column=token.column,
                    position=token.position,
                    rule_id=self.RULE_ID,
                    fix=Fix(
                        position=token.position,
                        old_value=keyword,
                        new_value=expected,
                    ),
                )
            ]

        return []

    def _get_expected_form(self, keyword: str) -> str:
        """
        Get the expected form of a keyword based on the configured style.

        Args:
            keyword: The keyword string in any casing.

        Returns:
            The keyword in the expected casing.
        """
        if self.style == "uppercase":
            return keyword.upper()
        elif self.style == "lowercase":
            return keyword.lower()
        elif self.style == "camelcase":
            return keyword.capitalize()

        return keyword

    def _detect_style(self, keyword: str) -> str:
        """
        Detect the casing style of a keyword.

        Args:
            keyword: The keyword string.

        Returns:
            One of 'uppercase', 'lowercase', or 'camelcase'.
        """
        if keyword.isupper():
            return "uppercase"
        elif keyword.islower():
            return "lowercase"
        elif keyword[0].isupper() and keyword[1:].islower():
            return "camelcase"
        else:
            # Mixed case (treat as camelcase for simplicity)
            return "camelcase"
