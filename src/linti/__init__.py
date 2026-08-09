"""linti — minimal public API for TM1py integration."""

from linti.linter.api import lint_all, lint_process
from linti.linter.lint_issue import Fix, LintIssue, Severity
from linti.linter.linter import Linter
from linti.linter.reporter import (
    directory_report_exit_code,
    file_report_exit_code,
    filter_by_severity,
    render_directory_report,
    render_file_report,
)
from linti.rules.rule_factory import create_rules

__all__ = [
    # TM1 provider
    "TM1Provider",
    # Linting core
    "Linter",
    "create_rules",
    "lint_all",
    "lint_process",
    "render_file_report",
    "render_directory_report",
    # Issues
    "Fix",
    "LintIssue",
    # Severity
    "Severity",
    "filter_by_severity",
    "file_report_exit_code",
    "directory_report_exit_code",
]
