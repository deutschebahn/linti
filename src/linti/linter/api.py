"""High-level linting operations on ProcessIR and providers."""

from linti.lexer.lexer import Lexer
from linti.linter.fixer import auto_fix_process
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.linter.lint_issue import LintIssue
from linti.linter.reporter import ProcedureIssue
from linti.model.process_ir import ProcessIR, extract_procedures
from linti.parser.parser import NestingDepthExceeded, Parser
from linti.provider.base import ProcessProvider

# Pseudo rule id for the parser-level "nesting too deep" diagnostic. Not a
# registry rule — enforced in the parser, surfaced here as a LintIssue.
NESTING_DEPTH_RULE_ID = "S900"


def lint_process_model(process: ProcessIR, linter: Linter) -> list[ProcedureIssue]:
    """Lint one process model and return procedure-scoped issues."""
    all_issues: list[ProcedureIssue] = []

    for proc_name, proc_info in extract_procedures(process).items():
        lint_ctx = LintContext(
            block=proc_name,
            process_name=process.name,
            parameters=process.parameters,
            parameter_lines=process.parameter_lines,
            variables=process.variables,
            variable_lines=process.variable_lines,
            block_start_line=proc_info.source_line,
            block_end_line=proc_info.source_end_line,
        )
        tokens = Lexer(proc_info.code).tokenize()
        try:
            ast = Parser(tokens, max_nesting_depth=linter.max_nesting_depth).parse()
        except NestingDepthExceeded as e:
            issue = LintIssue(
                message=str(e),
                line=1,
                column=1,
                position=0,
                rule_id=NESTING_DEPTH_RULE_ID,
            )
            all_issues.append((proc_name, issue, proc_info.source_line))
            continue
        issues = linter.lint(tokens, lint_ctx, ast=ast, source=proc_info.code)
        for issue in issues:
            all_issues.append((proc_name, issue, proc_info.source_line))

    return all_issues


def lint_process(
    provider: ProcessProvider,
    process_name: str,
    linter: Linter,
    auto_fix: bool = False,
) -> dict[str, list[ProcedureIssue]]:
    """Lint one process and return results keyed by process name."""
    process = provider.get_process(process_name)

    if auto_fix:
        fixes_by_proc = auto_fix_process(process, linter)
        if fixes_by_proc:
            provider.save_process(process)
            process = provider.get_process(process_name)

    return {process_name: lint_process_model(process, linter)}


def lint_all(
    provider: ProcessProvider,
    linter: Linter,
    auto_fix: bool = False,
) -> dict[str, list[ProcedureIssue]]:
    """Lint all provider-backed processes and return results keyed by name."""
    results: dict[str, list[ProcedureIssue]] = {}
    for process_name in provider.list_processes():
        results[process_name] = lint_process(
            provider,
            process_name,
            linter,
            auto_fix=auto_fix,
        )
    return results
