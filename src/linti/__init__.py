"""linti — public API for embedding the linter in other tools.

The entry point depends on how much you already have:

- A process object from TM1py (or anything with the same attributes)::

      from linti import Config, Linter, create_rules, lint_process_model, process_ir_from_tm1

      token_rules, statement_rules = create_rules(Config())
      linter = Linter(rules=token_rules, statement_rules=statement_rules)
      issues = lint_process_model(process_ir_from_tm1(tm1.processes.get("MyProcess")), linter)

- A whole server, optionally writing fixes back::

      from linti import TM1Provider, lint_all

      results = lint_all(TM1Provider(tm1, prefetch=True), linter)

linti does not depend on TM1py: :class:`TM1Provider` takes a connection that is
already open and never builds one itself.
"""

from linti.config import Config
from linti.linter.api import lint_all, lint_process, lint_process_model
from linti.linter.lint_issue import Fix, LintIssue
from linti.linter.linter import Linter
from linti.linter.reporter import (
    ProcedureIssue,
    SourceLabel,
    render_directory_report,
    render_file_report,
)
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import ProcessProvider, ProviderError
from linti.provider.tm1 import (
    TM1Provider,
    TM1ProviderError,
    apply_to_tm1_process,
    process_ir_from_tm1,
)
from linti.rules.rule_factory import create_rules

__all__ = [
    # TM1 server integration
    "TM1Provider",
    "TM1ProviderError",
    "apply_to_tm1_process",
    "process_ir_from_tm1",
    # Linting core
    "Config",
    "Linter",
    "create_rules",
    "lint_all",
    "lint_process",
    "lint_process_model",
    "render_file_report",
    "render_directory_report",
    # Process model
    "ProcedureInfo",
    "ProcessIR",
    "ProcessProvider",
    # Issues
    "Fix",
    "LintIssue",
    "ProcedureIssue",
    "ProviderError",
    "SourceLabel",
]
