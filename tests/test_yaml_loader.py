"""Tests for YAML loader."""

import pytest

from linti.loader.yaml_loader import extract_procedures, load_yaml_process


def test_load_yaml_process_basic(tmp_path):
    """Test loading a basic YAML process file."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """
Name: TestProcess
PrologProcedure: |
  nValue = 1;
MetadataProcedure: |
  sText = 'data';
DataProcedure: null
EpilogProcedure: |
  LogOutput('INFO', 'Done');
"""
    )

    process = load_yaml_process(p)

    assert process.name == "TestProcess"
    assert process.procedures["prolog"].code == "nValue = 1;\n"
    assert process.procedures["metadata"].code == "sText = 'data';\n"
    assert process.procedures["data"] is None
    assert process.procedures["epilog"].code == "LogOutput('INFO', 'Done');\n"
    assert process.procedures["prolog"].source_line > 0


def test_extract_procedures(tmp_path):
    """Test extraction of non-null procedures."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """
Name: TestProcess
PrologProcedure: |
  nValue = 1;
MetadataProcedure: null
DataProcedure: |
  nData = 2;
EpilogProcedure: null
"""
    )

    process = load_yaml_process(p)
    procedures = extract_procedures(process)

    assert "prolog" in procedures
    assert "data" in procedures
    assert "metadata" not in procedures
    assert "epilog" not in procedures
    assert len(procedures) == 2


def test_load_yaml_with_tm1py_tag(tmp_path):
    """Test loading YAML file with TM1py.ProcessObject tag."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """!TM1py.ProcessObject
Name: TaggedProcess
PrologProcedure: |
  cExample = 'value';
MetadataProcedure: null
DataProcedure: null
EpilogProcedure: null
"""
    )

    process = load_yaml_process(p)

    assert process.name == "TaggedProcess"
    assert "cExample" in process.procedures["prolog"].code


def test_load_yaml_empty_file(tmp_path):
    """Test loading an empty YAML file raises error."""
    p = tmp_path / "test.yaml"
    p.write_text("")

    with pytest.raises(ValueError):
        load_yaml_process(p)


def test_load_yaml_non_process_file_raises(tmp_path):
    """Test that a YAML file without TM1 process markers is rejected."""
    p = tmp_path / "test.yaml"
    p.write_text("rules:\n  keyword_casing:\n    enabled: true\n")

    with pytest.raises(ValueError, match="Not a TM1 process YAML file"):
        load_yaml_process(p)


def test_load_yaml_non_process_with_kind_field(tmp_path):
    """Test that a YAML with a different 'kind' is rejected."""
    p = tmp_path / "test.yaml"
    p.write_text('kind: "something_else"\nmetadata:\n  name: "test"\n')

    with pytest.raises(ValueError, match="Not a TM1 process YAML file"):
        load_yaml_process(p)


def test_procedures_have_yaml_line_numbers(tmp_path):
    """Test that procedures track their YAML line numbers."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """Name: TestProcess
PrologProcedure: |
  first = 1;
MetadataProcedure: |
  second = 2;
DataProcedure: null
EpilogProcedure: |
  third = 3;
"""
    )

    process = load_yaml_process(p)

    # Line numbers should be > 0 for non-null procedures
    assert process.procedures["prolog"].source_line > 0
    assert process.procedures["metadata"].source_line > 0
    assert process.procedures["epilog"].source_line > 0

    # Metadata line should be after prolog
    assert (
        process.procedures["metadata"].source_line
        > process.procedures["prolog"].source_line
    )


def test_procedures_have_yaml_end_line_numbers(tmp_path):
    """Test that procedures track their YAML end line numbers."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """Name: TestProcess
PrologProcedure: |
  first = 1;
  second = 2;
MetadataProcedure: |
  third = 3;
DataProcedure: null
EpilogProcedure: |
  fourth = 4;
"""
    )

    process = load_yaml_process(p)

    assert process.procedures["prolog"].source_end_line > 0
    assert process.procedures["metadata"].source_end_line > 0
    assert process.procedures["epilog"].source_end_line > 0

    assert (
        process.procedures["prolog"].source_end_line
        >= process.procedures["prolog"].source_line
    )
    assert (
        process.procedures["metadata"].source_end_line
        >= process.procedures["metadata"].source_line
    )
    assert (
        process.procedures["epilog"].source_end_line
        >= process.procedures["epilog"].source_line
    )


def test_load_config_definition_format(tmp_path):
    """Test loading the new config.definition YAML format."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """\
apiVersion: "1.0"
kind: "process_definition"
metadata:
  name: "TestProcess"
config:
  definition:
    Name: TestProcess
    PrologProcedure: |-
      nValue = 1;
      IF(nValue = 1);
          nResult = 2;
      ENDIF;
    MetadataProcedure: |-
      sText = 'data';
    DataProcedure: null
    EpilogProcedure: |-
      LogOutput('INFO', 'Done');
    Parameters:
      - Name: pLogOutput
        Prompt: "Log output"
        Value: 1
        Type: Numeric
    Variables:
      - Name: vDimension
        Type: String
        Position: 1
        StartByte: 0
        EndByte: 0
"""
    )

    process = load_yaml_process(p)

    assert process.name == "TestProcess"
    assert "nValue = 1;" in process.procedures["prolog"].code
    assert process.procedures["metadata"].code.strip() == "sText = 'data';"
    assert process.procedures["data"] is None
    assert "LogOutput" in process.procedures["epilog"].code
    assert process.procedures["prolog"].source_line > 0
    assert process.content_indent == 6
    assert process.parameters == ["pLogOutput"]
    assert "pLogOutput" in process.parameter_lines
    assert process.variables == ["vDimension"]
    assert "vDimension" in process.variable_lines


def test_legacy_format_has_content_indent_2(tmp_path):
    """Test that legacy TM1py format sets content_indent to 2."""
    p = tmp_path / "test.yaml"
    p.write_text(
        """!TM1py.ProcessObject
Name: LegacyProcess
PrologProcedure: |
  nValue = 1;
"""
    )

    process = load_yaml_process(p)
    assert process.content_indent == 2
