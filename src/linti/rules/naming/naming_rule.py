from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.parser.ast import Assignment, WhileStatement
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata
from linti.semantic.type_inference import infer_type


def _collect_loop_counter_names(statements: list) -> set[str]:
    """Return names of single-char variables initialised directly before a WHILE loop.

    Looks *backward* from each ``WhileStatement``, collecting every contiguous
    run of single-character ``Assignment`` statements that precede it.  This
    handles the common pattern of initialising multiple counters (``i``, ``j``)
    before a single WHILE loop.  Recurses into IF/WHILE bodies.
    """
    from linti.parser.ast import IfStatement

    names: set[str] = set()
    for i, stmt in enumerate(statements):
        if isinstance(stmt, WhileStatement):
            # Walk backwards through consecutive single-char assignments
            j = i - 1
            while (
                j >= 0
                and isinstance(statements[j], Assignment)
                and len(statements[j].left.name) == 1
            ):
                names.add(statements[j].left.name)
                j -= 1
        # Recurse into nested blocks
        if isinstance(stmt, IfStatement):
            names.update(_collect_loop_counter_names(stmt.then_body))
            names.update(_collect_loop_counter_names(stmt.else_body or []))
        if isinstance(stmt, WhileStatement):
            names.update(_collect_loop_counter_names(stmt.body))
    return names


class VariablePrefixRule(BaseStatementRule):
    """
    Enforces TM1 variable naming conventions:
    - Numeric variables must start with 'n'
    - String variables must start with 's'
    - Optionally allow constants to start with 'c'
    - TM1 predefined system variables are automatically excluded
    """

    CONFIG_KEY = "variable_prefix"
    METADATA = RuleMetadata(
        name="Variable Prefix Naming",
        description="Enforces TM1 variable naming conventions (n/s/c prefixes)",
        auto_fix=False,
        explanation=(
            "Enforces TM1 variable naming conventions:\n"
            "- Numeric variables must start with 'n': nCount, nValue, nSum\n"
            "- String variables must start with 's': sMessage, sName, sPath\n"
            "- Optional constants may start with 'c': cRate, cMessage\n\n"
            "If `allow_constant_prefix` is enabled, any variable starting with 'c' "
            "may only be assigned once in the process (see C220).\n\n"
            "If `allow_loop_counter_variables` is enabled, single-character numeric "
            "variables (e.g. i, j) that are assigned directly before a WHILE loop "
            "are exempt from naming conventions.\n\n"
            "TM1 predefined system variables (e.g. DatasourceASCIIDecimalSeparator, "
            "NValue, SValue) are automatically excluded from naming convention checks."
        ),
        config_example=(
            "rules:\n"
            "  variable_prefix:\n"
            "    enabled: true\n"
            "    allow_constant_prefix: false\n"
            "    allow_loop_counter_variables: true"
        ),
        examples=[
            RuleExample(code="nCount = 5;", description="Numeric variable", valid=True),
            RuleExample(
                code="sMessage = 'test';", description="String variable", valid=True
            ),
            RuleExample(
                code="count = 5;", description="Missing 'n' prefix", valid=False
            ),
            RuleExample(
                code="name = 'test';", description="Missing 's' prefix", valid=False
            ),
            RuleExample(
                code="i = 0;\nWHILE(i < 10);\n  i = i + 1;\nEND;",
                description="Loop counter before WHILE (exempt when allow_loop_counter_variables: true)",
                valid=True,
            ),
            RuleExample(
                code="DatasourceASCIIDecimalSeparator = ',';",
                description="Predefined variable (excluded)",
                valid=True,
            ),
        ],
    )

    @classmethod
    def from_config(cls, rule_cfg: dict) -> list:
        from linti.rules.semantic.constant_rule import ConstantAssignmentRule

        allow = (
            rule_cfg.get("allow_constant_prefix", False)
            if isinstance(rule_cfg, dict)
            else getattr(rule_cfg, "allow_constant_prefix", False)
        )
        allow_loop = (
            rule_cfg.get("allow_loop_counter_variables", False)
            if isinstance(rule_cfg, dict)
            else getattr(rule_cfg, "allow_loop_counter_variables", False)
        )
        rules: list = [
            cls(allow_constant_prefix=allow, allow_loop_counter_variables=allow_loop)
        ]
        if allow:
            rules.append(ConstantAssignmentRule())
        return rules

    @property
    def RULE_ID(self) -> str:
        return "N110"

    def __init__(
        self,
        allow_constant_prefix: bool = False,
        allow_loop_counter_variables: bool = False,
    ):
        """
        Initialize the rule.

        Args:
            allow_constant_prefix: If True, allow variables to start with 'c'.
            allow_loop_counter_variables: If True, allow single-character numeric
                variables (e.g. i, j) that are assigned directly before a WHILE loop.
        """
        self.allow_constant_prefix = allow_constant_prefix
        self.allow_loop_counter_variables = allow_loop_counter_variables
        self._loop_counter_names: set[str] = set()

    def reset(self) -> None:
        self._loop_counter_names = set()

    def prepare(self, ast) -> None:
        """Pre-scan AST to find single-char loop counter variable names."""
        if self.allow_loop_counter_variables:
            from linti.parser.ast import Program

            statements = ast.statements if isinstance(ast, Program) else []
            self._loop_counter_names = _collect_loop_counter_names(statements)

    def interested_in(self):
        """Only interested in Assignment statements."""
        return [Assignment]

    def visit(self, statement, context: LintContext):
        """
        Check that variable name prefix matches the assigned value type.

        Args:
            statement: An Assignment AST node.
            context: LintContext with block, parameters, variables.

        Returns:
            List of LintIssue objects.
        """
        # Get the identifier token
        token = statement.left.token
        if not token:
            # Fallback if token is not available
            return []

        # Skip TM1 predefined system variables (tokenized as PREDEFINED_IDENTIFIER)
        if token.type == TokenType.PREDEFINED_IDENTIFIER:
            return []

        var_name = statement.left.name
        rhs_type = infer_type(statement.right)

        errors = []
        line, column, position = token.line, token.column, token.position

        is_constant = self.allow_constant_prefix and var_name.lower().startswith("c")
        is_loop_counter = (
            self.allow_loop_counter_variables
            and len(var_name) == 1
            and var_name in self._loop_counter_names
        )

        if rhs_type == "number" and not (
            var_name.lower().startswith("n") or is_constant or is_loop_counter
        ):
            errors.append(
                LintIssue(
                    message=f"Numeric variables must start with 'n' (found '{var_name}')",
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            )

        if rhs_type == "string" and not (
            var_name.lower().startswith("s") or is_constant
        ):
            errors.append(
                LintIssue(
                    message=f"String variables must start with 's' (found '{var_name}')",
                    line=line,
                    column=column,
                    position=position,
                    rule_id=self.RULE_ID,
                )
            )

        return errors
