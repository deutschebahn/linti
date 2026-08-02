"""Tests for HardcodedSecretRule (X130)."""

from linti.config import Config
from linti.lexer.lexer import Lexer
from linti.linter.api import lint_process_model
from linti.linter.lint_context import LintContext
from linti.linter.linter import Linter
from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.rules.rule_factory import create_rules
from linti.rules.semantic.hardcoded_secret_rule import HardcodedSecretRule
from linti.semantic.constant_evaluation import ConstantEvaluationIndex


def _lint(code: str, **kwargs):
    """Lint without a process model, so constant evaluation reports nothing.

    This is the syntax-only path: whatever these tests assert has to hold from
    the AST alone. ``_lint_with_constant_evaluation`` covers the same rule
    with the index wired in.
    """
    rule = HardcodedSecretRule(**kwargs)
    return Linter(statement_rules=[rule]).lint(Lexer(code).tokenize())


def _lint_with_constant_evaluation(code: str, **kwargs):
    """Lint *code* as a Prolog with the constant evaluation index available."""
    process = ProcessIR(name="test_process", prolog=ProcedureInfo(code=code))
    context = LintContext(block="prolog", constants=ConstantEvaluationIndex(process))
    rule = HardcodedSecretRule(**kwargs)
    return Linter(statement_rules=[rule]).lint(Lexer(code).tokenize(), context=context)


def _names(issues):
    # Extract the quoted variable name from each message.
    return sorted(issue.message.split("'")[1] for issue in issues)


def _x130_rules(config_dict=None):
    _, statement_rules = create_rules(Config.model_validate(config_dict or {}))
    return [r for r in statement_rules if r.RULE_ID == "X130"]


class TestDetection:
    def test_string_literal_is_reported(self):
        issues = _lint("sPassword = 'hunter2';")
        assert len(issues) == 1
        assert issues[0].rule_id == "X130"

    def test_parameter_reference_is_allowed(self):
        assert _lint("sPassword = pPassword;") == []

    def test_variable_reference_is_allowed(self):
        assert _lint("sPassword = sOtherPassword;") == []

    def test_unrelated_function_call_is_allowed(self):
        assert _lint("sPassword = Trim(pPassword);") == []

    def test_empty_string_initialisation_is_allowed(self):
        assert _lint("sPassword = '';") == []

    def test_whitespace_only_literal_is_allowed(self):
        assert _lint("sPassword = '   ';") == []

    def test_number_literal_is_reported_for_password_like_names(self):
        # A numeric PIN is still a hardcoded secret for the precise fragments
        # (see _NUMERIC_SECRET_PATTERNS).
        issues = _lint("sPassword = 12345;")
        assert len(issues) == 1
        assert issues[0].rule_id == "X130"

    def test_number_literal_is_not_reported_for_strict_only_names(self):
        # `key` is a common name for an ordinary integer (a dimension key, a
        # permission level, ...), so it stays string-only even in strict mode.
        assert _lint("nKey = 12345;", mode="strict") == []

    def test_number_literal_is_not_reported_for_custom_secret_names(self):
        # Custom secret_names are just as generic as the strict-only
        # fragments by default, so they stay string-only too.
        assert _lint("nKennwort = 12345;", secret_names=["kennwort"]) == []

    def test_non_secret_name_is_ignored(self):
        assert _lint("nRetries = 'abc';") == []

    def test_name_match_is_case_insensitive_and_substring_based(self):
        code = "sPASSWORD = 'a';\nvPwd_Prod = 'b';\nsMyTokenValue = 'c';"
        assert _names(_lint(code)) == ["sMyTokenValue", "sPASSWORD", "vPwd_Prod"]

    def test_predefined_datasource_password_is_reported(self):
        issues = _lint("DatasourcePassword = 'hunter2';")
        assert _names(issues) == ["DatasourcePassword"]

    def test_issue_position_points_at_the_variable(self):
        code = "sTemp = 'x';\nsPassword = 'hunter2';"
        issues = _lint(code)
        assert len(issues) == 1
        assert issues[0].line == 2
        assert issues[0].column == 1

    def test_assignment_inside_a_block_is_reported(self):
        code = "if(1 = 1);\n  sPassword = 'hunter2';\nendif;"
        assert len(_lint(code)) == 1

    def test_noqa_suppresses_the_finding(self):
        code = "sPassword = 'REPLACE_ME';  # noqa: X130"
        assert _lint(code) == []


