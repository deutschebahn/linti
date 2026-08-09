"""High-level linting operations on ProcessIR and providers."""

from linti.semantic.constant_evaluation import ConstantEvaluationIndex
from linti.linter.fixer import auto_fix_process
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.linter.lint_issue import LintIssue, Severity
from linti.linter.parse_cache import SectionParseCache
from linti.linter.reporter import ProcedureIssue
from linti.model.process_ir import ProcessIR, extract_procedures
from linti.provider.base import ProcessProvider
from linti.rules.Rule import RuleMetadata

# Pseudo rule id for the parser-level "nesting too deep" diagnostic. Not a
# registry rule — enforced in the parser, surfaced here as a LintIssue.
NESTING_DEPTH_RULE_ID = "P900"

# METADATA for the pseudo-rule above. There is no rule class to carry this
# (nothing to `interested_in()` — the parser bails before an AST exists for
# the affected procedure), so `cli/rule_explainer.py` and
# `scripts/generate_all_rules.py` merge this in manually alongside the real,
# registry-derived rules.
NESTING_DEPTH_METADATA = RuleMetadata(
    name="Maximum Nesting Depth Exceeded",
    description=(
        "Flags a procedure whose control-flow nesting exceeded the "
        "configured limit, stopping the parser before it could build a full "
        "AST for that section"
    ),
    auto_fix=False,
    severity=Severity.WARNING,
    explanation=(
        "TI's IF/WHILE nesting is parsed recursively; without a cap, "
        "pathologically deep nesting would recurse until Python's own "
        "RecursionError, crashing the run instead of reporting a clean "
        "diagnostic. `max_nesting_depth` (top-level config key, default 150) "
        "caps that recursion; once a procedure's nesting exceeds it, the "
        "parser aborts the section and this diagnostic reports the drop.\n\n"
        "This safety cap itself cannot be turned off — only how loud linti is "
        "about hitting it. `rules.nesting_depth.enabled: false` silences the "
        "diagnostic, but the procedure is still dropped from linting exactly "
        "the same; the cap keeps applying either way. Raise "
        "`max_nesting_depth` if your codebase genuinely nests deeper than the "
        "default.\n\n"
        "Unlike every other rule, this diagnostic is enforced directly in "
        "the parser rather than by a rule module — there is nothing to "
        "`--select` or scan for in the AST, since the AST for the affected "
        "procedure was never built. Only `rules.nesting_depth.enabled` and "
        "`rules.nesting_depth.severity` control it."
    ),
    config_example=(
        "rules:\n"
        "  nesting_depth:\n"
        "    enabled: true    # hides the diagnostic only — the cap always applies\n"
        "    severity: warning"
    ),
)


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
            # The section could not be parsed at all, so no rule ever sees it.
            # Suppressing the diagnostic therefore drops the procedure silently
            # — which is the point of `rules.nesting_depth.enabled: false`.
            if linter.nesting_depth_enabled:
                issue = LintIssue(
                    message=str(parsed.error),
                    line=1,
                    column=1,
                    position=0,
                    rule_id=NESTING_DEPTH_RULE_ID,
                    severity=linter.nesting_depth_severity,
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
