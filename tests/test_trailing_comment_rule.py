"""Tests for P120 – trailing comment after code on the same line."""

import pytest

from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.format.whitespace_around_operators_rule import (
    WhitespaceAroundOperatorsRule,
)
from linti.rules.parser.trailing_comment_rule import TrailingCommentRule


def _lint(code: str, rules=None):
    linter = Linter(rules=rules or [TrailingCommentRule()])
    return linter.lint(Lexer(code).tokenize(), source=code)


def _fix(code: str) -> str:
    fixed, _ = apply_fixes_iteratively(code, Linter(rules=[TrailingCommentRule()]))
    return fixed


class TestDetection:
    @pytest.mark.parametrize(
        "code",
        [
            "# comment\nnVar = 1;",
            "    # indented comment\nnVar = 1;",
            "nVar = 1;\n# comment on its own line\n",
            "sX = 'not # a comment';",
            "sX = 'a';\n\n   # comment\n",
        ],
    )
    def test_comment_on_its_own_line_is_fine(self, code):
        assert _lint(code) == []

    @pytest.mark.parametrize(
        "code",
        [
            "nVar = 1; # comment",
            "nVar = 1;# comment",
            "IF(nVar = 1);\nENDIF; # comment",
            "nA = 1; nB = 2; # comment",
        ],
    )
    def test_trailing_comment_is_reported(self, code):
        issues = _lint(code)
        assert [i.rule_id for i in issues] == ["P120"]
        assert "noqa" not in issues[0].message

    def test_location_points_at_the_comment(self):
        (issue,) = _lint("nA = 1;\n  nVar = 1;  # comment")
        assert (issue.line, issue.column) == (2, 14)

    def test_trailing_noqa_is_called_out(self):
        (issue,) = _lint("nVar=1; # noqa: F220")
        assert "this noqa has no effect" in issue.message


class TestAutoFix:
    def test_moves_comment_above_the_code(self):
        assert _fix("nVar = 1;  # note\n") == "# note\nnVar = 1;\n"

    def test_keeps_indentation(self):
        code = "IF(1 = 1);\n    nVar = 1; # note\nENDIF;\n"
        expected = "IF(1 = 1);\n    # note\n    nVar = 1;\nENDIF;\n"
        assert _fix(code) == expected

    def test_line_with_string_literal(self):
        code = "sX = 'it''s'; # note\n"
        assert _fix(code) == "# note\nsX = 'it''s';\n"

    def test_fixed_code_lints_clean(self):
        fixed = _fix("nA = 1; # one\nnB = 2; nC = 3; # two\n")
        assert _lint(fixed) == []

    def test_continuation_line_is_not_fixed(self):
        code = "nVar = 1 +\n  2; # note\n"
        (issue,) = _lint(code)
        assert issue.fix is None

    @pytest.mark.parametrize("marker", ["noqa-begin", "noqa-end"])
    def test_region_markers_are_not_fixed(self, marker):
        (issue,) = _lint(f"nA = 1;\nnVar = 1; # {marker}: F220\n")
        assert issue.fix is None

    def test_noqa_on_first_code_line_is_not_fixed(self):
        """Moved above the first code line it would become procedure-wide."""
        (issue,) = _lint("nVar=1; # noqa: F220\nnB=2;\n")
        assert issue.fix is None

    def test_moved_noqa_takes_effect(self):
        code = "nA = 1;\nnVar=1; # noqa: F220\n"
        f220 = [WhitespaceAroundOperatorsRule()]
        assert _lint(code, rules=f220)  # trailing noqa does not suppress

        fixed = _fix(code)
        assert fixed == "nA = 1;\n# noqa: F220\nnVar=1;\n"
        assert _lint(fixed, rules=f220) == []
