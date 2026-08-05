"""Tests for the TM1 server provider and its ProcessIR adapter."""

import pytest
from tm1_fakes import (
    BEGIN_GENERATED_STATEMENTS,
    END_GENERATED_STATEMENTS,
    FakeProcess,
    FakeTM1,
    TM1pyRestException,
)

from linti.linter.reporter import format_issue
from linti.linter.lint_issue import LintIssue
from linti.provider.base import ProviderError
from linti.provider.tm1 import (
    PROCESS_KEY,
    TM1Provider,
    TM1ProviderError,
    apply_to_tm1_process,
    process_ir_from_tm1,
)

PROLOG = "\r\nnValue = 1;\r\nnOther = 2;\r\n"


def make_process(name="MyProcess", **kwargs):
    kwargs.setdefault("prolog_procedure", PROLOG)
    return FakeProcess(name, **kwargs)


class TestProcessIrFromTm1:
    def test_strips_generated_block_and_carriage_returns(self):
        ir = process_ir_from_tm1(make_process())
        assert ir.prolog.code == "\nnValue = 1;\nnOther = 2;\n"
        assert "\r" not in ir.prolog.code
        assert BEGIN_GENERATED_STATEMENTS not in ir.prolog.code

    def test_keeps_all_four_sections_even_when_empty(self):
        ir = process_ir_from_tm1(make_process())
        for section in ("prolog", "metadata", "data", "epilog"):
            assert getattr(ir, section) is not None
        assert ir.metadata.code == ""

    def test_reads_parameters_and_variables(self):
        ir = process_ir_from_tm1(
            make_process(
                parameters=[{"Name": "pCube", "Type": "String"}],
                variables=[{"Name": "vLine", "Type": "String"}],
            )
        )
        assert ir.parameters == ["pCube"]
        assert ir.variables == ["vLine"]
        assert ir.parameter_lines == {"pCube": 0}

    def test_reads_datasource(self):
        ir = process_ir_from_tm1(
            make_process(datasource_type="ODBC", datasource_query="SELECT 1")
        )
        assert ir.datasource_type == "ODBC"
        assert ir.datasource_query == "SELECT 1"

    def test_accepts_any_object_with_the_right_attributes(self):
        # The integration contract is structural: no TM1py type is required.
        class Minimal:
            name = "Minimal"
            prolog_procedure = "nValue = 1;\n"
            metadata_procedure = ""
            data_procedure = ""
            epilog_procedure = ""

        ir = process_ir_from_tm1(Minimal())
        assert ir.name == "Minimal"
        assert ir.prolog.code == "nValue = 1;\n"
        assert ir.parameters == []


class TestSourceLineArithmetic:
    """Reported line numbers must match how TM1 numbers the stored procedure."""

    def test_source_line_starts_after_the_generated_block(self):
        ir = process_ir_from_tm1(make_process())
        # FakeProcess prepends BEGIN/END, so code line 1 is TM1 line 3.
        assert ir.prolog.source_line == 3

    def test_rendered_line_number_matches_hand_counted_tm1_line(self):
        process = make_process()
        ir = process_ir_from_tm1(process)

        # Hand-count where "nOther = 2;" sits in the stored procedure.
        stored_lines = process.prolog_procedure.replace("\r\n", "\n").split("\n")
        expected_tm1_line = stored_lines.index("nOther = 2;") + 1

        # That statement is line 3 of the code linti sees ("", "nValue…", "nOther…").
        issue = LintIssue(message="x", line=3, column=1, position=0, rule_id="F110")
        rendered = format_issue("MyProcess", "prolog", issue, ir.prolog.source_line)
        assert rendered.startswith(f"MyProcess:{expected_tm1_line}:1 (PrologProcedure)")

    def test_source_end_line_is_absolute(self):
        # It feeds LintContext.block_end_line, which compares against absolute
        # line numbers; a relative count would silently change F320.
        ir = process_ir_from_tm1(make_process())
        assert ir.prolog.code.count("\n") == 3  # three code lines
        assert ir.prolog.source_end_line == ir.prolog.source_line + 2

    def test_empty_procedure_keeps_a_usable_end_line(self):
        ir = process_ir_from_tm1(make_process())
        assert ir.metadata.source_end_line == ir.metadata.source_line

    def test_message_line_references_are_offset_too(self):
        ir = process_ir_from_tm1(make_process())
        issue = LintIssue(
            message="duplicate of line 1", line=3, column=1, position=0, rule_id="S110"
        )
        rendered = format_issue("MyProcess", "prolog", issue, ir.prolog.source_line)
        assert "duplicate of line 3" in rendered


