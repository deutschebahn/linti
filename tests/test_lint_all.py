"""Tests for lint_all over a multi-process provider."""

import pytest

from linti.config import Config
from linti.linter.api import lint_all
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules.rule_factory import create_rules


class FakeMultiProvider:
    """Minimal multi-process provider; the file providers all hold exactly one."""

    def __init__(self, sources: dict, failures: dict = None):
        self._sources = sources
        self._failures = failures or {}
        self.saved: list = []

    def list_processes(self) -> list:
        # Deliberately unsorted, to prove lint_all imposes an order.
        return list(reversed(list(self._sources)))

    def get_process(self, name: str) -> ProcessIR:
        if name in self._failures:
            raise self._failures[name]
        return ProcessIR(
            name=name,
            prolog=ProcedureInfo(
                code=self._sources[name], source_line=1, source_end_line=1
            ),
        )

    def save_process(self, process: ProcessIR) -> None:
        self.saved.append(process.name)


def new_linter() -> Linter:
    cfg = Config()
    token_rules, statement_rules = create_rules(cfg)
    return Linter(
        rules=token_rules,
        statement_rules=statement_rules,
        max_nesting_depth=cfg.max_nesting_depth,
        max_file_size=cfg.max_file_size,
        max_values_per_variable=cfg.max_values_per_variable,
    )


def test_results_are_flat_lists_of_issues():
    provider = FakeMultiProvider({"Alpha": "if(1=1);\nendif;\n", "Beta": "nA = 1;\n"})
    results = lint_all(provider, new_linter())

    assert sorted(results) == ["Alpha", "Beta"]
    for issues in results.values():
        assert isinstance(issues, list)
        for entry in issues:
            proc_name, issue, source_line = entry
            assert isinstance(proc_name, str)
            assert isinstance(source_line, int)
            assert hasattr(issue, "rule_id")


def test_processes_are_visited_in_sorted_order():
    provider = FakeMultiProvider({"Zeta": "nA = 1;\n", "Alpha": "nA = 1;\n"})
    assert list(lint_all(provider, new_linter())) == ["Alpha", "Zeta"]


def test_a_failure_propagates_by_default():
    provider = FakeMultiProvider(
        {"Alpha": "nA = 1;\n", "Beta": "nA = 1;\n"},
        failures={"Alpha": ValueError("boom")},
    )
    with pytest.raises(ValueError, match="boom"):
        lint_all(provider, new_linter())


def test_on_error_collects_and_keeps_going():
    provider = FakeMultiProvider(
        {"Alpha": "nA = 1;\n", "Beta": "if(1=1);\nendif;\n", "Gamma": "nA = 1;\n"},
        failures={"Beta": ValueError("boom")},
    )
    seen: list = []
    results = lint_all(
        provider, new_linter(), on_error=lambda n, e: seen.append((n, str(e)))
    )

    assert seen == [("Beta", "boom")]
    # The failure must not hide the processes that came after it.
    assert sorted(results) == ["Alpha", "Gamma"]