class TestCubeSource:
    def test_cell_read_is_reported(self):
        issues = _lint("sPassword = CellGetS('Config', 'Api', 'Key');")
        assert len(issues) == 1
        assert issues[0].rule_id == "X130"

    def test_every_cube_read_function_is_reported(self):
        code = (
            "sPassword = CellGetS('C', 'a', 'b');\n"
            "nPassword = CellGetN('C', 'a', 'b');\n"
            "sPwd1 = AttrS('User', 'u1', 'Pwd');\n"
            "nPwd2 = AttrN('User', 'u1', 'Pwd');\n"
            "sPwd3 = ElementAttrS('User', '', 'u1', 'Pwd');\n"
            "nPwd4 = ElementAttrN('User', '', 'u1', 'Pwd');"
        )
        assert len(_lint(code)) == 6

    def test_function_name_match_is_case_insensitive(self):
        assert len(_lint("sPassword = CELLGETS('C', 'a', 'b');")) == 1

    def test_non_secret_name_reading_a_cube_is_allowed(self):
        assert _lint("sCustomer = CellGetS('Sales', '2026', 'Customer');") == []

    def test_nested_cube_read_is_not_reported(self):
        # Known, deliberate gap: only a direct call on the right-hand side counts.
        assert _lint("sPassword = Trim(CellGetS('Config', 'Api', 'Key'));") == []

    def test_issue_position_points_at_the_variable(self):
        code = "sTemp = 'x';\nsPassword = CellGetS('Config', 'Api', 'Key');"
        issues = _lint(code)
        assert len(issues) == 1
        assert issues[0].line == 2
        assert issues[0].column == 1

    def test_allow_secrets_in_cubes_suppresses_the_finding(self):
        code = "sPassword = CellGetS('Config', 'Api', 'Key');"
        assert _lint(code, allow_secrets_in_cubes=True) == []

    def test_allow_secrets_in_cubes_leaves_literals_reported(self):
        code = "sPassword = 'hunter2';"
        assert len(_lint(code, allow_secrets_in_cubes=True)) == 1


class TestMessage:
    def test_message_never_echoes_the_value(self):
        issues = _lint("sPassword = 'letmein123';")
        assert "letmein123" not in issues[0].message

    def test_message_names_the_variable_and_suggests_a_parameter(self):
        issues = _lint("sPassword = 'hunter2';")
        assert "sPassword" in issues[0].message
        assert "parameter" in issues[0].message.lower()

    def test_cube_message_names_the_reading_function(self):
        issues = _lint("sPassword = CellGetS('Config', 'Api', 'Key');")
        assert "CellGetS" in issues[0].message
        assert "cube" in issues[0].message.lower()

    def test_cube_message_never_echoes_the_coordinates(self):
        issues = _lint("sPassword = CellGetS('SecretCube', 'Api', 'KeyElem');")
        assert "SecretCube" not in issues[0].message
        assert "KeyElem" not in issues[0].message


