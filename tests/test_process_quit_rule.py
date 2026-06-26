"""Tests for ProcessQuitRule."""

from linti.lexer.lexer import Lexer
from linti.linter.linter import Linter
from linti.rules.semantic.process_quit_rule import ProcessQuitRule


def test_process_quit_at_end_of_if_block():
    """Test that ProcessQuit() at the end of an if block is allowed."""
    code = """
    IF (nValue = 1);
        nResult = 10;
        ProcessQuit();
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 0


def test_process_quit_at_end_of_else_block():
    """Test that ProcessQuit() at the end of an else block is allowed."""
    code = """
    IF (nValue = 1);
        nResult = 10;
    ELSE;
        nResult = 20;
        ProcessQuit();
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 0


def test_process_quit_with_unreachable_code_in_if():
    """Test that ProcessQuit() followed by code in an if block is flagged."""
    code = """
    IF (nValue = 1);
        ProcessQuit();
        nResult = 10;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "unreachable" in errors[0].message.lower()


def test_process_quit_with_unreachable_code_in_else():
    """Test that ProcessQuit() followed by code in an else block is flagged."""
    code = """
    IF (nValue = 1);
        nResult = 10;
    ELSE;
        ProcessQuit();
        nResult = 20;
        sMessage = 'test';
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "2 unreachable statement" in errors[0].message


def test_process_quit_at_end_of_main_body():
    """Test that ProcessQuit() in main body is not allowed (even at the end)."""
    code = """
    nValue = 5;
    sMessage = 'test';
    ProcessQuit();
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "main program body" in errors[0].message


def test_process_quit_with_unreachable_code_in_main():
    """Test that ProcessQuit() in main body is flagged (not allowed at all)."""
    code = """
    nValue = 5;
    ProcessQuit();
    sMessage = 'test';
    nResult = 10;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "main program body" in errors[0].message


def test_process_quit_case_insensitive():
    """Test that ProcessQuit check is case-insensitive."""
    code = """
    IF (nValue = 1);
        processquit();
        nResult = 10;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id


def test_process_quit_nested_if_statements():
    """Test ProcessQuit in nested if statements."""
    code = """
    IF (nValue = 1);
        IF (nOther = 2);
            ProcessQuit();
            nResult = 999;
        ENDIF;
        nResult = 10;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    # Should find unreachable code in the nested IF (nResult = 999)
    # but nResult = 10 is reachable (it's in the outer IF after the inner IF)
    assert len(errors) == 1
    assert "S110" in errors[0].rule_id


def test_multiple_process_quit_calls():
    """Test multiple ProcessQuit calls in different blocks."""
    code = """
    IF (nValue = 1);
        ProcessQuit();
        nResult = 10;
    ELSE;
        ProcessQuit();
        nResult = 20;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()

    rule = ProcessQuitRule()
    linter = Linter(statement_rules=[rule])
    errors = linter.lint(tokens)

    # Both blocks have unreachable code
    assert len(errors) == 2
    assert all("S110" in err.rule_id for err in errors)


def test_process_quit_without_parens_valid():
    """Test that ProcessQuit without parentheses at the end of an IF block is allowed."""
    code = """
    IF (nValue = 1);
        nResult = 10;
        ProcessQuit;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()
    errors = Linter(statement_rules=[ProcessQuitRule()]).lint(tokens)

    assert len(errors) == 0


def test_process_quit_without_parens_unreachable():
    """Test that ProcessQuit without parentheses followed by code is flagged."""
    code = """
    IF (nValue = 1);
        ProcessQuit;
        nResult = 10;
    ENDIF;
    """

    tokens = Lexer(code).tokenize()
    errors = Linter(statement_rules=[ProcessQuitRule()]).lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "unreachable" in errors[0].message.lower()


def test_process_quit_without_parens_in_main_body():
    """Test that ProcessQuit without parentheses in main body is flagged."""
    code = """
    nValue = 5;
    ProcessQuit;
    """

    tokens = Lexer(code).tokenize()
    errors = Linter(statement_rules=[ProcessQuitRule()]).lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "main program body" in errors[0].message


def test_process_quit_with_string_not_equal_operator():
    """Test that ProcessQuit inside an IF using @<> is correctly detected."""
    code = """
    IF (cString @<> 'ABC');
        ProcessQuit;
        LogOutput('INFO', 'msg');
    ENDIF;
    """

    tokens = Lexer(code).tokenize()
    errors = Linter(statement_rules=[ProcessQuitRule()]).lint(tokens)

    assert len(errors) == 1
    assert "S110" in errors[0].rule_id
    assert "unreachable" in errors[0].message.lower()


def test_process_quit_with_string_equals_operator():
    """Test that ProcessQuit inside an IF using @= is correctly detected."""
    code = """
    IF (cString @= 'ABC');
        ProcessQuit();
    ENDIF;
    """

    tokens = Lexer(code).tokenize()
    errors = Linter(statement_rules=[ProcessQuitRule()]).lint(tokens)

    assert len(errors) == 0
