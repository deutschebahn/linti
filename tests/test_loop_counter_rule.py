"""Tests for VariablePrefixRule: allow_loop_counter_variables option."""

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.naming.naming_rule import VariablePrefixRule


def _lint(code: str, allow: bool = True) -> list:
    rule = VariablePrefixRule(allow_loop_counter_variables=allow)
    linter = Linter(statement_rules=[rule])
    return linter.lint(Lexer(code).tokenize())


def test_loop_counter_before_while_no_error():
    """Single-char numeric var directly before WHILE is allowed."""
    code = """
i = 0;
WHILE(i < 10);
  i = i + 1;
END;
"""
    assert _lint(code) == []


def test_two_loop_counters_before_while_no_error():
    """Multiple single-char counters before a WHILE are allowed."""
    code = """
i = 0;
j = 0;
WHILE(i < 10);
  i = i + 1;
  j = j + 1;
END;
"""
    assert _lint(code) == []


def test_loop_counter_without_while_flagged():
    """Single-char numeric var NOT followed by WHILE is still flagged."""
    code = "i = 0;\nnValue = 5;"
    errors = _lint(code)
    assert len(errors) == 1
    assert "i" in errors[0].message


def test_loop_counter_not_directly_before_while_flagged():
    """Single-char var separated from WHILE by another statement is flagged."""
    code = """
i = 0;
nSomething = 1;
WHILE(i < 10);
  i = i + 1;
END;
"""
    errors = _lint(code)
    assert any("i" in e.message for e in errors)


def test_loop_counter_disabled_by_default():
    """Loop counter exception is off by default — single-char var is flagged."""
    code = """
i = 0;
WHILE(i < 10);
  i = i + 1;
END;
"""
    errors = _lint(code, allow=False)
    assert len(errors) == 1
    assert "i" in errors[0].message


def test_loop_counter_reassignment_inside_while_no_error():
    """Reassignment of the counter inside the WHILE body is not flagged."""
    code = """
i = 0;
WHILE(i < 10);
  i = i + 1;
END;
"""
    assert _lint(code) == []


def test_loop_counter_nested_if_before_while_no_error():
    """Loop counter before a WHILE nested inside an IF is also exempt."""
    code = """
IF(1 = 1);
  i = 0;
  WHILE(i < 5);
    i = i + 1;
  END;
ENDIF;
"""
    assert _lint(code) == []


def test_multi_char_var_before_while_still_flagged():
    """Multi-char variables before WHILE without correct prefix are still flagged."""
    code = """
count = 0;
WHILE(count < 10);
  count = count + 1;
END;
"""
    errors = _lint(code)
    assert any("count" in e.message for e in errors)
