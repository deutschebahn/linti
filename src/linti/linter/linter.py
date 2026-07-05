from linti.lexer.token_window import TokenWindow
from linti.linter.lint_context import LintContext
from linti.linter.noqa import filter_issues, parse_noqa
from linti.parser.parser import DEFAULT_MAX_NESTING_DEPTH, Parser
from linti.provider.base import DEFAULT_MAX_FILE_SIZE
from linti.rules.Rule import BaseRule, BaseStatementRule


class Linter:
    def __init__(
        self,
        rules: list[BaseRule] = None,
        statement_rules: list[BaseStatementRule] = None,
        max_nesting_depth: int = DEFAULT_MAX_NESTING_DEPTH,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ):
        """
        Initialize the linter with token-based and statement-based rules.

        Args:
            rules: List of token-based rules (BaseRule instances).
            statement_rules: List of AST statement-based rules (BaseStatementRule instances).
            max_nesting_depth: Control-flow nesting cap forwarded to the parser.
            max_file_size: File-size ceiling (bytes) carried for the CLI flows
                that construct providers from a pre-built linter.
        """
        self.max_nesting_depth = max_nesting_depth
        self.max_file_size = max_file_size
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
                issues.extend(rule.visit(token, window, context))

        if ast is None:
            ast = Parser(tokens, max_nesting_depth=self.max_nesting_depth).parse()

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
            issues.extend(rule.visit(node, context))

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
