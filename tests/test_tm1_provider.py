"""Tests for the read-only TM1 provider."""

import pytest

from linti.provider.base import ProviderError
from linti.provider.tm1 import (
    PROCEDURES_KEY,
    TM1Provider,
    TM1ProviderError,
    process_ir_from_tm1,
)
from tm1_fakes import FakeProcess, FakeTM1Service, server_procedure


def make_service(**kwargs):
    processes = [
        FakeProcess(
            "Sales.Load",
            prolog=server_procedure("sCube = 'Sales';"),
            epilog=server_procedure("nDone = 1;"),
            parameters=[{"Name": "pYear", "Value": "2026"}],
            variables=[{"Name": "vAmount"}],
            datasource_type="ODBC",
            datasource_query="SELECT 1",
        ),
        FakeProcess("Sales.Report", prolog=server_procedure("nX = 1;")),
        FakeProcess("}ControlProcess", prolog=server_procedure("nY = 1;")),
        FakeProcess("{OtherControl", prolog=server_procedure("nZ = 1;")),
    ]
    return FakeTM1Service(processes, **kwargs)


class TestListProcesses:
    def test_control_processes_are_skipped_and_names_sorted(self):
        provider = TM1Provider(make_service())
        assert provider.list_processes() == ["Sales.Load", "Sales.Report"]

    def test_control_processes_can_be_included(self):
        provider = TM1Provider(make_service(), skip_control_processes=False)
        assert provider.list_processes() == [
            "Sales.Load",
            "Sales.Report",
            "{OtherControl",
            "}ControlProcess",
        ]

    def test_server_failure_is_translated_and_keeps_the_cause(self):
        class Broken:
            def get_all_names(self):
                raise RuntimeError("boom")

        class Service:
            processes = Broken()

        provider = TM1Provider(Service(), label="prod")
        with pytest.raises(TM1ProviderError) as exc_info:
            provider.list_processes()
        assert "prod" in str(exc_info.value)
        assert "RuntimeError: boom" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_connection_without_a_processes_service(self):
        with pytest.raises(TM1ProviderError, match="no 'processes' service"):
            TM1Provider(object()).list_processes()


class TestGetProcess:
    def test_all_four_sections_are_present_even_when_empty(self):
        ir = TM1Provider(make_service()).get_process("Sales.Load")
        assert ir.prolog is not None and ir.metadata is not None
        assert ir.data is not None and ir.epilog is not None
        assert ir.metadata.code == ""

    def test_generated_block_and_crlf_are_gone(self):
        ir = TM1Provider(make_service()).get_process("Sales.Load")
        assert ir.prolog.code == "sCube = 'Sales';\n"
        assert "\r" not in ir.prolog.code
        assert "Generated Statements" not in ir.prolog.code

    def test_line_numbers_start_after_the_generated_block(self):
        ir = TM1Provider(make_service()).get_process("Sales.Load")
        # BEGIN, NULL;, END occupy TM1 lines 1-3.
        assert ir.prolog.source_line == 4
        assert ir.prolog.source_end_line == 5

    def test_parameters_variables_and_datasource(self):
        ir = TM1Provider(make_service()).get_process("Sales.Load")
        assert ir.parameters == ["pYear"]
        assert ir.variables == ["vAmount"]
        assert ir.datasource_type == "ODBC"
        assert ir.datasource_query == "SELECT 1"

    def test_decoded_sections_are_kept_for_a_future_write_back(self):
        ir = TM1Provider(make_service()).get_process("Sales.Load")
        decoded = ir.provider_data[PROCEDURES_KEY]
        assert set(decoded) == {"prolog", "metadata", "data", "epilog"}
        assert "Generated Statements" in decoded["prolog"].prefix
        assert decoded["prolog"].newline == "\r\n"

    def test_the_ir_holds_no_reference_to_the_process_object(self):
        """It stays a plain snapshot, so no session is kept alive by an IR."""
        service = make_service()
        ir = TM1Provider(service).get_process("Sales.Load")
        held = list(ir.provider_data.values())
        assert not any(isinstance(value, FakeProcess) for value in held)

    def test_unknown_process(self):
        with pytest.raises(TM1ProviderError, match="not found"):
            TM1Provider(make_service()).get_process("Nope")

    def test_server_returning_a_different_process_is_rejected(self):
        service = make_service()
        service.processes.processes["Sales.Load"].name = "Something.Else"
        with pytest.raises(TM1ProviderError, match="returned 'Something.Else'"):
            TM1Provider(service).get_process("Sales.Load")

    def test_oversized_process_is_rejected_before_linting(self):
        provider = TM1Provider(make_service(), max_process_size=10)
        with pytest.raises(ProviderError, match="exceeds size limit"):
            provider.get_process("Sales.Load")

    def test_fetch_failure_is_translated(self):
        provider = TM1Provider(make_service(fail_on=["Sales.Load"]))
        with pytest.raises(TM1ProviderError, match="RuntimeError"):
            provider.get_process("Sales.Load")


class TestSaveProcess:
    def test_saving_is_refused_and_explains_why(self):
        provider = TM1Provider(make_service())
        ir = provider.get_process("Sales.Load")
        with pytest.raises(TM1ProviderError) as exc_info:
            provider.save_process(ir)
        message = str(exc_info.value)
        assert "auto-fix is not supported" in message
        assert "Sales.Load" in message


class TestProcessIrFromTm1:
    def test_works_on_a_bare_process_object_without_a_provider(self):
        """The documented entry point for callers who already hold a process."""
        process = FakeProcess("Direct", prolog=server_procedure("nA = 1;"))
        ir = process_ir_from_tm1(process)
        assert ir.name == "Direct"
        assert ir.prolog.code == "nA = 1;\n"

    def test_missing_attributes_default_rather_than_raise(self):
        class Minimal:
            name = "Minimal"

        ir = process_ir_from_tm1(Minimal())
        assert ir.prolog.code == ""
        assert ir.parameters == []
        assert ir.datasource_type is None
