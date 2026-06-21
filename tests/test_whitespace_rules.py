"""Tests for whitespace linting rules F220–F270."""

from linti.lexer.lexer import Lexer
from linti.linter.fixer import apply_fixes, apply_fixes_iteratively
from linti.linter.linter import Linter
from linti.rules.format.no_multiple_spaces_rule import NoMultipleSpacesRule
from linti.rules.format.no_space_before_semicolon_rule import (
    NoSpaceBeforeSemicolonRule,
)
from linti.rules.format.no_trailing_whitespace_rule import NoTrailingWhitespaceRule
from linti.rules.format.one_space_inside_parentheses_rule import (
    OneSpaceInsideParenthesesRule,
)
from linti.rules.format.whitespace_after_comma_rule import WhitespaceAfterCommaRule
from linti.rules.format.whitespace_around_operators_rule import (
    WhitespaceAroundOperatorsRule,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lint(code: str, rule):
    tokens = Lexer(code).tokenize()
    linter = Linter(rules=[rule])
    return linter.lint(tokens)


def _fix(code: str, rule):
    """Lint, collect issues with fixes, apply them and return fixed code."""
    tokens = Lexer(code).tokenize()
    linter = Linter(rules=[rule])
    issues = linter.lint(tokens)
    fixed, _ = apply_fixes(code, issues)
    return fixed


def _fix_iterative(code: str, rules):
    linter = Linter(rules=rules)
    fixed, _ = apply_fixes_iteratively(code, linter)
    return fixed


# ===========================================================================
# F220 – Whitespace Around Operators
# ===========================================================================


class TestWhitespaceAroundOperators:
    rule = WhitespaceAroundOperatorsRule()

    def test_ok_assignment(self):
        assert _lint("nVar = 1;", self.rule) == []

    def test_ok_arithmetic(self):
        assert _lint("nVar = nA + nB;", self.rule) == []

    def test_ok_comparison(self):
        assert _lint("IF (a < b);", self.rule) == []

    def test_ok_string_equals(self):
        assert _lint("IF (sVal @= 'abc');", self.rule) == []

    def test_ok_logical_and(self):
        assert _lint("IF (a = 1 & b = 2);", self.rule) == []

    def test_ok_unary_minus(self):
        """Leading minus is unary and should not be flagged."""
        assert _lint("nVar = -1;", self.rule) == []

    def test_ok_unary_minus_in_expr(self):
        """Minus after LPAREN is unary."""
        assert _lint("nVar = (-1 + 2);", self.rule) == []

    def test_ok_unary_minus_after_comma(self):
        """Minus after comma is unary (negative argument)."""
        assert _lint("func(a, -1);", self.rule) == []

    def test_missing_space_before_operator(self):
        issues = _lint("nVar= 1;", self.rule)
        assert len(issues) == 1
        assert "before '='" in issues[0].message
        assert issues[0].rule_id == "F220"

    def test_missing_space_after_operator(self):
        issues = _lint("nVar =1;", self.rule)
        assert len(issues) == 1
        assert "after '='" in issues[0].message

    def test_missing_space_both_sides(self):
        issues = _lint("nVar=1;", self.rule)
        assert len(issues) == 2

    def test_multiple_spaces_before_operator(self):
        issues = _lint("nVar  = 1;", self.rule)
        assert len(issues) == 1
        assert "before '='" in issues[0].message

    def test_multiple_spaces_after_operator(self):
        issues = _lint("nVar =  1;", self.rule)
        assert len(issues) == 1
        assert "after '='" in issues[0].message

    def test_fix_inserts_missing_space_before(self):
        fixed = _fix("nVar= 1;", self.rule)
        assert fixed == "nVar = 1;"

    def test_fix_inserts_missing_space_after(self):
        fixed = _fix("nVar =1;", self.rule)
        assert fixed == "nVar = 1;"

    def test_fix_replaces_multiple_spaces_before(self):
        fixed = _fix("nVar  = 1;", self.rule)
        assert fixed == "nVar = 1;"

    def test_fix_replaces_multiple_spaces_after(self):
        fixed = _fix("nVar =  1;", self.rule)
        assert fixed == "nVar = 1;"

    def test_fix_no_space_arithmetic(self):
        fixed = _fix("nVar = nA+nB;", self.rule)
        assert fixed == "nVar = nA + nB;"

    def test_from_config_disabled(self):
        instances = WhitespaceAroundOperatorsRule.from_config(
            {"around_operators": False}
        )
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = WhitespaceAroundOperatorsRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert WhitespaceAroundOperatorsRule().RULE_ID == "F220"


# ===========================================================================
# F230 – Whitespace After Comma
# ===========================================================================


class TestWhitespaceAfterComma:
    rule = WhitespaceAfterCommaRule()

    def test_ok_with_space(self):
        assert _lint("func(a, b, c);", self.rule) == []

    def test_ok_comma_at_eol(self):
        """Comma at end of line (multi-line arg list) is exempt."""
        code = "func(a,\n    b);"
        assert _lint(code, self.rule) == []

    def test_ok_single_arg(self):
        assert _lint("func(a);", self.rule) == []

    def test_missing_space_after_comma(self):
        issues = _lint("func(a,b,c);", self.rule)
        assert len(issues) == 2
        assert all(i.rule_id == "F230" for i in issues)
        assert all("after ','" in i.message for i in issues)

    def test_multiple_spaces_after_comma(self):
        issues = _lint("func(a,  b);", self.rule)
        assert len(issues) == 1
        assert "after ','" in issues[0].message

    def test_fix_inserts_missing_space(self):
        fixed = _fix("func(a,b,c);", self.rule)
        assert fixed == "func(a, b, c);"

    def test_fix_replaces_multiple_spaces(self):
        fixed = _fix("func(a,  b);", self.rule)
        assert fixed == "func(a, b);"

    def test_from_config_disabled(self):
        instances = WhitespaceAfterCommaRule.from_config({"after_comma": False})
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = WhitespaceAfterCommaRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert WhitespaceAfterCommaRule().RULE_ID == "F230"


# ===========================================================================
# F240 – No Space Before Semicolon
# ===========================================================================


class TestNoSpaceBeforeSemicolon:
    rule = NoSpaceBeforeSemicolonRule()

    def test_ok_no_space(self):
        assert _lint("nVar = 1;", self.rule) == []

    def test_ok_multiple_statements(self):
        assert _lint("nA = 1;\nnB = 2;", self.rule) == []

    def test_space_before_semicolon(self):
        issues = _lint("nVar = 1 ;", self.rule)
        assert len(issues) == 1
        assert issues[0].rule_id == "F240"
        assert "before ';'" in issues[0].message

    def test_multiple_spaces_before_semicolon(self):
        issues = _lint("nVar = 1   ;", self.rule)
        assert len(issues) == 1

    def test_fix_removes_space(self):
        fixed = _fix("nVar = 1 ;", self.rule)
        assert fixed == "nVar = 1;"

    def test_fix_removes_multiple_spaces(self):
        fixed = _fix("nVar = 1   ;", self.rule)
        assert fixed == "nVar = 1;"

    def test_from_config_disabled(self):
        instances = NoSpaceBeforeSemicolonRule.from_config(
            {"no_space_before_semicolon": False}
        )
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = NoSpaceBeforeSemicolonRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert NoSpaceBeforeSemicolonRule().RULE_ID == "F240"


# ===========================================================================
# F250 – One Space Inside Parentheses
# ===========================================================================


class TestOneSpaceInsideParentheses:
    rule = OneSpaceInsideParenthesesRule()

    def test_ok_one_space_each_side(self):
        assert _lint("func( a, b );", self.rule) == []

    def test_ok_empty_parens(self):
        assert _lint("func();", self.rule) == []

    def test_ok_multiline_open_paren(self):
        """Opening paren followed by newline is exempt (multi-line arg list)."""
        code = "func(\n    a\n);"
        assert _lint(code, self.rule) == []

    def test_missing_space_after_open_paren(self):
        issues = _lint("func(a, b );", self.rule)
        assert len(issues) == 1
        assert issues[0].rule_id == "F250"
        assert "after '('" in issues[0].message

    def test_missing_space_before_close_paren(self):
        issues = _lint("func( a, b);", self.rule)
        assert len(issues) == 1
        assert "before ')'" in issues[0].message

    def test_missing_spaces_both_sides(self):
        issues = _lint("func(a, b);", self.rule)
        assert len(issues) == 2

    def test_multiple_spaces_after_open_paren(self):
        issues = _lint("func(  a, b );", self.rule)
        assert len(issues) == 1
        assert "after '('" in issues[0].message

    def test_fix_inserts_space_after_open_paren(self):
        fixed = _fix("func(a, b );", self.rule)
        assert fixed == "func( a, b );"

    def test_fix_inserts_space_before_close_paren(self):
        fixed = _fix("func( a, b);", self.rule)
        assert fixed == "func( a, b );"

    def test_fix_inserts_spaces_both_sides(self):
        fixed = _fix_iterative("func(a, b);", [OneSpaceInsideParenthesesRule()])
        assert fixed == "func( a, b );"

    def test_fix_normalises_multiple_spaces(self):
        fixed = _fix("func(  a, b );", self.rule)
        assert fixed == "func( a, b );"

    def test_from_config_disabled(self):
        instances = OneSpaceInsideParenthesesRule.from_config(
            {"one_space_inside_parentheses": False}
        )
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = OneSpaceInsideParenthesesRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert OneSpaceInsideParenthesesRule().RULE_ID == "F250"


# ===========================================================================
# F260 – No Multiple Consecutive Spaces
# ===========================================================================


class TestNoMultipleSpaces:
    rule = NoMultipleSpacesRule()

    def test_ok_single_spaces(self):
        assert _lint("nVar = 1;", self.rule) == []

    def test_ok_indentation_is_exempt(self):
        """Leading whitespace on a line is indentation — must not be flagged."""
        code = "IF (a = 1);\n    nVar = 1;\nENDIF;"
        assert _lint(code, self.rule) == []

    def test_multiple_spaces_before_operator(self):
        issues = _lint("nVar  = 1;", self.rule)
        assert len(issues) == 1
        assert issues[0].rule_id == "F260"
        assert "Multiple consecutive spaces" in issues[0].message

    def test_multiple_spaces_after_operator(self):
        issues = _lint("nVar =  1;", self.rule)
        assert len(issues) == 1

    def test_fix_replaces_with_single_space(self):
        fixed = _fix("nVar  = 1;", self.rule)
        assert fixed == "nVar = 1;"

    def test_from_config_disabled(self):
        instances = NoMultipleSpacesRule.from_config({"no_multiple_spaces": False})
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = NoMultipleSpacesRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert NoMultipleSpacesRule().RULE_ID == "F260"


# ===========================================================================
# F270 – No Trailing Whitespace
# ===========================================================================


class TestNoTrailingWhitespace:
    rule = NoTrailingWhitespaceRule()

    def test_ok_no_trailing_space(self):
        assert _lint("nVar = 1;\n", self.rule) == []

    def test_ok_no_trailing_space_eof(self):
        assert _lint("nVar = 1;", self.rule) == []

    def test_trailing_space(self):
        issues = _lint("nVar = 1;   \n", self.rule)
        assert len(issues) == 1
        assert issues[0].rule_id == "F270"
        assert "Trailing whitespace" in issues[0].message

    def test_trailing_tab(self):
        issues = _lint("nVar = 1;\t\n", self.rule)
        assert len(issues) == 1

    def test_fix_removes_trailing_spaces(self):
        fixed = _fix("nVar = 1;   \n", self.rule)
        assert fixed == "nVar = 1;\n"

    def test_fix_removes_trailing_tab(self):
        fixed = _fix("nVar = 1;\t\n", self.rule)
        assert fixed == "nVar = 1;\n"

    def test_blank_line_with_spaces(self):
        """Blank lines that contain only spaces should be flagged."""
        code = "nA = 1;\n   \nnB = 2;\n"
        issues = _lint(code, self.rule)
        assert len(issues) == 1

    def test_from_config_disabled(self):
        instances = NoTrailingWhitespaceRule.from_config(
            {"no_trailing_whitespace": False}
        )
        assert instances == []

    def test_from_config_enabled_default(self):
        instances = NoTrailingWhitespaceRule.from_config({})
        assert len(instances) == 1

    def test_rule_id(self):
        assert NoTrailingWhitespaceRule().RULE_ID == "F270"


# ===========================================================================
# Integration: all 6 rules together
# ===========================================================================


class TestAllWhitespaceRulesIntegration:
    """Smoke tests that combine multiple whitespace rules."""

    all_rules = [
        WhitespaceAroundOperatorsRule(),
        WhitespaceAfterCommaRule(),
        NoSpaceBeforeSemicolonRule(),
        OneSpaceInsideParenthesesRule(),
        NoMultipleSpacesRule(),
        NoTrailingWhitespaceRule(),
    ]

    def test_clean_code_no_issues(self):
        code = "nVar = nA + nB;\nIF ( sVal @= 'x' );\n    func( a, b );\nENDIF;\n"
        tokens = Lexer(code).tokenize()
        linter = Linter(rules=self.all_rules)
        assert linter.lint(tokens) == []

    def test_combined_fixes_converge(self):
        """Messy code is fully fixed after iterative auto-fix."""
        messy = "nVar=nA+nB ;\n"
        linter = Linter(rules=self.all_rules)
        fixed, _ = apply_fixes_iteratively(messy, linter)
        # Check no remaining issues
        tokens = Lexer(fixed).tokenize()
        remaining = linter.lint(tokens)
        assert remaining == []
