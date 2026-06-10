"""Auto-fixing functionality for TM1 linter."""

from pathlib import Path
from typing import Optional

from linti.lexer.lexer import Lexer
from linti.linter.lint_context import LintContext
from linti.linter.lint_issue import LintIssue
from linti.linter.linter import Linter

MAX_AUTO_FIX_PASSES = 10


def apply_fixes(code: str, issues: list[LintIssue]) -> tuple[str, int]:
    """
    Apply all fixable issues to code.

    Replaces text at positions specified by each issue's Fix object.
    Works with any rule that provides a Fix — no rule-specific logic needed.

    Args:
        code: The original source code
        issues: List of LintIssue objects (only those with a fix are applied)

    Returns:
        Tuple of (fixed_code, num_fixes_applied)
    """
    fixable = [issue for issue in issues if issue.fix is not None]

    if not fixable:
        return code, 0

    # Sort fixes from back to front.
    # At the same position, apply replacements before insertions.
    fixable.sort(key=lambda i: (-i.fix.position, len(i.fix.old_value) == 0))

    fixed_code = code
    for issue in fixable:
        fix = issue.fix
        start = fix.position
        end = start + len(fix.old_value)

        # Verify the old value is at the expected position
        if fixed_code[start:end] == fix.old_value:
            fixed_code = fixed_code[:start] + fix.new_value + fixed_code[end:]

    return fixed_code, len(fixable)


def collect_fixable_issues(
    code: str, linter: Linter, lint_context: Optional[LintContext] = None
) -> list[LintIssue]:
    """
    Lint code and return only the fixable issues.

    Args:
        code: The TI code to analyze
        linter: Configured linter instance
        lint_context: Optional LintContext

    Returns:
        List of LintIssue objects that have a Fix
    """
    tokens = Lexer(code).tokenize()
    issues = linter.lint(tokens, lint_context)
    return [issue for issue in issues if issue.fix is not None]


def apply_fixes_iteratively(
    code: str,
    linter: Linter,
    lint_context: Optional[LintContext] = None,
    max_passes: int = MAX_AUTO_FIX_PASSES,
) -> tuple[str, int]:
    """Apply fixable issues repeatedly until no more fixes remain.

    This is needed when one fix creates the structure required for later fixes,
    for example splitting statements onto new lines before indentation can be
    computed correctly.

    Args:
        code: The original source code
        linter: Configured linter instance
        lint_context: Optional lint context
        max_passes: Safety limit to avoid infinite fix loops

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


def auto_fix_ti_file(
    file_path: Path, linter: Linter, lint_context: Optional[LintContext] = None
) -> int:
    """
    Auto-fix a TI file in place.

    Args:
        file_path: Path to the TI file
        linter: Configured linter instance
        lint_context: Optional LintContext

    Returns:
        Number of fixes applied
    """
    with open(file_path, "r") as f:
        original_code = f.read()

    fixed_code, num_fixes = apply_fixes_iteratively(original_code, linter, lint_context)

    if num_fixes > 0:
        with open(file_path, "w") as f:
            f.write(fixed_code)

    return num_fixes


def auto_fix_yaml_procedures(
    file_path: Path, process, linter: Linter
) -> dict[str, int]:
    """
    Auto-fix procedures in a YAML ProcessObject file.

    Args:
        file_path: Path to the YAML file
        process: TM1Process with procedures
        linter: Configured linter instance

    Returns:
        Dict mapping procedure names to number of fixes applied
    """
    from linti.loader.base import extract_procedures

    procedures = extract_procedures(process)
    fixes_by_proc = {}

    # Read original YAML content
    with open(file_path, "r") as f:
        yaml_lines = f.readlines()

    indent_prefix = " " * process.content_indent

    # Process each procedure
    for proc_name, proc_info in procedures.items():
        code = proc_info.code
        yaml_start_line = proc_info.source_line

        # Create context for this procedure
        lint_ctx = LintContext(
            block=proc_name,
            parameters=process.parameters,
            parameter_lines=process.parameter_lines,
            variables=process.variables,
            variable_lines=process.variable_lines,
            block_start_line=proc_info.source_line,
            block_end_line=proc_info.source_end_line,
        )

        # Apply fixes
        fixed_code, num_fixes = apply_fixes_iteratively(code, linter, lint_ctx)

        if num_fixes > 0:
            fixes_by_proc[proc_name] = num_fixes

            # Replace the procedure content in YAML
            # yaml_start_line points to where the procedure content starts (after "ProcedureName: |-")
            # We need to find where the content ends (next line at lower indent or end of file)

            content_start = yaml_start_line  # This is 1-based line number
            content_start_idx = content_start - 1  # Convert to 0-based index

            # Find end of content (next line not indented at the content level or end of file)
            content_end_idx = content_start_idx
            for j in range(content_start_idx, len(yaml_lines)):
                line = yaml_lines[j]
                # If line has content and is not indented at (or beyond) the content level, we've hit the end
                if line.strip() and not line.startswith(indent_prefix):
                    content_end_idx = j
                    break
            else:
                content_end_idx = len(yaml_lines)

            # Replace the content with fixed code
            fixed_lines = []
            for line in fixed_code.split("\n"):
                if not line and not fixed_lines:
                    # Skip leading empty lines
                    continue
                if line:
                    fixed_lines.append(f"{indent_prefix}{line}\n")
                else:
                    # Preserve blank lines without adding trailing spaces
                    fixed_lines.append("\n")

            yaml_lines[content_start_idx:content_end_idx] = fixed_lines

    # Write back the modified YAML
    if fixes_by_proc:
        with open(file_path, "w") as f:
            f.writelines(yaml_lines)

    return fixes_by_proc
