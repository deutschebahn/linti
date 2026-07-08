"""Tests for auto-fixer functionality."""

import tempfile
from pathlib import Path

from linti.cli.file_linter import auto_fix_file
from linti.linter.fixer import (
    apply_fixes,
    apply_fixes_iteratively,
    collect_fixable_issues,
)
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import Fix, LintIssue
from linti.linter.linter import Linter
from linti.rules.format.indentation_rule import IndentationRule
from linti.rules.format.keyword_casing_rule import KeywordCasingRule
from linti.rules.format.newline_per_statement_rule import NewLinePerStatementRule

# --- Helper ---


def _fix(code: str, style: str = "uppercase", context=None) -> tuple[str, int]:
    """Lint code, collect fixable issues, and apply fixes."""
    rule = KeywordCasingRule(style=style)
    linter = Linter(rules=[rule])
    issues = collect_fixable_issues(code, linter, context)
    return apply_fixes(code, issues)


# --- Unit tests for apply_fixes ---


def test_apply_fixes_with_single_fix():
    """Test applying a single fix."""
    code = "if (x = 1);"
    issues = [
        LintIssue(
            message="test",
            line=1,
            column=1,
            position=0,
            rule_id="F110",
            fix=Fix(position=0, old_value="if", new_value="IF"),
        )
    ]
    fixed_code, num_fixes = apply_fixes(code, issues)
    assert fixed_code == "IF (x = 1);"
    assert num_fixes == 1


def test_apply_fixes_skips_issues_without_fix():
    """Test that issues without a fix are skipped."""
    code = "if (x = 1);"
    issues = [LintIssue(message="no fix", line=1, column=1, position=0, rule_id="X001")]
    fixed_code, num_fixes = apply_fixes(code, issues)
    assert fixed_code == code
    assert num_fixes == 0


def test_apply_fixes_with_no_issues():
    """Test applying fixes with empty issue list."""
    code = "IF (x = 1);"
    fixed_code, num_fixes = apply_fixes(code, [])
    assert fixed_code == code
    assert num_fixes == 0


def test_apply_fixes_counts_only_applied_fixes():
    """A fix skipped on old_value mismatch must not be counted as applied."""
    code = "if (x = 1);"
    issues = [
        LintIssue(
            message="applied",
            line=1,
            column=1,
            position=0,
            rule_id="F110",
            fix=Fix(position=0, old_value="if", new_value="IF"),
        ),
        LintIssue(
            message="stale",
            line=1,
            column=5,
            position=4,
            rule_id="F110",
            # old_value does not match the text at this position -> skipped
            fix=Fix(position=4, old_value="zzz", new_value="YYY"),
        ),
    ]
    fixed_code, num_fixes = apply_fixes(code, issues)
    assert fixed_code == "IF (x = 1);"
    assert num_fixes == 1


# --- Integration tests: keyword casing via collect + apply ---


def test_keyword_casing_fixes_uppercase():
    """Test applying uppercase fixes to code with lowercase keywords."""
    fixed_code, num_fixes = _fix("if (x = 1);\n    nResult = 2;\nendif;")

    assert num_fixes == 2
    assert "IF (x = 1);" in fixed_code
    assert "ENDIF;" in fixed_code
    assert "nResult" in fixed_code


def test_keyword_casing_fixes_lowercase():
    """Test applying lowercase fixes to code with uppercase keywords."""
    fixed_code, num_fixes = _fix(
        "IF (x = 1);\n    nResult = 2;\nENDIF;", style="lowercase"
    )

    assert num_fixes == 2
    assert "if (x = 1);" in fixed_code
    assert "endif;" in fixed_code
    assert "nResult" in fixed_code


def test_keyword_casing_fixes_camelcase():
    """Test applying camelcase fixes to code with mixed keywords."""
    fixed_code, num_fixes = _fix(
        "if (x = 1);\n    nResult = 2;\nENDIF;", style="camelcase"
    )

    assert num_fixes == 2
    assert "If (x = 1);" in fixed_code
    assert "Endif;" in fixed_code


def test_keyword_casing_fixes_no_issues():
    """Test that code with correct casing returns unchanged with 0 fixes."""
    code = "IF (x = 1);\n    nResult = 2;\nENDIF;"
    fixed_code, num_fixes = _fix(code)

    assert num_fixes == 0
    assert fixed_code == code


def test_keyword_casing_fixes_while_end():
    """Test fixing WHILE and END keywords."""
    fixed_code, num_fixes = _fix("while (x > 0);\n    x = x - 1;\nend;")

    assert num_fixes == 2
    assert "WHILE (x > 0);" in fixed_code
    assert "END;" in fixed_code


def test_keyword_casing_fixes_nested_if():
    """Test fixing nested IF statements."""
    code = "if (x = 1);\n    if (y = 2);\n        z = 3;\n    endif;\nendif;"
    fixed_code, num_fixes = _fix(code)

    assert num_fixes == 4
    assert "IF (x = 1);" in fixed_code
    assert "IF (y = 2);" in fixed_code
    assert fixed_code.count("ENDIF") == 2


def test_keyword_casing_fixes_preserves_spacing():
    """Test that fixing preserves original spacing and indentation."""
    code = "  if   (x = 1)  ;\n        nResult = 2;\n  endif  ;\n"
    fixed_code, num_fixes = _fix(code)

    assert num_fixes == 2
    assert "  IF   (x = 1)  ;" in fixed_code
    assert "        nResult = 2;" in fixed_code
    assert "  ENDIF  ;" in fixed_code