class TestListProcesses:
    def test_sorted_and_control_processes_filtered(self):
        tm1 = FakeTM1(
            make_process("Zeta"),
            make_process("}ControlProcess"),
            make_process("{Internal"),
            make_process("Alpha"),
        )
        assert TM1Provider(tm1).list_processes() == ["Alpha", "Zeta"]

    def test_control_processes_can_be_kept(self):
        tm1 = FakeTM1(make_process("Alpha"), make_process("}Control"))
        provider = TM1Provider(tm1, skip_control_processes=False)
        assert provider.list_processes() == ["Alpha", "}Control"]

    def test_prefetch_uses_a_single_call(self):
        tm1 = FakeTM1(make_process("Alpha"), make_process("Beta"))
        calls = []
        original = tm1.processes.get
        tm1.processes.get = lambda name: (calls.append(name), original(name))[1]

        provider = TM1Provider(tm1, prefetch=True)
        for name in provider.list_processes():
            provider.get_process(name)

        assert calls == []


class TestGetProcess:
    def test_round_trips_a_process(self):
        tm1 = FakeTM1(make_process())
        ir = TM1Provider(tm1).get_process("MyProcess")
        assert ir.name == "MyProcess"
        assert ir.provider_data[PROCESS_KEY] is not None

    def test_missing_process_is_reported_with_the_original_error_name(self):
        tm1 = FakeTM1(make_process())
        with pytest.raises(TM1ProviderError) as excinfo:
            TM1Provider(tm1).get_process("Nope")
        message = str(excinfo.value)
        assert "Cannot load process 'Nope' from TM1" in message
        # The originating type is named without linti importing TM1py.
        assert "TM1pyRestException" in message

    def test_connection_failure_names_the_original_error(self):
        tm1 = FakeTM1(raise_on_list=TM1pyRestException("401 Unauthorized"))
        with pytest.raises(TM1ProviderError, match="Cannot list processes on TM1"):
            TM1Provider(tm1).list_processes()

    def test_provider_errors_are_value_errors(self):
        # Keeps the pre-existing provider error contract intact.
        tm1 = FakeTM1(make_process())
        with pytest.raises(ValueError):
            TM1Provider(tm1).get_process("Nope")

    def test_label_appears_in_messages(self):
        tm1 = FakeTM1(make_process())
        with pytest.raises(TM1ProviderError, match="from tm1srv01"):
            TM1Provider(tm1, label="tm1srv01").get_process("Nope")

    def test_oversized_process_is_rejected(self):
        tm1 = FakeTM1(make_process(prolog_procedure="x" * 5000))
        provider = TM1Provider(tm1, max_process_size=1000)
        with pytest.raises(ProviderError, match="exceeds size limit"):
            provider.get_process("MyProcess")

    def test_service_without_processes_attribute_is_reported(self):
        class NotAService:
            pass

        with pytest.raises(TM1ProviderError, match="has no 'processes' service"):
            TM1Provider(NotAService()).list_processes()