class TestModes:
    CODE = (
        "sPassword = 'a';\n"
        "sApiKey = 'b';\n"
        "sToken = 'c';\n"
        "sKey = 'd';\n"
        "sAuthority = 'e';"
    )

    def test_relaxed_matches_only_password_like_names(self):
        assert _names(_lint(self.CODE, mode="relaxed")) == ["sPassword"]

    def test_standard_is_the_default(self):
        assert _names(_lint(self.CODE)) == _names(_lint(self.CODE, mode="standard"))

    def test_standard_adds_api_keys_and_tokens(self):
        assert _names(_lint(self.CODE, mode="standard")) == [
            "sApiKey",
            "sPassword",
            "sToken",
        ]

    def test_strict_adds_key_and_auth(self):
        assert _names(_lint(self.CODE, mode="strict")) == [
            "sApiKey",
            "sAuthority",
            "sKey",
            "sPassword",
            "sToken",
        ]

    def test_secret_names_extend_the_preset(self):
        code = "sKennwort = 'a';\nsPassword = 'b';"
        assert _names(_lint(code, secret_names=["kennwort"])) == [
            "sKennwort",
            "sPassword",
        ]

    def test_custom_mode_uses_only_the_configured_names(self):
        code = "sKennwort = 'a';\nsPassword = 'b';"
        issues = _lint(code, mode="custom", secret_names=["kennwort"])
        assert _names(issues) == ["sKennwort"]

    def test_custom_mode_without_names_reports_nothing(self):
        assert _lint("sPassword = 'hunter2';", mode="custom") == []

    def test_unknown_mode_falls_back_to_standard(self):
        rule = HardcodedSecretRule(mode="nonsense")
        assert rule.mode == "standard"
        assert rule.patterns == HardcodedSecretRule().patterns


class TestConfiguration:
    def test_rule_is_enabled_by_default(self):
        assert len(_x130_rules()) == 1

    def test_rule_can_be_disabled(self):
        cfg = {"rules": {"hardcoded_secret": {"enabled": False}}}
        assert _x130_rules(cfg) == []

    def test_mode_from_config(self):
        cfg = {"rules": {"hardcoded_secret": {"mode": "strict"}}}
        rule = _x130_rules(cfg)[0]
        assert rule.mode == "strict"
        assert "auth" in rule.patterns

    def test_secret_names_from_config(self):
        cfg = {
            "rules": {
                "hardcoded_secret": {"mode": "custom", "secret_names": ["Kennwort"]}
            }
        }
        rule = _x130_rules(cfg)[0]
        assert rule.secret_names == frozenset({"kennwort"})
        assert rule.patterns == frozenset({"kennwort"})

    def test_allow_secrets_in_cubes_from_config(self):
        cfg = {"rules": {"hardcoded_secret": {"allow_secrets_in_cubes": True}}}
        assert _x130_rules(cfg)[0].allow_secrets_in_cubes is True

    def test_from_config_defaults(self):
        rule = HardcodedSecretRule.from_config({"enabled": True})[0]
        assert rule.mode == "standard"
        assert rule.secret_names == frozenset()
        assert rule.allow_secrets_in_cubes is False


