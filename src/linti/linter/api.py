"""High-level linting operations on ProcessIR and providers."""

from typing import Callable, Optional

from linti.semantic.constant_evaluation import ConstantEvaluationIndex
from linti.linter.fixer import auto_fix_process
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.linter.lint_issue import LintIssue
from linti.linter.parse_cache import SectionParseCache
from linti.linter.reporter import ProcedureIssue
from linti.model.process_ir import ProcessIR, extract_procedures
from linti.provider.base import ProcessProvider

# Pseudo rule id for the parser-level "nesting too deep" diagnostic. Not a
# registry rule — enforced in the parser, surfaced here as a LintIssue.
NESTING_DEPTH_RULE_ID = "S900"


def lint_process_model(process: ProcessIR, linter: Linter) -> list[ProcedureIssue]:
    """Lint one process model and return procedure-scoped issues."""
    all_issues: list[ProcedureIssue] = []

    # Lex/parse each section at most once per run: the lint loop populates
    # this cache and the index reads from it instead of re-parsing.
    parse_cache = SectionParseCache(process, max_nesting_depth=linter.max_nesting_depth)
    # One shared index per process; it builds lazily on first rule access.
    constants = ConstantEvaluationIndex(
        process,
        cache=parse_cache,
        max_values_per_variable=linter.max_values_per_variable,
    )

    for proc_name, proc_info in extract_procedures(process).items():
        lint_ctx = LintContext.for_procedure(process, proc_name, proc_info, constants)
        parsed = parse_cache.get(proc_name)
        if parsed.error is not None:
            issue = LintIssue(
                message=str(parsed.error),
                line=1,
                column=1,
                position=0,
                rule_id=NESTING_DEPTH_RULE_ID,
            )
            all_issues.append((proc_name, issue, proc_info.source_line))
            continue
        issues = linter.lint(
            parsed.tokens, lint_ctx, ast=parsed.ast, source=proc_info.code
        )
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
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> dict[str, list[ProcedureIssue]]:
    """Lint all provider-backed processes and return results keyed by name.

    Processes are visited in sorted order so iteration, write and error order
    stay deterministic even when the provider's listing is unordered (a remote
    provider returns whatever the server sends).

    *on_error* controls what a per-process failure does. Left at ``None`` the
    first failure propagates, which is what a single-process file run wants.
    A callback receives ``(process_name, exception)`` and lets the run continue
    with the remaining processes — relevant for a provider spanning hundreds of
    processes, where one unreadable process must not hide the rest. There is
    deliberately no "ignore errors" flag: continuing requires the caller to say
    what happens to the failure.
    """
    results: dict[str, list[ProcedureIssue]] = {}
    for process_name in sorted(provider.list_processes()):
        try:
            results.update(
                lint_process(provider, process_name, linter, auto_fix=auto_fix)
            )
        except Exception as exc:
            if on_error is None:
                raise
            on_error(process_name, exc)
    return results
