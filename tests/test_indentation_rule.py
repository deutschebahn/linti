from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.format.indentation_rule import IndentationRule


def _lint(code: str, indent_size: int = 4):
    tokens = Lexer(code).tokenize()
    linter = Linter(rules=[IndentationRule(indent_size=indent_size)])
    return linter.lint(tokens)


def test_indentation_ok_for_if_block():
    code = """
IF (a = 1);
    nVal = 1;
ENDIF;
"""
    issues = _lint(code)
    assert issues == []


def test_indentation_wrong_for_if_block():
    code = """
IF (a = 1);
  nVal = 1;
ENDIF;
"""
    issues = _lint(code)
    assert len(issues) == 1
    assert "Expected indentation of 4 spaces" in issues[0].message


def test_indentation_ok_for_while_block():
    code = """
WHILE (a = 1);
    nVal = 1;
END;
"""
    issues = _lint(code)
    assert issues == []


def test_indentation_respects_custom_size():
    code = """
IF (a = 1);
  nVal = 1;
ENDIF;
"""
    issues = _lint(code, indent_size=2)
    assert issues == []