def test_keyword_casing_fixes_with_context():
    """Test fixing with LintContext (parameters and variables)."""
    code = "if (pParam = 1);\n    vVariable = 2;\nendif;"
    context = LintContext(
        block="prolog", parameters=["pParam"], variables=["vVariable"]
    )
    fixed_code, num_fixes = _fix(code, context=context)

    assert num_fixes == 2
    assert "IF (pParam = 1);" in fixed_code
    assert "vVariable = 2;" in fixed_code


def test_keyword_casing_fixes_else_statement():
    """Test fixing ELSE statements."""
    fixed_code, num_fixes = _fix("if (x = 1);\n    y = 2;\nelse;\n    y = 3;\nendif;")

    assert num_fixes == 3
    assert "IF (x = 1);" in fixed_code
    assert "ELSE;" in fixed_code
    assert "ENDIF;" in fixed_code


def test_keyword_casing_fixes_complex_code():
    """Test fixing complex code with multiple keyword types."""
    code = """nCounter = 0;
while (nCounter < 10);
    if (nCounter = 5);
        ProcessBreak();
    else;
        nCounter = nCounter + 1;
    endif;
end;
"""
    fixed_code, num_fixes = _fix(code)

    assert num_fixes == 5
    assert "WHILE (nCounter < 10);" in fixed_code
    assert "IF (nCounter = 5);" in fixed_code
    assert "ELSE;" in fixed_code
    assert "ENDIF;" in fixed_code
    assert "END;" in fixed_code
    assert "ProcessBreak();" in fixed_code
    assert "nCounter" in fixed_code


def test_auto_fix_yaml_preserves_blank_line_without_spaces():
    """Ensure YAML auto-fix keeps blank lines truly empty (no added two-space padding)."""
    yaml_content = """!TM1py.ProcessObject
Name: Example
PrologProcedure: |-
  if (a = 1);
   nValue = 1;

  endif;
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "process.yaml"
        file_path.write_text(yaml_content)

        linter = Linter(rules=[KeywordCasingRule(style="uppercase"), IndentationRule()])

        fixes_by_proc = auto_fix_file(file_path, linter)
        fixed_content = file_path.read_text()

        assert fixes_by_proc.get("prolog", 0) > 0
        assert "\n\n  ENDIF;\n" in fixed_content
        assert "\n  \n  ENDIF;\n" not in fixed_content


def test_combined_keyword_and_newline_fixes():
    """Test that keyword casing and newline fixes work together on the same line."""
    code = "a = 1;iF(a=1);a = b;ENDif;"
    linter = Linter(
        rules=[KeywordCasingRule(style="lowercase"), NewLinePerStatementRule()]
    )
    issues = collect_fixable_issues(code, linter)
    fixed_code, num_fixes = apply_fixes(code, issues)

    assert "if" in fixed_code, "iF should be fixed to if"
    assert "endif" in fixed_code, "ENDif should be fixed to endif"
    assert "iF" not in fixed_code
    assert "ENDif" not in fixed_code
    assert num_fixes >= 4  # 2 keyword + at least 2 newline fixes


def test_iterative_fixes_resolve_indentation_after_newlines():
    """A later pass should fix indentation revealed by newline insertion."""
    code = "a = 1;iF(a=1);a = b;ENDif;"
    linter = Linter(
        rules=[
            KeywordCasingRule(style="lowercase"),
            NewLinePerStatementRule(),
            IndentationRule(),
        ]
    )

    fixed_code, num_fixes = apply_fixes_iteratively(code, linter)

    assert fixed_code == "a = 1;\nif(a=1);\n    a = b;\nendif;"
    assert num_fixes >= 5


def test_auto_fix_ti_file_runs_multiple_passes():
    """File auto-fix should resolve indentation in the same command run."""
    code = "a = 1;iF(a=1);a = b;ENDif;"

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "process.ti"
        file_path.write_text(code)

        linter = Linter(
            rules=[
                KeywordCasingRule(style="lowercase"),
                NewLinePerStatementRule(),
                IndentationRule(),
            ]
        )

        fixes_by_proc = auto_fix_file(file_path, linter)
        fixed_code = file_path.read_text()

        assert fixed_code == "a = 1;\nif(a=1);\n    a = b;\nendif;"
        assert sum(fixes_by_proc.values()) >= 5


def test_auto_fix_context_wires_constant_evaluation():
    """Auto-fix rules see the same cross-section constants as the lint pass.

    A possible_values-based rule linted through auto_fix_process must resolve a
    value assigned in an earlier section, just as it does through
    lint_process_model — otherwise it would compute fixes with less information
    than it reports with.
    """
    from linti.linter.fixer import auto_fix_process
    from linti.model.process_ir import ProcedureInfo, ProcessIR
    from linti.parser.ast import Assignment
    from linti.rules.Rule import BaseStatementRule

    seen: dict[str, object] = {}

    class _Spy(BaseStatementRule):
        @property
        def RULE_ID(self) -> str:
            return "T999"

        def interested_in(self):
            return [Assignment]

        def visit(self, statement, context):
            seen[context.block] = context.possible_values("sDim", 99).exact
            return []

    process = ProcessIR(
        name="p",
        prolog=ProcedureInfo(code="sDim = 'Region:Default';"),
        data=ProcedureInfo(code="nX = 1;"),
    )
    auto_fix_process(process, Linter(statement_rules=[_Spy()]))

    # The Prolog value is visible while the Data block is being fixed.
    assert seen["data"] == "Region:Default"
