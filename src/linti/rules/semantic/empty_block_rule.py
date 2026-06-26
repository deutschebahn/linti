from linti.lexer.token import TokenType
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.parser.ast import IfStatement, WhileStatement
from linti.rules.Rule import BaseStatementRule, RuleExample, RuleMetadata

# Keywords that terminate a branch when scanning an (already known to be
# empty) body for comments and the fix span.
_IF_BODY_TERMINATORS = frozenset({TokenType.ELSEIF, TokenType.ELSE, TokenType.ENDIF})
_ELSE_BODY_TERMINATORS = frozenset({TokenType.ENDIF})
_WHILE_BODY_TERMINATORS = frozenset({TokenType.END})


class EmptyBlockRule(BaseStatementRule):
    """
    Flags control-flow blocks (IF/ELSEIF/ELSE/WHILE) that contain no
    executable code — i.e. blocks that are completely empty or hold only
    comments.

    Empty branches are usually leftover scaffolding or a sign of an
    incomplete refactor.  Auto-fix removes a block only when deleting it is
    completely safe and discards nothing meaningful:

    - an empty ELSE, or an empty WHILE (the whole ``WHILE ... END;``);
    - an empty ELSEIF *only* when it is the last branch — otherwise the
      condition it swallows would fall through to a following ELSEIF/ELSE and
      change behaviour.

    Everything else (empty IF, ELSEIF that is not the last branch, or any
    block holding a comment) is reported only.

    Emptiness is read straight from the AST (an empty body parses to an empty
    statement list, comments included since the parser drops them).  The raw
    token stream from the lint context is consulted only for the two things
    the AST cannot answer: whether the block held a comment, and the exact
    source span to delete for an auto-fix.
    """

    CONFIG_KEY = "empty_block"
    METADATA = RuleMetadata(
        name="Empty Block",
        description="Flags IF/ELSEIF/ELSE/WHILE blocks that contain no executable code",
        auto_fix=True,
        explanation=(
            "Flags control-flow blocks (IF/ELSEIF/ELSE/WHILE) that contain no "
            "executable code, either because they are completely empty or "
            "because they hold only comments.\n\n"
            "Auto-fix removes a block only when it is completely empty (no "
            "comments) and deletion is safe: an empty ELSE, an empty WHILE "
            "(including its END;), or an empty ELSEIF that is the last branch. "
            "An empty ELSEIF followed by another ELSEIF/ELSE is reported only — "
            "removing it would change behaviour — as is any empty IF or any "
            "block that still holds a comment."
        ),
        config_example=("rules:\n  empty_block:\n    enabled: true"),
        examples=[
            RuleExample(
                code="IF (nValue = 1);\n    nResult = 10;\nENDIF;",
                description="IF block with executable code",
                valid=True,
            ),
            RuleExample(
                code="IF (nValue = 1);\n    nResult = 10;\nELSE;\nENDIF;",
                description="Empty ELSE block (auto-fixable: branch removed)",
                valid=False,
            ),
            RuleExample(
                code="IF (nValue = 1);\nENDIF;",
                description="Empty IF block",
                valid=False,
            ),
            RuleExample(
                code="WHILE (nValue < 10);\n    # todo\nEND;",
                description="WHILE block with only a comment",
                valid=False,
            ),
        ],
    )

    @property
    def RULE_ID(self) -> str:
        return "S130"

    def interested_in(self):
        return [IfStatement, WhileStatement]

    def visit(self, statement, context: LintContext):
        if isinstance(statement, WhileStatement):
            return self._visit_while(statement, context)
        return self._visit_if(statement, context)

    def _visit_if(self, node: IfStatement, context: LintContext):
        issues = []

        # THEN body — the node's own keyword is IF (top level) or ELSEIF
        # (nested branch, visited in its own right by the linter).
        if not node.then_body:
            is_elseif = node.token is not None and node.token.type == TokenType.ELSEIF
            label = "ELSEIF" if is_elseif else "IF"
            # An empty ELSEIF is safe to drop only as the LAST branch.  An empty
            # ELSEIF silently swallows its condition and stops the chain, so with
            # a following ELSEIF/ELSE removing it would let that condition fall
            # through and change behaviour.  "Last branch" == no nested ELSEIF in
            # else_body and no ELSE.
            deletable = is_elseif and not node.else_body and node.else_token is None
            issue = self._make_issue(
                node.token,
                label,
                _IF_BODY_TERMINATORS,
                context,
                deletable=deletable,
                terminator_inclusive=False,
            )
            if issue:
                issues.append(issue)

        # ELSE body — distinguishable from "no ELSE" only via else_token.
        if node.else_token is not None and not node.else_body:
            issue = self._make_issue(
                node.else_token,
                "ELSE",
                _ELSE_BODY_TERMINATORS,
                context,
                deletable=True,
                terminator_inclusive=False,
            )
            if issue:
                issues.append(issue)

        return issues

    def _visit_while(self, node: WhileStatement, context: LintContext):
        if node.body:
            return []
        # A WHILE owns its closing END; — unlike a branch, the terminator is
        # part of what gets removed.
        issue = self._make_issue(
            node.token,
            "WHILE",
            _WHILE_BODY_TERMINATORS,
            context,
            deletable=True,
            terminator_inclusive=True,
        )
        return [issue] if issue else []

    def _make_issue(
        self, keyword, label, terminators, context, deletable, terminator_inclusive
    ):
        """Build the issue (and fix) for an empty block opened by ``keyword``."""
        if keyword is None:
            return None

        tokens = context.tokens or []
        has_comment, terminator = self._scan_empty_body(tokens, keyword, terminators)

        detail = " (contains only comments)" if has_comment else ""
        issue = LintIssue(
            message=f"{label} block has no executable code{detail}",
            line=keyword.line,
            column=keyword.column,
            position=keyword.position,
            rule_id=self.RULE_ID,
        )

        # Only delete completely empty (comment-free) blocks: removing one then
        # changes no behaviour and discards no comment.  The text is sliced from
        # the source (token values drop string quotes, so they cannot
        # reconstruct the span reliably).
        if (
            deletable
            and not has_comment
            and terminator is not None
            and context.source is not None
        ):
            end = self._removal_end(tokens, terminator, terminator_inclusive)
            removed = context.source[keyword.position : end]
            issue.fix = Fix(position=keyword.position, old_value=removed, new_value="")

        return issue

    @staticmethod
    def _removal_end(tokens, terminator, inclusive):
        """Char offset where a block's removal span ends.

        Branches stop *before* their terminator (the ENDIF/next clause belongs
        to the enclosing IF and must stay).  A WHILE owns its closing ``END;``,
        so its span runs up to and including that terminating ``;``.
        """
        if not inclusive:
            return terminator.position
        for tok in tokens:
            if tok.position > terminator.position and tok.type == TokenType.SEMICOLON:
                return tok.position + len(tok.value)
        return terminator.position + len(terminator.value)

    @staticmethod
    def _scan_empty_body(tokens, keyword, terminators):
        """Find an empty block's terminator and whether it holds a comment.

        The body is already known to be empty (the AST carried no statements),
        so between the keyword and the terminator there is only the header, plus
        whitespace, newlines or comments — no nested blocks, and no comment can
        sit inside the header's parentheses.  That lets us scan purely by source
        position from the keyword onwards: the first terminator-typed token ends
        the branch, and any COMMENT seen on the way is the body's comment.

        Returns ``(has_comment, terminator_token)``; ``terminator_token`` is
        ``None`` when the stream ends before a terminator (malformed input).
        """
        has_comment = False
        for tok in tokens:
            if tok.position <= keyword.position:
                continue
            if tok.type in terminators:
                return has_comment, tok
            if tok.type == TokenType.COMMENT:
                has_comment = True
        return has_comment, None
