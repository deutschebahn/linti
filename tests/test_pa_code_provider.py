"""Tests for the PA code provider (#SECTION + #JSON_PROPERTIES)."""

import json
from pathlib import Path

import pytest

from linti.provider.factory import provider_for_path
from linti.provider.pa_code import PaCodeProvider, is_pa_code_content

PA_CODE = """\
#SECTION Prolog

sVar = 'X';

#SECTION Metadata

nMeta = 1;

#SECTION Data

nData = 2;

#SECTION Epilog

ProcessQuit;

#JSON_PROPERTIES
{
  "Parameters": [
    {"Name": "pValue"}
  ],
  "DataSource": {
    "Type": "None"
  },
  "Variables": [
    {"Name": "vName"}
  ],
  "HasSecurityAccess": false
}
"""


class TestPaCodeDetection:
    def test_is_pa_code_content_true(self):
        assert is_pa_code_content(PA_CODE) is True

    def test_is_pa_code_content_false(self):
        assert is_pa_code_content("#SECTION Prolog\na=1;\n") is False


class TestPaCodeProvider:
    @pytest.fixture
    def pa_file(self, tmp_path: Path) -> Path:
        file_path = tmp_path / "pa-code.ti"
        file_path.write_text(PA_CODE)
        return file_path

    def test_list_processes(self, pa_file: Path):
        provider = PaCodeProvider(pa_file)
        assert provider.list_processes() == ["pa-code"]

    def test_get_process_sections_and_metadata(self, pa_file: Path):
        provider = PaCodeProvider(pa_file)
        process = provider.get_process("pa-code")

        assert process.prolog is not None
        assert process.metadata is not None
        assert process.data is not None
        assert process.epilog is not None
        assert process.parameters == ["pValue"]
        assert process.variables == ["vName"]
        assert process.provider_data.get("pa_code") is True

    def test_get_process_wrong_name(self, pa_file: Path):
        provider = PaCodeProvider(pa_file)
        with pytest.raises(ValueError, match="Unknown PA code process"):
            provider.get_process("wrong")

    def test_save_process_roundtrip(self, pa_file: Path):
        provider = PaCodeProvider(pa_file)
        process = provider.get_process("pa-code")
        process.prolog.code = "sVar = 'Y';"
        provider.save_process(process)

        reloaded = provider.get_process("pa-code")
        assert "sVar = 'Y';" in reloaded.prolog.code

    def test_invalid_json_properties(self, tmp_path: Path):
        file_path = tmp_path / "bad.ti"
        file_path.write_text("#SECTION Prolog\n\n#JSON_PROPERTIES\n{ bad json }\n")

        provider = PaCodeProvider(file_path)
        with pytest.raises(ValueError, match="Invalid #JSON_PROPERTIES"):
            provider.get_process("bad")


class TestFactoryPaCodeDetection:
    def test_ti_with_pa_code_markers_uses_pa_provider(self, tmp_path: Path):
        file_path = tmp_path / "process.ti"
        file_path.write_text(PA_CODE)

        provider = provider_for_path(file_path)
        assert isinstance(provider, PaCodeProvider)

    def test_ti_without_pa_code_markers_not_pa_provider(self, tmp_path: Path):
        from linti.provider.ti import TiProvider

        file_path = tmp_path / "plain.ti"
        file_path.write_text("a=1;\n")

        provider = provider_for_path(file_path)
        assert isinstance(provider, TiProvider)

    def test_json_sibling_still_uses_git_provider(self, tmp_path: Path):
        from linti.provider.git import GitProvider

        ti_path = tmp_path / "proc.ti"
        json_path = tmp_path / "proc.json"

        ti_path.write_text(PA_CODE)
        json_path.write_text(
            json.dumps(
                {
                    "Name": "proc",
                    "Code@Code.link": "proc.ti",
                    "Parameters": [],
                    "Variables": [],
                }
            )
        )

        provider = provider_for_path(ti_path)
        assert isinstance(provider, GitProvider)

    def test_large_ti_is_detected_as_pa_code(self, tmp_path: Path):
        file_path = tmp_path / "large-pa.ti"
        large_middle = "\n".join("# filler" for _ in range(20000))
        file_path.write_text(
            "#SECTION Prolog\n\n"
            + large_middle
            + "\n#JSON_PROPERTIES\n"
            + "{\n"
            + '  "Parameters": [],\n'
            + '  "Variables": [],\n'
            + '  "DataSource": {"Type": "None"}\n'
            + "}\n"
        )

        provider = provider_for_path(file_path)
        assert isinstance(provider, PaCodeProvider)
