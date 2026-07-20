"""Tests for DocstringRegionRule (D110)."""

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.rules.documentation.docstring_region_rule import DocstringRegionRule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lint(code: str, context: LintContext | None = None):
    """Tokenise *code* and run DocstringRegionRule against it."""
    if context is None:
        context = LintContext(block="prolog")
    tokens = Lexer(code).tokenize()
    rule = DocstringRegionRule()
    linter = Linter(rules=[rule])
    return linter.lint(tokens, context)


def _lint_with_rule(
    code: str, rule: DocstringRegionRule, context: LintContext | None = None
):
    """Tokenise *code* and run the provided *rule*."""
    if context is None:
        context = LintContext(block="prolog")
    tokens = Lexer(code).tokenize()
    linter = Linter(rules=[rule])
    return linter.lint(tokens, context)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rule_id():
    assert DocstringRegionRule().RULE_ID == "D110"


def test_default_disabled():
    assert DocstringRegionRule.DEFAULT_ENABLED is False


def test_ok_with_docstring_and_description_header():
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# does something useful\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    errors = _lint(code)
    assert errors == []


def test_ok_multiple_headers():
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# does something\n"
        "# Author:\n"
        "# Alice\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    errors = _lint(code)
    assert errors == []


def test_ok_no_executable_code():
    """Prolog with only comments and no semicolons should not trigger."""
    code = "# Just a comment, no code"
    errors = _lint(code)
    assert errors == []


def test_ok_docstring_only_no_code():
    """Well-formed docstring but no executable code – still OK."""
    code = "#Region - Docstring\n# Description:\n# nothing\n#EndRegion - Docstring\n"
    errors = _lint(code)
    assert errors == []


def test_missing_docstring_reports_at_semicolon():
    code = "nVar = 1;"
    errors = _lint(code)
    assert len(errors) == 1
    assert "D110" in errors[0].rule_id
    assert "Expected" in errors[0].message
    assert "Docstring" in errors[0].message


def test_missing_docstring_only_reported_once():
    """Running into multiple statements should still produce only one issue."""
    code = "nVar = 1;\nnOther = 2;"
    errors = _lint(code)
    assert len(errors) == 1


def test_unclosed_region_reports_at_semicolon():
    code = "#Region - Docstring\n# Description:\n# something\nnVar = 1;"
    errors = _lint(code)
    assert len(errors) == 1
    assert "D110" in errors[0].rule_id
    assert "not closed" in errors[0].message.lower()


def test_missing_required_header():
    code = "#Region - Docstring\n# Author: me\n#EndRegion - Docstring\nnVar = 1;"
    errors = _lint(code)
    assert len(errors) == 1
    assert "D110" in errors[0].rule_id
    assert "# Description" in errors[0].message


def test_non_prolog_block_ignored():
    """Rule must not fire in metadata, data, or epilog blocks."""
    code = "nVar = 1;"
    for block in ("metadata", "data", "epilog"):
        errors = _lint(code, LintContext(block=block))
        assert errors == [], f"Unexpected issue in block={block!r}"


def test_non_prolog_none_block_ignored():
    errors = _lint("nVar = 1;", LintContext(block=None))
    assert errors == []


def test_generic_process_requires_extra_header():
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# a core process\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    rule = DocstringRegionRule(
        generic_prefixes=["}core."],
        generic_extra_headers=["# Use Case"],
    )
    ctx = LintContext(block="prolog", process_name="}core.some.process")
    errors = _lint_with_rule(code, rule, ctx)
    assert len(errors) == 1
    assert "# Use Case" in errors[0].message


def test_generic_process_ok_with_all_headers():
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# a core process\n"
        "# Use Case:\n"
        "# migration\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    rule = DocstringRegionRule(
        generic_prefixes=["}core."],
        generic_extra_headers=["# Use Case"],
    )
    ctx = LintContext(block="prolog", process_name="}core.some.process")
    errors = _lint_with_rule(code, rule, ctx)
    assert errors == []


def test_non_generic_does_not_need_extra_header():
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# normal process\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    rule = DocstringRegionRule(
        generic_prefixes=["}core."],
        generic_extra_headers=["# Use Case"],
    )
    ctx = LintContext(block="prolog", process_name="MyNormalProcess")
    errors = _lint_with_rule(code, rule, ctx)
    assert errors == []


def test_custom_region_name():
    code = (
        "#Region - Header\n# Description:\n# something\n#EndRegion - Header\nnVar = 1;"
    )
    rule = DocstringRegionRule(region_name="Header")
    errors = _lint_with_rule(code, rule)
    assert errors == []


def test_custom_region_name_mismatch_reports_issue():
    """Using default region name when custom name expected → missing docstring."""
    code = (
        "#Region - Docstring\n"
        "# Description:\n"
        "# something\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    rule = DocstringRegionRule(region_name="Header")
    errors = _lint_with_rule(code, rule)
    assert len(errors) == 1
    assert "Header" in errors[0].message


def test_header_with_colon_only_is_accepted():
    """The bare header may optionally end with a colon."""
    code = "#Region - Docstring\n# Description:\n#EndRegion - Docstring\nnVar = 1;"
    errors = _lint(code)
    assert errors == []


def test_header_with_inline_content_is_not_accepted():
    """Header content must be on following lines, not on the header line."""
    code = (
        "#Region - Docstring\n"
        "# Description: lots of detail here\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    errors = _lint(code)
    assert len(errors) == 1
    assert "# Description" in errors[0].message


def test_from_config_creates_instance():
    rules = DocstringRegionRule.from_config(
        {
            "region_name": "Docstring",
            "required_headers": ["# Description"],
            "generic_prefixes": [],
            "generic_extra_headers": [],
        }
    )
    assert len(rules) == 1
    assert isinstance(rules[0], DocstringRegionRule)


def test_from_config_defaults():
    rules = DocstringRegionRule.from_config({})
    assert len(rules) == 1
    r = rules[0]
    assert r._region_name == "Docstring"
    assert "# Description" in r._required_headers


def test_reset_clears_state():
    code = (
        "#Region - Docstring\n# Description:\n# ok\n#EndRegion - Docstring\nnVar = 1;"
    )
    rule = DocstringRegionRule()
    ctx = LintContext(block="prolog")
    linter = Linter(rules=[rule])
    tokens = Lexer(code).tokenize()

    # First pass should be clean
    errors1 = linter.lint(tokens, ctx)
    assert errors1 == []

    # Second pass (linter calls reset()) should also be clean
    errors2 = linter.lint(tokens, ctx)
    assert errors2 == []


def test_generated_statements_boilerplate_ignored():
    """The #****Begin/End: Generated Statements markers must not interfere."""
    code = (
        "#****Begin: Generated Statements***\n"
        "#****End: Generated Statements***\n"
        "#Region - Docstring\n"
        "# Description:\n"
        "# something\n"
        "#EndRegion - Docstring\n"
        "nVar = 1;"
    )
    errors = _lint(code)
    assert errors == []
