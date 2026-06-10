import pytest

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.format.keyword_casing_rule import KeywordCasingRule


def _lint_with_rule(code: str, rule):
    """Helper to tokenize and lint code with a specific rule."""
    tokens = Lexer(code).tokenize()
    linter = Linter(rules=[rule])
    return linter.lint(tokens)


def test_keyword_casing_uppercase_valid():
    """Test that uppercase keywords pass uppercase rule."""
    code = "IF (x = 1); ENDIF;"
    rule = KeywordCasingRule(style="uppercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_keyword_casing_uppercase_invalid():
    """Test that lowercase keywords fail uppercase rule."""
    code = "if (x = 1); endif;"
    rule = KeywordCasingRule(style="uppercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 2
    assert "should be 'IF'" in issues[0].message
    assert "should be 'ENDIF'" in issues[1].message


def test_keyword_casing_lowercase_valid():
    """Test that lowercase keywords pass lowercase rule."""
    code = "if (x = 1); endif;"
    rule = KeywordCasingRule(style="lowercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_keyword_casing_lowercase_invalid():
    """Test that uppercase keywords fail lowercase rule."""
    code = "IF (x = 1); ENDIF;"
    rule = KeywordCasingRule(style="lowercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 2
    assert "should be 'if'" in issues[0].message
    assert "should be 'endif'" in issues[1].message


def test_keyword_casing_camelcase_valid():
    """Test that camelcase keywords pass camelcase rule."""
    code = "If (x = 1); Endif;"
    rule = KeywordCasingRule(style="camelcase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_keyword_casing_camelcase_invalid():
    """Test that uppercase keywords fail camelcase rule."""
    code = "IF (x = 1); ENDIF;"
    rule = KeywordCasingRule(style="camelcase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 2
    assert "should be 'If'" in issues[0].message
    assert "should be 'Endif'" in issues[1].message


def test_keyword_casing_mixed_keywords():
    """Test various keywords with uppercase rule."""
    code = "IF (x = 1); ELSE; ENDIF;"
    rule = KeywordCasingRule(style="uppercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_keyword_casing_invalid_style():
    """Test that invalid style raises ValueError."""
    with pytest.raises(ValueError, match="Invalid style"):
        KeywordCasingRule(style="invalid")


def test_keyword_casing_position_info():
    """Test that lint issues include correct position information."""
    code = "if (x = 1); endif;"
    rule = KeywordCasingRule(style="uppercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 2

    # First issue is 'if'
    assert issues[0].line == 1
    assert issues[0].position == 0

    # Second issue is 'endif'
    assert issues[1].line == 1
    assert issues[1].position == 12


def test_consistency_rule_all_uppercase():
    """Test consistency rule with all uppercase keywords."""
    code = "IF (x = 1); ELSE; ENDIF;"
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_consistency_rule_all_lowercase():
    """Test consistency rule with all lowercase keywords."""
    code = "if (x = 1); else; endif;"
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_consistency_rule_all_camelcase():
    """Test consistency rule with all camelcase keywords."""
    code = "If (x = 1); Else; Endif;"
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_consistency_rule_mixed_uppercase_lowercase():
    """Test consistency rule catches mixed uppercase/lowercase."""
    code = "IF (x = 1); endif;"  # IF uppercase, endif lowercase
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 1
    assert "Inconsistent keyword casing" in issues[0].message
    assert "expected uppercase" in issues[0].message
    assert "'IF'" in issues[0].message  # Shows first keyword as reference


def test_consistency_rule_mixed_camelcase_uppercase():
    """Test consistency rule catches camelcase mixed with uppercase."""
    code = "If (x = 1); ENDIF;"  # If camelcase, ENDIF uppercase
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 1
    assert "expected camelcase" in issues[0].message


def test_consistency_rule_multiple_violations():
    """Test consistency rule reports all violations."""
    code = "IF (x = 1); ELSE; endif;"  # Mixed uppercase/lowercase
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    # Should flag: endif (lowercase after uppercase IF and ELSE)
    assert len(issues) == 1


def test_consistency_rule_first_keyword_sets_standard():
    """Test that first keyword encountered sets the expected style."""
    code = "if (x = 1); endif; IF (y = 2); ENDIF;"  # First if lowercase, second IF uppercase
    rule = KeywordCasingRule(style="consistent")
    issues = _lint_with_rule(code, rule)

    # Second IF and ENDIF should be flagged as inconsistent with first 'if'
    assert len(issues) == 2
    assert all("expected lowercase" in issue.message for issue in issues)


def test_keyword_casing_with_comments():
    """Test that comments don't interfere with keyword checking."""
    code = """
    # Comment with IF in it
    IF (x = 1); # inline comment
    ENDIF;
    """
    rule = KeywordCasingRule(style="uppercase")
    issues = _lint_with_rule(code, rule)

    assert len(issues) == 0


def test_keyword_casing_preserves_other_issues():
    """Test that keyword casing rule works alongside other rules."""
    from linti.rules.format.whitespace_around_operators_rule import (
        WhitespaceAroundOperatorsRule,
    )

    code = "IF (x=1); ENDIF;"  # Uppercase keywords, but missing operator spacing

    tokens = Lexer(code).tokenize()
    linter = Linter(
        rules=[KeywordCasingRule(style="uppercase"), WhitespaceAroundOperatorsRule()]
    )
    issues = linter.lint(tokens)

    # Should only have spacing issue, not keyword issues
    keyword_issues = [i for i in issues if "Keyword" in i.message]
    spacing_issues = [i for i in issues if "space" in i.message]

    assert len(keyword_issues) == 0
    assert len(spacing_issues) > 0


@pytest.mark.parametrize(
    "code,style,expected_count",
    [
        ("IF (x = 1); ENDIF;", "uppercase", 0),
        ("if (x = 1); endif;", "lowercase", 0),
        ("If (x = 1); Endif;", "camelcase", 0),
        ("IF (x = 1); ENDIF;", "lowercase", 2),
        ("if (x = 1); endif;", "uppercase", 2),
        ("If (x = 1); Endif;", "uppercase", 2),
    ],
)
def test_keyword_casing_parametrized(code, style, expected_count):
    """Parametrized test for different keyword casing scenarios."""
    rule = KeywordCasingRule(style=style)
    issues = _lint_with_rule(code, rule)
    assert len(issues) == expected_count
