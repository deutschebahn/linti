"""Tests for the GitProvider (JSON + .ti git-deploy format)."""

import json
from pathlib import Path

import pytest

from linti.provider.git import GitProvider
from linti.provider.ti import TiProvider
from linti.provider.ti_regions import parse_ti_regions

TI_CODE = """\
#region Prolog

cString = 'Hello';

#endregion
#region Metadata

nCount = 1;

#endregion
#region Data

sValue = CellGetS('Cube', 'e1', 'e2');

#endregion
#region Epilog

ProcessQuit;

#endregion
"""

JSON_META = {
    "@type": "Process",
    "Name": "test-process",
    "HasSecurityAccess": False,
    "Code@Code.link": "test-process.ti",
    "DataSource": {"Type": "None"},
    "Parameters": [
        {"Name": "pRegion", "Value": "", "Prompt": "", "Type": "String"},
        {"Name": "pDebug", "Value": 0, "Prompt": "", "Type": "Numeric"},
    ],
    "Variables": [
        {"Name": "vName", "StartByte": 1, "EndByte": 10},
    ],
}


class TestParseTiRegions:
    def test_parses_all_sections(self):
        sections = parse_ti_regions(TI_CODE)
        assert set(sections.keys()) == {"prolog", "metadata", "data", "epilog"}

    def test_prolog_content(self):
        sections = parse_ti_regions(TI_CODE)
        assert "cString = 'Hello';" in sections["prolog"].code

    def test_source_lines(self):
        sections = parse_ti_regions(TI_CODE)
        # #region Prolog is line 1, so content starts at line 2
        assert sections["prolog"].source_line == 2

    def test_empty_code(self):
        sections = parse_ti_regions("")
        assert sections == {}

    def test_single_section(self):
        code = "#region Prolog\nx = 1;\n#endregion\n"
        sections = parse_ti_regions(code)
        assert "prolog" in sections
        assert sections["prolog"].code == "x = 1;"

    def test_case_insensitive(self):
        code = "#Region PROLOG\nx = 1;\n#EndRegion\n"
        sections = parse_ti_regions(code)
        assert "prolog" in sections


class TestGitProvider:
    @pytest.fixture
    def git_process(self, tmp_path: Path):
        json_path = tmp_path / "test-process.json"
        ti_path = tmp_path / "test-process.ti"
        json_path.write_text(json.dumps(JSON_META))
        ti_path.write_text(TI_CODE)
        return json_path

    def test_list_processes(self, git_process: Path):
        provider = GitProvider(git_process)
        assert provider.list_processes() == ["test-process"]

    def test_get_process_name(self, git_process: Path):
        provider = GitProvider(git_process)
        process = provider.get_process("test-process")
        assert process.name == "test-process"

    def test_get_process_procedures(self, git_process: Path):
        provider = GitProvider(git_process)
        process = provider.get_process("test-process")
        assert process.prolog is not None
        assert process.metadata is not None
        assert process.data is not None
        assert process.epilog is not None

    def test_get_process_parameters(self, git_process: Path):
        provider = GitProvider(git_process)
        process = provider.get_process("test-process")
        assert process.parameters == ["pRegion", "pDebug"]

    def test_get_process_variables(self, git_process: Path):
        provider = GitProvider(git_process)
        process = provider.get_process("test-process")
        assert process.variables == ["vName"]

    def test_get_process_wrong_name(self, git_process: Path):
        provider = GitProvider(git_process)
        with pytest.raises(ValueError, match="Unknown process"):
            provider.get_process("wrong-name")

    def test_save_process_roundtrip(self, git_process: Path):
        provider = GitProvider(git_process)
        process = provider.get_process("test-process")
        # Modify prolog
        from linti.model.process_ir import ProcedureInfo

        process.prolog = ProcedureInfo(
            code="\ncFixed = 'Fixed';\n",
            source_line=process.prolog.source_line,
            source_end_line=process.prolog.source_end_line,
        )
        provider.save_process(process)
        # Reload and verify
        reloaded = provider.get_process("test-process")
        assert "cFixed = 'Fixed';" in reloaded.prolog.code

    def test_missing_code_link(self, tmp_path: Path):
        json_path = tmp_path / "bad.json"
        json_path.write_text(json.dumps({"Name": "bad"}))
        with pytest.raises(ValueError, match="Code@Code.link"):
            GitProvider(json_path)


class TestFactoryGitDetection:
    def test_json_gives_git_provider(self, tmp_path: Path):
        from linti.provider.factory import provider_for_path

        json_path = tmp_path / "proc.json"
        ti_path = tmp_path / "proc.ti"
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
        ti_path.write_text("#region Prolog\n#endregion\n")
        provider = provider_for_path(json_path)
        assert isinstance(provider, GitProvider)

    def test_ti_with_json_sibling_gives_git_provider(self, tmp_path: Path):
        from linti.provider.factory import provider_for_path

        json_path = tmp_path / "proc.json"
        ti_path = tmp_path / "proc.ti"
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
        ti_path.write_text("#region Prolog\nx=1;\n#endregion\n")
        provider = provider_for_path(ti_path)
        assert isinstance(provider, GitProvider)

    def test_ti_without_json_gives_ti_provider(self, tmp_path: Path):
        from linti.provider.factory import provider_for_path

        ti_path = tmp_path / "plain.ti"
        ti_path.write_text("x = 1;\n")
        provider = provider_for_path(ti_path)
        assert isinstance(provider, TiProvider)


class TestTiProviderRegionSupport:
    def test_get_process_parses_region_sections(self, tmp_path: Path):
        ti_path = tmp_path / "regioned.ti"
        ti_path.write_text(TI_CODE)

        provider = TiProvider(ti_path)
        process = provider.get_process("regioned")

        assert process.prolog is not None
        assert process.metadata is not None
        assert process.data is not None
        assert process.epilog is not None
        assert process.provider_data.get("ti_has_regions") is True

    def test_get_process_plain_ti_stays_prolog(self, tmp_path: Path):
        ti_path = tmp_path / "plain.ti"
        ti_path.write_text("a = 1;\nb = 2;\n")

        provider = TiProvider(ti_path)
        process = provider.get_process("plain")

        assert process.prolog is not None
        assert process.metadata is None
        assert process.data is None
        assert process.epilog is None
        assert process.provider_data.get("ti_has_regions") is None

    def test_save_preserves_region_format(self, tmp_path: Path):
        ti_path = tmp_path / "regioned.ti"
        ti_path.write_text(TI_CODE)

        provider = TiProvider(ti_path)
        process = provider.get_process("regioned")
        provider.save_process(process)

        saved = ti_path.read_text()
        assert "#region Prolog" in saved
        assert "#region Metadata" in saved
        assert "#region Data" in saved
        assert "#region Epilog" in saved