class TestConstantEvaluation:
    """What the index adds on top of the syntax-only checks above."""

    def test_concatenated_literals_are_reported(self):
        # The reason this class exists: no String node sits on the right-hand
        # side, so only the folded value gives the secret away.
        issues = _lint_with_constant_evaluation("sPassword = 'let' | 'mein';")
        assert len(issues) == 1
        assert issues[0].rule_id == "X130"

    def test_concatenation_through_a_variable_is_reported(self):
        code = "sPart = 'let';\nsPassword = sPart | 'mein';"
        assert _names(_lint_with_constant_evaluation(code)) == ["sPassword"]

    def test_literal_carried_over_from_another_variable_is_reported(self):
        code = "sTemp = 'letmein';\nsPassword = sTemp;"
        assert _names(_lint_with_constant_evaluation(code)) == ["sPassword"]

    def test_concatenation_is_missed_without_the_index(self):
        # Pins the split: the syntax-only path cannot see a folded value.
        # constants=None only happens here in tests -- lint_process_model
        # always builds the index in production -- so this also pins that
        # LintContext.possible_values() degrades to UNASSIGNED instead of
        # requiring rules to special-case a missing index.
        assert _lint("sPassword = 'let' | 'mein';") == []

    def test_parameter_is_still_allowed(self):
        assert _lint_with_constant_evaluation("sPassword = pPassword;") == []

    def test_partially_known_concatenation_is_not_reported(self):
        # Known, deliberate gap: the secret itself may live in the dynamic part.
        assert _lint_with_constant_evaluation("sPassword = 'prefix_' | pDyn;") == []

    def test_number_carried_through_a_variable_is_reported_for_password_like_names(
        self,
    ):
        # A direct numeric literal is already caught without the index (see
        # TestDetection); this pins that the index extends the same numeric
        # allowance to a value carried over from another variable.
        code = "nTemp = 12345;\nsPassword = nTemp;"
        assert _names(_lint_with_constant_evaluation(code)) == ["sPassword"]

    def test_number_is_not_reported_for_strict_only_names(self):
        code = "nTemp = 12345;\nnKey = nTemp;"
        assert _lint_with_constant_evaluation(code, mode="strict") == []

    def test_number_is_not_reported_for_custom_secret_names(self):
        code = "nTemp = 12345;\nnKennwort = nTemp;"
        assert _lint_with_constant_evaluation(code, secret_names=["kennwort"]) == []

    def test_empty_string_is_not_reported(self):
        assert _lint_with_constant_evaluation("sPassword = '';") == []

    def test_concatenated_empty_strings_are_not_reported(self):
        assert _lint_with_constant_evaluation("sPassword = '' | '';") == []

    def test_literal_in_a_while_body_is_still_reported(self):
        # The index forgets loop values, so only the syntax check catches this.
        code = "nI = 0;\nwhile(nI < 2);\n  sPassword = 'hunter2';\nend;"
        assert len(_lint_with_constant_evaluation(code)) == 1

    def test_assignment_inside_an_if_is_reported(self):
        # The branch-join event lands on the assignment's own line and is never
        # complete, so this only holds because the rule asks any_of, not exact.
        code = "if(1 = 1);\n  sPassword = 'hunter2';\nendif;"
        assert len(_lint_with_constant_evaluation(code)) == 1

    def test_both_branches_of_an_if_else_are_reported(self):
        code = "if(1 = 1);\n  sPassword = 'a';\nelse;\n  sPassword = 'b';\nendif;"
        assert len(_lint_with_constant_evaluation(code)) == 2

    def test_direct_literal_is_reported_exactly_once(self):
        # Both detectors fire here; the issue must not be duplicated.
        assert len(_lint_with_constant_evaluation("sPassword = 'hunter2';")) == 1

    def test_cube_read_is_reported_exactly_once(self):
        issues = _lint_with_constant_evaluation(
            "sPassword = CellGetS('Config', 'Api', 'Key');"
        )
        assert len(issues) == 1
        assert "CellGetS" in issues[0].message

    def test_allow_secrets_in_cubes_still_suppresses_the_cube_finding(self):
        code = "sPassword = CellGetS('Config', 'Api', 'Key');"
        assert _lint_with_constant_evaluation(code, allow_secrets_in_cubes=True) == []

    def test_folded_value_never_reaches_the_message(self):
        issues = _lint_with_constant_evaluation("sPassword = 'let' | 'mein123';")
        assert "letmein123" not in issues[0].message
        assert "mein123" not in issues[0].message

    def test_reported_through_the_full_pipeline(self):
        # Proves the index reaches the rule in the real per-procedure pipeline,
        # not just when a test hands it a context.
        process = ProcessIR(
            name="test_process",
            prolog=ProcedureInfo(code="sPassword = 'let' | 'mein';"),
        )
        linter = Linter(rules=[], statement_rules=[HardcodedSecretRule()])
        issues = lint_process_model(process, linter)
        assert [issue.rule_id for _, issue, _ in issues] == ["X130"]
