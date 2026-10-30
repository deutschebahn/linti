"""Lint and auto-fix a process given as text instead of a file path.

Backs the browser playground: the pasted source is written to a private
temporary directory so the regular providers detect the format and round-trip
fixes exactly as the CLI does. Nothing here depends on the CLI or on Typer.
"""

from __future__ import annotations

import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from linti.config import Config, LintiConfigWarning
from linti.linter.api import lint_process, lint_process_model, linter_from_config
from linti.linter.fixer import auto_fix_process
from linti.linter.reporter import adjust_line_numbers_in_message, filter_by_severity
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import require_single_process_name
from linti.provider.factory import provider_for_path
from linti.provider.pa_code import is_pa_code_content
from linti.provider.yaml_ti import _is_tm1_process_yaml

TextFormat = Literal["ti", "pa", "yaml"]

_FILE_NAMES: dict[TextFormat, str] = {
    "ti": "process.ti",
    "pa": "process.ti",
    "yaml": "process.yaml",
}


@dataclass
class TextIssue:
    """One finding, with its line mapped to the pasted text."""

    procedure: str
    rule_id: str
    message: str
    line: int
    column: int
    severity: str
    fixable: bool


@dataclass
class TextLintResult:
    """Outcome of :func:`lint_text`."""

    format: TextFormat
    process_name: str
    code: str
    fixes: dict[str, int]
    issues: list[TextIssue]
    warnings: list[str] = field(default_factory=list)


@dataclass
class RuleTextResult:
    """One selected rule run against a procedure with optional process context."""

    code: str
    fixes: int
    issues: list[TextIssue]
    warnings: list[str] = field(default_factory=list)


def detect_format(text: str) -> TextFormat:
    """Guess the process format of *text*.

    PA-code markers win, then a TM1 process YAML document; anything else is a
    ``.ti`` file (plain or with ``#region`` sections).
    """
    if is_pa_code_content(text):
        return "pa"
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return "ti"
    if isinstance(data, dict) and _is_tm1_process_yaml(text, data):
        return "yaml"
    return "ti"


def config_from_text(config_text: str | None) -> Config:
    """Build a :class:`Config` from ``linti.yaml`` content (empty → defaults)."""
    if not config_text or not config_text.strip():
        return Config()
    try:
        data = yaml.safe_load(config_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid linti.yaml: {exc}") from exc
    if data is None:
        return Config()
    if not isinstance(data, dict):
        raise TypeError("Invalid linti.yaml: expected a mapping at the top level")
    config_path = Path("linti.yaml")
    Config._warn_about_removed_rule_configs(data, config_path)
    Config._warn_about_moved_rule_configs(data, config_path)
    return Config(**data)


def _check_text_size(text: str, max_bytes: int) -> None:
    size = len(text.encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"Input exceeds size limit ({size} > {max_bytes} bytes)")


def lint_rule_text(
    source: str,
    procedure: str,
    rule_id: str,
    config_text: str | None = None,
    *,
    auto_fix: bool = False,
    parameters: list[str] | None = None,
    variables: list[str] | None = None,
    datasource_type: str | None = None,
    datasource_query: str | None = None,
) -> RuleTextResult:
    """Lint a selected rule using the same limits and severity filter as lint_text."""
    if procedure not in {"prolog", "metadata", "data", "epilog"}:
        raise ValueError(f"Unknown procedure: {procedure}")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", LintiConfigWarning)
        cfg = config_from_text(config_text)
        _check_text_size(source, cfg.max_file_size)
        linter = linter_from_config(cfg, rule_id)
        process = ProcessIR(
            name="playground",
            parameters=list(parameters or []),
            variables=list(variables or []),
            datasource_type=datasource_type or None,
            datasource_query=datasource_query or None,
            **{procedure: ProcedureInfo(code=source)},
        )
        fixes = sum(auto_fix_process(process, linter).values()) if auto_fix else 0
        issues = filter_by_severity(
            lint_process_model(process, linter), cfg.min_severity
        )

    return RuleTextResult(
        code=getattr(process, procedure).code,
        fixes=fixes,
        warnings=[str(warning.message) for warning in caught],
        issues=[
            TextIssue(
                procedure=proc_name,
                rule_id=issue.rule_id,
                message=issue.message,
                line=issue.line,
                column=issue.column,
                severity=issue.severity.value,
                fixable=issue.fix is not None,
            )
            for proc_name, issue, _ in issues
        ],
    )


def lint_text(
    text: str,
    config_text: str | None = None,
    auto_fix: bool = False,
    select: str | None = None,
) -> TextLintResult:
    """Lint (and optionally auto-fix) a whole process given as *text*.

    Line numbers in the result refer to *text* itself, matching the CLI's
    report for the same file. With *auto_fix*, ``code`` holds the fixed source
    in its original format and the issues are those left after fixing.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = config_from_text(config_text)
        linter = linter_from_config(cfg, select)

        # detect_format may parse YAML; enforce the configured limit first.
        _check_text_size(text, linter.max_file_size)

        text_format = detect_format(text)
        with tempfile.TemporaryDirectory(prefix="linti-") as tmp:
            path = Path(tmp) / _FILE_NAMES[text_format]
            path.write_text(text, encoding="utf-8")
            provider = provider_for_path(path, max_file_size=linter.max_file_size)
            name = require_single_process_name(provider)
            fixes: dict[str, int] = {}
            if auto_fix:
                process = provider.get_process(name)
                fixes = auto_fix_process(process, linter)
                if fixes:
                    provider.save_process(process)
            issues = lint_process(provider, name, linter)[name]
            code = path.read_text(encoding="utf-8")

    issues = filter_by_severity(issues, cfg.min_severity)
    return TextLintResult(
        format=text_format,
        process_name=name,
        code=code,
        fixes=fixes,
        issues=sorted(
            (
                TextIssue(
                    procedure=proc_name,
                    rule_id=issue.rule_id,
                    message=adjust_line_numbers_in_message(issue.message, source_line),
                    line=source_line + issue.line - 1,
                    column=issue.column,
                    severity=issue.severity.value,
                    fixable=issue.fix is not None,
                )
                for proc_name, issue, source_line in issues
            ),
            key=lambda issue: (issue.line, issue.column, issue.rule_id),
        ),
        warnings=[str(warning.message) for warning in caught],
    )
