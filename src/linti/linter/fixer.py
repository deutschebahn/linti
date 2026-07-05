"""Programmatic auto-fixing of TI code and ProcessIR objects."""

from typing import Optional

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR, extract_procedures

MAX_AUTO_FIX_PASSES = 10


def apply_fixes(code: str, issues: list[LintIssue]) -> tuple[str, int]:
    """Apply all fixable issues to code.

    Replaces text at positions specified by each issue's Fix object.
    Works with any rule that provides a Fix — no rule-specific logic needed.

    Returns:
        Tuple of (fixed_code, num_fixes_applied)
    """
    fixable = [issue for issue in issues if issue.fix is not None]

    if not fixable:
        return code, 0

    fixable.sort(key=lambda i: (-i.fix.position, len(i.fix.old_value) == 0))

    fixed_code = code
    applied = 0
    for issue in fixable:
        fix = issue.fix
        start = fix.position
        end = start + len(fix.old_value)
        if fixed_code[start:end] == fix.old_value:
            fixed_code = fixed_code[:start] + fix.new_value + fixed_code[end:]
            applied += 1

    return fixed_code, applied


def collect_fixable_issues(
    code: str, linter: Linter, lint_context: Optional[LintContext] = None
) -> list[LintIssue]:
    """Lint code and return only the fixable issues."""
    tokens = Lexer(code).tokenize()
    issues = linter.lint(tokens, lint_context, source=code)
    return [issue for issue in issues if issue.fix is not None]


def apply_fixes_iteratively(
    code: str,
    linter: Linter,
    lint_context: Optional[LintContext] = None,
    max_passes: int = MAX_AUTO_FIX_PASSES,
) -> tuple[str, int]:
    """Apply fixable issues repeatedly until no more fixes remain.

    Returns:
        Tuple of (fixed_code, total_num_fixes_applied)
    """
    fixed_code = code
    total_fixes = 0

    for _ in range(max_passes):
        issues = collect_fixable_issues(fixed_code, linter, lint_context)
        if not issues:
            break

        next_code, num_fixes = apply_fixes(fixed_code, issues)
        if num_fixes == 0 or next_code == fixed_code:
            break

        fixed_code = next_code
        total_fixes += num_fixes

    return fixed_code, total_fixes


def auto_fix_process(process: ProcessIR, linter: Linter) -> dict[str, int]:
    """Auto-fix all procedures on an in-memory ProcessIR.

    Mutates *process* in place, updating each procedure's code.

    Returns:
        Dict mapping procedure names to number of fixes applied.
    """
    fixes_by_proc: dict[str, int] = {}

    for proc_name, proc_info in extract_procedures(process).items():
        lint_ctx = LintContext(
            block=proc_name,
            process_name=process.name,
            parameters=process.parameters,
            parameter_lines=process.parameter_lines,
            variables=process.variables,
            variable_lines=process.variable_lines,
            block_start_line=proc_info.source_line,
        )

        fixed_code, num_fixes = apply_fixes_iteratively(
            proc_info.code, linter, lint_ctx
        )
        if num_fixes == 0:
            continue

        fixes_by_proc[proc_name] = num_fixes
        setattr(
            process,
            proc_name,
            ProcedureInfo(
                code=fixed_code,
                source_line=proc_info.source_line,
                source_end_line=proc_info.source_end_line,
            ),
        )

    return fixes_by_proc