class TestSaveProcess:
    def test_unchanged_process_is_not_written(self):
        tm1 = FakeTM1(make_process())
        provider = TM1Provider(tm1)
        provider.save_process(provider.get_process("MyProcess"))
        assert tm1.processes.updated == []

    def test_changed_process_is_written_once_with_endings_restored(self):
        tm1 = FakeTM1(make_process())
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = ir.prolog.code.replace("nValue = 1;", "nValue = 42;")

        provider.save_process(ir)

        assert len(tm1.processes.updated) == 1
        written = tm1.processes.updated[0].prolog_procedure
        assert written == (
            f"{BEGIN_GENERATED_STATEMENTS}\r\n{END_GENERATED_STATEMENTS}\r\n"
            "\r\nnValue = 42;\r\nnOther = 2;\r\n"
        )

    def test_only_the_intended_span_changes(self):
        process = make_process()
        original = process.prolog_procedure
        tm1 = FakeTM1(process)
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = ir.prolog.code.replace("nValue = 1;", "nValue = 42;")

        provider.save_process(ir)

        written = tm1.processes.updated[0].prolog_procedure
        assert written == original.replace("nValue = 1;", "nValue = 42;")

    def test_other_sections_are_untouched(self):
        tm1 = FakeTM1(make_process(epilog_procedure="ProcessQuit;\r\n"))
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        original_epilog = ir.provider_data[PROCESS_KEY].epilog_procedure
        ir.prolog.code = ir.prolog.code.replace("nValue = 1;", "nValue = 42;")

        provider.save_process(ir)

        assert tm1.processes.updated[0].epilog_procedure == original_epilog

    def test_save_without_a_loaded_process_is_refused(self):
        from linti.model.process_ir import ProcedureInfo, ProcessIR

        tm1 = FakeTM1(make_process())
        detached = ProcessIR(name="MyProcess", prolog=ProcedureInfo(code="nA = 1;\n"))
        with pytest.raises(TM1ProviderError, match="not loaded through this provider"):
            TM1Provider(tm1).save_process(detached)

    def test_prefetch_cache_is_invalidated_on_save(self):
        tm1 = FakeTM1(make_process())
        provider = TM1Provider(tm1, prefetch=True)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = ir.prolog.code.replace("nValue = 1;", "nValue = 42;")
        provider.save_process(ir)

        # Must come from the server, not from the pre-save snapshot.
        assert "nValue = 42;" in provider.get_process("MyProcess").prolog.code

    def test_update_failure_names_the_original_error(self):
        tm1 = FakeTM1(make_process(), raise_on_update=TM1pyRestException("403"))
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = "nValue = 99;\n"
        with pytest.raises(TM1ProviderError) as excinfo:
            provider.save_process(ir)
        assert "Cannot save process 'MyProcess' to TM1" in str(excinfo.value)
        assert "TM1pyRestException" in str(excinfo.value)


class TestVerifyBeforeSave:
    def test_server_syntax_errors_block_the_write(self):
        tm1 = FakeTM1(
            make_process(),
            compile_errors={"MyProcess": [{"Message": "Syntax error on line 2"}]},
        )
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = "nValue = ;\n"

        with pytest.raises(TM1ProviderError, match="rejected the fixed code"):
            provider.save_process(ir)
        assert tm1.processes.updated == []

    def test_verification_can_be_switched_off(self):
        tm1 = FakeTM1(
            make_process(), compile_errors={"MyProcess": [{"Message": "boom"}]}
        )
        provider = TM1Provider(tm1, verify_before_save=False)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = "nValue = 99;\n"
        provider.save_process(ir)
        assert len(tm1.processes.updated) == 1
        assert tm1.processes.compiled == []

    def test_missing_compile_support_warns_but_saves(self):
        tm1 = FakeTM1(make_process(), supports_compile=False)
        provider = TM1Provider(tm1)
        ir = provider.get_process("MyProcess")
        ir.prolog.code = "nValue = 99;\n"

        with pytest.warns(RuntimeWarning, match="pre-save compilation"):
            provider.save_process(ir)
        assert len(tm1.processes.updated) == 1


class TestApplyToTm1Process:
    def test_reports_whether_anything_changed(self):
        process = make_process()
        ir = process_ir_from_tm1(process)
        assert apply_to_tm1_process(ir, process) is False

        ir.prolog.code = "nValue = 42;\n"
        assert apply_to_tm1_process(ir, process) is True

    def test_process_without_a_prefix_lets_the_server_object_add_one(self):
        # A ProcessIR built from scratch has no stored prefix; TM1py's setter
        # then supplies the generated block itself.
        from linti.model.process_ir import ProcedureInfo, ProcessIR

        process = FakeProcess("New")
        ir = ProcessIR(name="New", prolog=ProcedureInfo(code="nValue = 1;\n"))
        assert apply_to_tm1_process(ir, process) is True
        assert process.prolog_procedure.startswith(BEGIN_GENERATED_STATEMENTS)
        # Written with server line endings, since there is no original to match.
        assert process.prolog_procedure.endswith("nValue = 1;\r\n")

    def test_a_rewriting_setter_is_caught_rather_than_trusted(self):
        class RewritingProcess(FakeProcess):
            @property
            def prolog_procedure(self):
                return self._procedures["prolog"]

            @prolog_procedure.setter
            def prolog_procedure(self, value):
                self._procedures["prolog"] = value + "\r\n# injected\r\n"

        process = RewritingProcess("MyProcess", prolog_procedure=PROLOG)
        ir = process_ir_from_tm1(process)
        ir.prolog.code = "nValue = 42;\n"

        with pytest.raises(TM1ProviderError, match="did not store the intended code"):
            apply_to_tm1_process(ir, process)
