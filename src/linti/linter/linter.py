from linti.lexer.token_window import TokenWindow
from linti.semantic.constant_evaluation import DEFAULT_MAX_VALUES_PER_VARIABLE
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Severity
from linti.linter.noqa import filter_issues, parse_noqa
from linti.parser.parser import DEFAULT_MAX_NESTING_DEPTH, Parser
from linti.provider.base import DEFAULT_MAX_FILE_SIZE
from linti.rules.Rule import BaseTokenRule, BaseStatementRule


def _stamped(rule, issues: list) -> list:
    """Tag each issue with the producing rule's effective severity.

    Rules build plain ``LintIssue``s and stay unaware of severity: the weight of
    a finding is a project decision (``rules.<key>.severity``), not something a
    rule should hard-code at every construction site. ``rule.severity`` has
    already resolved config override → METADATA → default, so it wins
    unconditionally here.
    """
    severity = rule.severity
    for issue in issues:
        issue.severity = severity
    return issues


class Linter:
    def __init__(
        self,
        rules: list[BaseTokenRule] = None,
        statement_rules: list[BaseStatementRule] = None,
        max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_values_per_variable: int = DEFAULT_MAX_VALUES_PER_VARIABLE,
        nesting_depth_enabled: bool = True,
        nesting_depth_severity: Severity = Severity.WARNING,
    ):
        """
        Initialize the linter with token-based and statement-based rules.

        Args:
            rules: List of token-based rules (BaseTokenRule instances).
            statement_rules: List of AST statement-based rules (BaseStatementRule instances).
            max_nesting_depth: Control-flow nesting cap forwarded to the parser.
            max_file_size: File-size ceiling (bytes) carried for the CLI flows
                that construct providers from a pre-built linter.
            max_values_per_variable: Cap on how many distinct values the constant
                evaluation index tracks per variable before degrading to
                UNKNOWN.
            nesting_depth_enabled: Whether the P900 diagnostic is reported at all.
            nesting_depth_severity: Weight of the P900 diagnostic. Read by
                ``linter.api``, which owns that pseudo-rule; it has no rule
                module to carry METADATA, so it is configured through here.
        """
        self.max_nesting_depth = max_nesting_depth
        self.max_file_size = max_file_size
        self.max_values_per_variable = max_values_per_variable
        self.nesting_depth_enabled = nesting_depth_enabled
        self.nesting_depth_severity = nesting_depth_severity
        # Registry for token-based rules
        self.token_registry = {}
        for rule in rules or []:
            for token_type in rule.interested_in():
                self.token_registry.setdefault(token_type, []).append(rule)

        # Registry for statement-based rules
        self.statement_registry = {}
        for rule in statement_rules or []:
            for stmt_type in rule.interested_in():
                self.statement_registry.setdefault(stmt_type, []).append(rule)

    def lint(self, tokens, context: LintContext = None, ast=None, source=None):
        """
        Run all linting rules on the given tokens.

        Args:
            tokens: List of Token objects.
            context: Optional LintContext with block, parameters, variables.
            ast: Optional pre-built AST (Program node).  When supplied the
                 parser is *not* invoked again, avoiding duplicate work.
            source: Optional raw source text.  Lets statement rules slice the
                 exact span of an auto-fix; without it such rules degrade to
                 reporting only.

        Returns:
            List of issues found (LintIssue objects and error messages).
        """
        if context is None:
            context = LintContext()

        # Expose the raw token stream and source so statement rules can reach
        # source-level detail (comments, exact fix spans) the AST drops.
        context.tokens = tokens
        if source is not None:
            context.source = source

        # The token pass runs before the AST is built, but layout rules need
        # the CST, so parse up front when the caller did not supply a tree.
        # ``collect_fixable_issues`` is one such caller.
        if ast is None:
            ast = Parser(tokens, max_nesting_depth=self.max_nesting_depth).parse()
        context.cst = getattr(ast, "cst", None)
        context._line_index = None

        # Reset mutable rule state so each lint pass starts clean
        for rules in self.token_registry.values():
            for rule in rules:
                rule.reset()
        seen_statement_rules: set[int] = set()
        for rules in self.statement_registry.values():
            for rule in rules:
                rid = id(rule)
                if rid not in seen_statement_rules:
                    seen_statement_rules.add(rid)
                    rule.reset()

        issues = []

        window = TokenWindow(tokens)
        for i, token in enumerate(tokens):
            window.set_index(i)
            for rule in self.token_registry.get(token.type, []):
                issues.extend(_stamped(rule, rule.visit(token, window, context)))

        # Let statement rules pre-scan the full AST (e.g. for lookahead)
        seen_prepare: set[int] = set()
        for rules in self.statement_registry.values():
            for rule in rules:
                rid = id(rule)
                if rid not in seen_prepare:
                    seen_prepare.add(rid)
                    rule.prepare(ast)

        issues.extend(self._visit_node(ast, context))

        # Apply noqa suppressions
        directives = parse_noqa(tokens)
        issues = filter_issues(issues, directives)

        return issues

    def _visit_node(self, node, context: LintContext) -> list:
        from linti.parser.ast import IfStatement, Program, WhileStatement

        issues = []

        for rule in self.statement_registry.get(type(node), []):
            issues.extend(_stamped(rule, rule.visit(node, context)))

        if isinstance(node, Program):
            for child in node.statements:
                issues.extend(self._visit_node(child, context))

        elif isinstance(node, IfStatement):
            context.block_stack.append("if")
            for child in node.then_body:
                issues.extend(self._visit_node(child, context))
            for child in node.else_body or []:
                issues.extend(self._visit_node(child, context))
            context.block_stack.pop()

        elif isinstance(node, WhileStatement):
            context.block_stack.append("while")
            for child in node.body:
                issues.extend(self._visit_node(child, context))
            context.block_stack.pop()

        return issues
