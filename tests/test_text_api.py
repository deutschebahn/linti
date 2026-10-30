"""Linting a process pasted as text (the browser playground's entry point)."""

from pathlib import Path
from collections import Counter

import pytest

from linti.linter.text_api import (
    config_from_text,
    detect_format,
    lint_rule_text,
    lint_text,
)

EXAMPLES = Path(__file__).parents[1] / "example"


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("example.ti", "ti"),
        ("git-format.ti", "ti"),
        ("pa-code.ti", "pa"),
        ("example-ti.yaml", "yaml"),
    ],
)
def test_detect_format(file_name, expected):
    assert detect_format((EXAMPLES / file_name).read_text()) == expected


def test_region_ti_is_detected_as_ti():
    text = "#region Prolog\nnValue = 1;\n#endregion\n#region Epilog\n#endregion\n"
    assert detect_format(text) == "ti"


def test_playground_examples_show_the_same_findings_in_all_four_formats():
    files = {
        "process.ti": "ti",
        "process-regions.ti": "ti",
        "process-pa.ti": "pa",
        "process.yaml": "yaml",
    }
    reports = []
    for name, expected_format in files.items():
        text = (EXAMPLES / "playground" / name).read_text()
        result = lint_text(text)
        assert result.format == expected_format
        assert not result.warnings
        reports.append(Counter(issue.rule_id for issue in result.issues))

        fixed = lint_text(text, auto_fix=True)
        assert fixed.format == expected_format
        assert sum(fixed.fixes.values()) > 0
        assert detect_format(fixed.code) == expected_format

    assert all(report == reports[0] for report in reports)
    assert set(reports[0]) >= {"C220", "F110", "F220", "F230", "F250", "N110"}


def test_plain_ti_findings_use_text_line_numbers():
    result = lint_text("nValue = 1;\nif (nValue = 1);\nENDIF;\n", select="F110")
    assert result.format == "ti"
    assert [(i.rule_id, i.line, i.column, i.fixable) for i in result.issues] == [
        ("F110", 2, 1, True)
    ]
    assert result.fixes == {}


def test_pa_code_lines_match_the_whole_file():
    text = (EXAMPLES / "pa-code.ti").read_text()
    result = lint_text(text, select="F110")
    assert result.format == "pa"
    assert {(i.procedure, i.line) for i in result.issues} == {
        ("metadata", 6),
        ("metadata", 8),
    }


def test_auto_fix_keeps_original_format():
    text = (EXAMPLES / "example-ti.yaml").read_text()
    result = lint_text(text, auto_fix=True, select="F110")
    assert result.format == "yaml"
    assert result.process_name == "Example-TI"
    assert result.fixes == {"prolog": 1}
    assert result.code.startswith(text[: text.index("PrologProcedure")])
    assert "  IF (a = 1);" in result.code
    assert not result.issues


def test_auto_fix_pa_code_keeps_json_properties():
    text = (EXAMPLES / "pa-code.ti").read_text()
    result = lint_text(text, auto_fix=True, select="F110")
    assert sum(result.fixes.values()) == 2
    assert "#JSON_PROPERTIES" in result.code
    assert "IF (cSTring @<> 'ABC');" in result.code


def test_config_text_disables_rules_and_filters_severity():
    code = "nValue = 1;\nif (nValue = 1);\nENDIF;\n"
    disabled = lint_text(code, "rules:\n  keyword_casing:\n    enabled: false\n")
    assert not any(issue.rule_id == "F110" for issue in disabled.issues)

    downgraded = lint_text(
        code,
        "severity: error\nrules:\n  keyword_casing:\n    severity: warning\n",
    )
    assert not any(issue.rule_id == "F110" for issue in downgraded.issues)


def test_config_warnings_are_returned():
    result = lint_text("nValue = 1;\n", "severity: loud\n")
    assert any("loud" in warning for warning in result.warnings)


def test_invalid_config_text_raises_value_error_for_parse_error():
    with pytest.raises(ValueError, match="Invalid linti.yaml"):
        config_from_text("rules: [")


def test_invalid_config_text_raises_type_error_for_list():
    with pytest.raises(TypeError, match="Invalid linti.yaml.*expected a mapping"):
        config_from_text("- just\n- a list\n")


def test_empty_config_text_uses_defaults():
    assert config_from_text("") == config_from_text("# only a comment\n")


def test_selected_rule_respects_severity_and_nesting_limits():
    assert [
        issue.rule_id for issue in lint_rule_text("nValue = 1", "prolog", "P110").issues
    ] == ["P110"]
    assert not lint_rule_text(
        "nValue = 1", "prolog", "P110", "severity: error\n"
    ).issues

    nested = "IF (1 = 1);\n  IF (1 = 1);\n    nValue = 1;\n  ENDIF;\nENDIF;"
    limited = lint_rule_text(nested, "prolog", "F220", "max_nesting_depth: 1\n")
    assert [issue.rule_id for issue in limited.issues] == ["P900"]


def test_selected_disabled_rule_runs_in_reference_but_not_full_scan():
    config = "rules:\n  docstring_region:\n    enabled: false\n"
    code = "nVar = 1;"

    assert [
        issue.rule_id for issue in lint_rule_text(code, "prolog", "D110", config).issues
    ] == ["D110"]
    assert not any(issue.rule_id == "D110" for issue in lint_text(code, config).issues)


def test_selected_rule_carries_context_and_config_warnings():
    result = lint_rule_text(
        "pFactor = 2;",
        "prolog",
        "C210",
        "rules:\n  process_quit:\n    enabled: true\n",
        parameters=["pFactor"],
    )
    assert any(issue.rule_id == "C210" for issue in result.issues)
    assert any("process_quit" in warning for warning in result.warnings)


def test_input_size_is_checked_before_format_detection(monkeypatch):
    def unexpected_parse(_text):
        raise AssertionError("format detection must not run on oversized input")

    monkeypatch.setattr("linti.linter.text_api.detect_format", unexpected_parse)
    with pytest.raises(ValueError, match="exceeds size limit"):
        lint_text("nValue = 1;", "max_file_size: 4\n")
    with pytest.raises(ValueError, match="exceeds size limit"):
        lint_rule_text("nValue = 1;", "prolog", "F220", "max_file_size: 4\n")
