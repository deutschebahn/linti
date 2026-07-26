"""Tests for the noqa suppression mechanism.

Tests cover:
1. Inline (trailing) comment suppression
2. Standalone comment suppression (next line)
3. Procedure-level (global) suppression
4. Region suppression (noqa-begin / noqa-end)
5. Multiple rule IDs
6. Case insensitivity
7. Integration with the full linter pipeline
"""

import pytest

from linti.config import LintiConfigWarning
from linti.lexer.lexer import Lexer
from linti.lexer.token import Token, TokenType
from linti.linter.lint_issue import LintIssue
from linti.linter.linter import Linter
from linti.linter.noqa import (
    NoqaDirectives,
    _find_next_code_line,
    _is_standalone_comment,
    _parse_rule_ids,
    filter_issues,
    parse_noqa,
)
from linti.rules.format.keyword_casing_rule import KeywordCasingRule
from linti.rules.format.whitespace_around_operators_rule import (
    WhitespaceAroundOperatorsRule,
)
from linti.rules.naming.naming_rule import VariablePrefixRule
from linti.rules.semantic.conditional_control_flow_rule import (
    ConditionalControlFlowRule,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _tokenize(code: str) -> list[Token]:
    return Lexer(code).tokenize()


def _lint(code: str, rules=None) -> list[LintIssue]:
    """Lint *code* with full noqa support via the Linter pipeline."""
    tokens = _tokenize(code)
    if rules is None:
        rules = [KeywordCasingRule(style="uppercase")]
    linter = Linter(rules=rules)
    return linter.lint(tokens)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestParseRuleIds:
    def test_single(self):
        assert _parse_rule_ids("F110") == {"F110"}

    def test_multiple(self):
        assert _parse_rule_ids("F110, C220, N110") == {"F110", "C220", "N110"}

    def test_case_normalisation(self):
        assert _parse_rule_ids("f110, c220") == {"F110", "C220"}

    def test_deprecated_id_resolved_to_canonical(self):
        """A deprecated ID is normalised to the canonical ID it maps to."""
        with pytest.warns(LintiConfigWarning, match="S220 is deprecated"):
            assert _parse_rule_ids("S220") == {"C220"}

    def test_deprecated_id_resolution_is_case_insensitive(self):
        with pytest.warns(LintiConfigWarning):
            assert _parse_rule_ids("s220") == {"C220"}

    def test_extra_whitespace(self):
        assert _parse_rule_ids("  F110 ,  C220  ") == {"F110", "C220"}

    def test_empty(self):
        assert _parse_rule_ids("") == set()


class TestIsStandaloneComment:
    def test_first_token(self):
        tokens = _tokenize("# comment\nnVar = 1;")
        idx = next(i for i, t in enumerate(tokens) if t.type == TokenType.COMMENT)
        assert _is_standalone_comment(tokens, idx) is True

    def test_standalone_after_newline(self):
        tokens = _tokenize("nVar = 1;\n# comment\nnVar2 = 2;")
        idx = next(i for i, t in enumerate(tokens) if t.type == TokenType.COMMENT)
        assert _is_standalone_comment(tokens, idx) is True

    def test_trailing_comment(self):
        tokens = _tokenize("nVar = 1; # comment")
        idx = next(i for i, t in enumerate(tokens) if t.type == TokenType.COMMENT)
        assert _is_standalone_comment(tokens, idx) is False


class TestFindNextCodeLine:
    def test_finds_next_code(self):
        tokens = _tokenize("# comment\nnVar = 1;")
        idx = next(i for i, t in enumerate(tokens) if t.type == TokenType.COMMENT)
        assert _find_next_code_line(tokens, idx) is not None

    def test_no_code_after(self):
        tokens = _tokenize("# comment")
        idx = next(i for i, t in enumerate(tokens) if t.type == TokenType.COMMENT)
        assert _find_next_code_line(tokens, idx) is None


# ---------------------------------------------------------------------------
# Unit tests for NoqaDirectives
# ---------------------------------------------------------------------------


class TestNoqaDirectives:
    def test_empty_not_suppressed(self):
        d = NoqaDirectives()
        assert d.is_suppressed("F110", 1) is False

    def test_global_suppression(self):
        d = NoqaDirectives(global_suppressions={"F110"})
        assert d.is_suppressed("F110", 1) is True
        assert d.is_suppressed("F110", 99) is True
        assert d.is_suppressed("C220", 1) is False

    def test_line_suppression(self):
        d = NoqaDirectives(line_suppressions={5: {"F110", "C220"}})
        assert d.is_suppressed("F110", 5) is True
        assert d.is_suppressed("C220", 5) is True
        assert d.is_suppressed("F110", 6) is False

    def test_case_insensitive_lookup(self):
        d = NoqaDirectives(global_suppressions={"F110"})
        assert d.is_suppressed("f110", 1) is True


# ---------------------------------------------------------------------------
# Unit tests for filter_issues
# ---------------------------------------------------------------------------


class TestFilterIssues:
    def test_filters_suppressed(self):
        issues = [
            LintIssue("msg1", line=5, column=1, position=0, rule_id="F110"),
            LintIssue("msg2", line=5, column=1, position=0, rule_id="C220"),
            LintIssue("msg3", line=10, column=1, position=0, rule_id="F110"),
        ]
        directives = NoqaDirectives(line_suppressions={5: {"F110"}})
        result = filter_issues(issues, directives)
        assert len(result) == 2
        assert result[0].rule_id == "C220"
        assert result[1].rule_id == "F110"
        assert result[1].line == 10

    def test_filters_global(self):
        issues = [
            LintIssue("msg1", line=1, column=1, position=0, rule_id="F110"),
            LintIssue("msg2", line=99, column=1, position=0, rule_id="F110"),
            LintIssue("msg3", line=50, column=1, position=0, rule_id="C220"),
        ]
        directives = NoqaDirectives(global_suppressions={"F110"})
        result = filter_issues(issues, directives)
        assert len(result) == 1
        assert result[0].rule_id == "C220"


# ---------------------------------------------------------------------------
# parse_noqa integration tests
# ---------------------------------------------------------------------------


class TestParseNoqaInline:
    """Trailing (inline) comment: ``code; # noqa: RULE``"""

    def test_inline_suppresses_current_line(self):
        code = "if(nVar = 1); # noqa: F110"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # The 'if' keyword is on line 1
        assert directives.is_suppressed("F110", 1) is True
        assert directives.is_suppressed("F110", 2) is False

    def test_inline_multiple_rules(self):
        code = "nVar=1; # noqa: F220, N110"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        assert directives.is_suppressed("F220", 1) is True
        assert directives.is_suppressed("N110", 1) is True
        assert directives.is_suppressed("C220", 1) is False


class TestParseNoqaStandalone:
    """Standalone comment: suppresses the *next* code line."""

    def test_standalone_suppresses_next_line(self):
        code = "nVar = 1;\n# noqa: F110\nif(nVar = 1);"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # Line 1 should NOT be suppressed
        assert directives.is_suppressed("F110", 1) is False
        # Line 3 (if) should be suppressed
        assert directives.is_suppressed("F110", 3) is True

    def test_standalone_only_suppresses_next_code_line(self):
        code = "nVar = 1;\n# noqa: F110\n\nif(nVar = 1);\nendif;"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # The next code line after the noqa comment
        next_code_line = None
        for t in tokens:
            if t.type not in (
                TokenType.COMMENT,
                TokenType.WHITESPACE,
                TokenType.NEWLINE,
            ):
                if t.line > 2:
                    next_code_line = t.line
                    break
        assert next_code_line is not None
        assert directives.is_suppressed("F110", next_code_line) is True


class TestParseNoqaProcedureLevel:
    """First standalone # noqa before any code → procedure-level suppression."""

    def test_procedure_level_suppression(self):
        code = "# noqa: F110\nif(nVar = 1);\nendif;"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # Should suppress F110 everywhere
        assert directives.is_suppressed("F110", 1) is True
        assert directives.is_suppressed("F110", 2) is True
        assert directives.is_suppressed("F110", 3) is True
        assert directives.is_suppressed("F110", 999) is True
        # Other rules not affected
        assert directives.is_suppressed("C220", 1) is False

    def test_procedure_level_multiple_rules(self):
        code = "# noqa: F110, C220\nif(nVar = 1);\nendif;"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        assert directives.is_suppressed("F110", 5) is True
        assert directives.is_suppressed("C220", 5) is True

    def test_non_first_standalone_is_not_procedure_level(self):
        code = "nVar = 1;\n# noqa: F110\nif(nVar = 1);"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # Line 1 should NOT be suppressed (not procedure-level)
        assert directives.is_suppressed("F110", 1) is False
        # Only line 3 should be suppressed (next-line behaviour)
        assert directives.is_suppressed("F110", 3) is True


class TestParseNoqaRegion:
    """Region suppression: noqa-begin / noqa-end."""

    def test_region_suppresses_lines_in_between(self):
        code = (
            "nVar = 1;\n"
            "# noqa-begin: F110\n"
            "if(nVar = 1);\n"
            "endif;\n"
            "# noqa-end: F110\n"
            "IF(nVar = 2);\n"
            "ENDIF;"
        )
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        # Line 1 before region: NOT suppressed
        assert directives.is_suppressed("F110", 1) is False
        # Lines inside region
        assert directives.is_suppressed("F110", 3) is True
        assert directives.is_suppressed("F110", 4) is True
        # Lines after region: NOT suppressed
        assert directives.is_suppressed("F110", 6) is False
        assert directives.is_suppressed("F110", 7) is False

    def test_region_accepts_a_deprecated_rule_id(self):
        """A deprecated ID in a region marker suppresses the canonical rule."""
        code = "# noqa-begin: S220\ncRate = 1.5;\n# noqa-end: S220\n"
        tokens = _tokenize(code)
        with pytest.warns(LintiConfigWarning, match="S220 is deprecated"):
            directives = parse_noqa(tokens)
        assert directives.is_suppressed("C220", 2) is True

    def test_region_only_suppresses_specified_rule(self):
        code = "# noqa-begin: F110\nif(nVar = 1);\n# noqa-end: F110\n"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        assert directives.is_suppressed("F110", 2) is True
        assert directives.is_suppressed("C220", 2) is False

    def test_unclosed_region_extends_to_eof(self):
        code = "# noqa-begin: F110\nif(nVar = 1);\nendif;\nif(nVar = 2);\nendif;"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        assert directives.is_suppressed("F110", 2) is True
        assert directives.is_suppressed("F110", 3) is True
        assert directives.is_suppressed("F110", 4) is True
        assert directives.is_suppressed("F110", 5) is True

    def test_multiple_rules_in_region(self):
        code = "# noqa-begin: F110, N110\nif(nVar = 1);\n# noqa-end: F110, N110\n"
        tokens = _tokenize(code)
        directives = parse_noqa(tokens)
        assert directives.is_suppressed("F110", 2) is True
        assert directives.is_suppressed("N110", 2) is True


# ---------------------------------------------------------------------------
# Full linter integration tests
# ---------------------------------------------------------------------------


class TestNoqaIntegration:
    """End-to-end tests through the Linter pipeline."""

    def test_inline_suppresses_casing_issue(self):
        code = "if(nVar = 1); # noqa: F110\nENDIF;"
        issues = _lint(code)
        # 'if' on line 1 is suppressed; 'ENDIF' on line 2 should still flag
        # Actually with uppercase rule — 'if' is the violation, 'ENDIF' is fine
        assert "F110" not in [i.rule_id for i in issues if i.line == 1]

    def test_diagnostics_report_the_canonical_rule_id(self):
        """A renamed rule reports its new ID, and that ID suppresses it."""
        rules = [WhitespaceAroundOperatorsRule()]
        issues = _lint("nVar=1;", rules=rules)
        assert issues and {i.rule_id for i in issues} == {"F220"}
        assert _lint("nVar=1; # noqa: F220", rules=rules) == []

    def test_deprecated_id_suppresses_the_canonical_rule(self):
        """An old ID keeps working for one deprecation cycle, with a warning."""
        code = "\nnValue = 5;\nProcessQuit();\n"
        linter = Linter(statement_rules=[ConditionalControlFlowRule()])

        tokens = _tokenize(code)
        assert [i.rule_id for i in linter.lint(tokens)] == ["C120"]

        tokens = _tokenize(
            code.replace("ProcessQuit();", "ProcessQuit(); # noqa: S110")
        )
        with pytest.warns(LintiConfigWarning, match="S110 is deprecated"):
            issues = linter.lint(tokens)
        assert issues == []

    def test_standalone_suppresses_next_line(self):
        code = "# noqa: F110\nif(nVar = 1);\nENDIF;"
        # Procedure-level: suppresses F110 everywhere
        issues = _lint(code)
        assert all(i.rule_id != "F110" for i in issues)

    def test_region_suppresses_block(self):
        code = (
            "# noqa-begin: F110\n"
            "if(nVar = 1);\n"
            "endif;\n"
            "# noqa-end: F110\n"
            "if(nVar = 2);\n"
            "endif;"
        )
        issues = _lint(code)
        # Issues inside region (lines 2-3) should be suppressed
        region_issues = [i for i in issues if i.rule_id == "F110" and 2 <= i.line <= 3]
        assert len(region_issues) == 0
        # Issues outside region (lines 5-6) should remain
        outside_issues = [i for i in issues if i.rule_id == "F110" and i.line >= 5]
        assert len(outside_issues) > 0

    def test_procedure_level_suppresses_all(self):
        code = "# noqa: F110\nif(nVar = 1);\nendif;\nif(nVar = 2);\nendif;"
        issues = _lint(code)
        f110_issues = [i for i in issues if i.rule_id == "F110"]
        assert len(f110_issues) == 0

    def test_noqa_does_not_affect_other_rules(self):
        code = "count = 1; # noqa: F110"
        rules = [KeywordCasingRule(style="uppercase")]
        stmt_rules = [VariablePrefixRule()]
        tokens = _tokenize(code)
        linter = Linter(rules=rules, statement_rules=stmt_rules)
        issues = linter.lint(tokens)
        # F110 is suppressed, but N110 (variable prefix) should still fire
        n_issues = [i for i in issues if i.rule_id == "N110"]
        assert len(n_issues) > 0

    def test_no_noqa_leaves_issues_intact(self):
        code = "if(nVar = 1);\nendif;"
        issues = _lint(code)
        # Without noqa all violations should remain
        assert len(issues) > 0

    def test_case_insensitive_noqa(self):
        code = "if(nVar = 1); # NOQA: f110\nENDIF;"
        issues = _lint(code)
        line1_f110 = [i for i in issues if i.rule_id == "F110" and i.line == 1]
        assert len(line1_f110) == 0
