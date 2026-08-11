"""End-to-end tests for the ``linti tm1`` command group.

No server and no TM1py: ``connect`` is replaced by a fake service, which is the
seam the whole design is built around.
"""

import pytest
import yaml
from typer.testing import CliRunner

from linti.cli import tm1_cli
from linti.cli.main import app
from linti.tm1 import credentials
from tm1_fakes import FakeKeyring, FakeProcess, FakeTM1Service, server_procedure

runner = CliRunner()

PROFILES = {
    "default_profile": "prod",
    "profiles": {
        "prod": {"address": "tm1.corp.local", "port": 8010, "user": "admin"},
        "dev": {"address": "dev.local", "port": 8010, "user": "svc"},
    },
}

# Deliberately messy: a long line (F250) and a lowercase keyword (F110) give the
# report something to find.
DIRTY = server_procedure(
    "if(1=1);",
    "sVeryLongVariableName = 'x';",
    "endif;",
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A working directory with a linti.yaml and a connections.yaml."""
    (tmp_path / "linti.yaml").write_text("rules: {}\n", encoding="utf-8")
    connections = tmp_path / "connections.yaml"
    connections.write_text(yaml.safe_dump(PROFILES), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return connections


@pytest.fixture
def service(monkeypatch):
    """A fake TM1 server, injected in place of a real connection."""
    fake = FakeTM1Service(
        [
            FakeProcess("Sales.Load", prolog=DIRTY),
            FakeProcess("Sales.Report", prolog=server_procedure("nX = 1;")),
            FakeProcess("}Control", prolog=DIRTY),
        ]
    )

    def fake_connect(profile, password, label="TM1"):
        fake.used_password = password
        fake.used_profile = profile
        return fake

    monkeypatch.setattr(tm1_cli, "connect", fake_connect)
    return fake


@pytest.fixture(autouse=True)
def env_password(monkeypatch):
    """Every test authenticates through the documented CI path."""
    monkeypatch.setenv("LINTI_TM1_PASSWORD", "from-env")


def invoke(*args, connections=None):
    base = ["tm1", *args]
    if connections is not None:
        base += ["--connections", str(connections)]
    return runner.invoke(app, base)


class TestLint:
    def test_lints_every_process_and_skips_control_processes(self, project, service):
        result = invoke("lint", "-p", "prod", connections=project)
        # A clean process contributes no report lines, so what was linted is
        # what was fetched — not what shows up in the output.
        assert service.processes.get_calls == ["Sales.Load", "Sales.Report"]
        assert "tm1://prod/Sales.Load" in result.output
        assert "}Control" not in result.output

    def test_control_processes_can_be_opted_in(self, project, service):
        result = invoke("lint", "-p", "prod", "--include-control", connections=project)
        assert "}Control" in result.output

    def test_patterns_filter_case_insensitively(self, project, service):
        result = invoke("lint", "-p", "prod", "sales.l*", connections=project)
        assert "Sales.Load" in result.output
        assert "Sales.Report" not in result.output

    def test_pattern_matching_nothing_exits_zero_with_an_explanation(
        self, project, service
    ):
        result = invoke("lint", "-p", "prod", "Nope*", connections=project)
        assert result.exit_code == 0
        assert "No processes on prod match Nope*" in result.output

    def test_single_process_gets_the_single_source_report(self, project, service):
        result = invoke("lint", "-p", "prod", "Sales.Load", connections=project)
        assert "LINTING ISSUES" in result.output
        assert "Total Issues:" in result.output

    def test_no_generated_statement_noise_in_the_report(self, project, service):
        """The whole reason tm1_code exists.

        Raw server text is CRLF-terminated and opens with TM1's generated block,
        so without decoding every line would report F270 and the boilerplate
        would be linted as user code.
        """
        result = invoke("lint", "-p", "prod", connections=project)
        assert "F270" not in result.output
        assert "Generated Statements" not in result.output

    def test_line_numbers_count_from_the_real_tm1_line(self, project, service):
        """Findings must line up with what the process editor shows."""
        result = invoke("lint", "-p", "prod", "Sales.Load", connections=project)
        # The generated block occupies TM1 lines 1-3, so nothing can be reported
        # before line 4.
        reported = [
            line
            for line in result.output.splitlines()
            if "tm1://prod/Sales.Load:" in line
        ]
        assert reported
        for line in reported:
            assert int(line.split(":")[2]) >= 4

    def test_rule_selection_is_honoured(self, project, service):
        result = invoke("lint", "-p", "prod", "--select", "F110", connections=project)
        assert "F250" not in result.output

    def test_severity_floor_is_honoured(self, project, service):
        result = invoke(
            "lint", "-p", "prod", "--severity", "error", connections=project
        )
        assert "⚠️" not in result.output

    def test_the_session_is_closed(self, project, service):
        invoke("lint", "-p", "prod", connections=project)
        assert service.closed

    def test_a_failing_process_does_not_abort_the_others(
        self, project, service, monkeypatch
    ):
        service.processes.fail_on = {"Sales.Report"}
        result = invoke("lint", "-p", "prod", connections=project)
        assert "Sales.Load" in result.output
        assert "tm1://prod/Sales.Report" in result.output
        assert result.exit_code != 0


class TestAutoFixIsRefused:
    def test_auto_fix_explains_itself_instead_of_being_an_unknown_option(
        self, project, service
    ):
        result = invoke("lint", "-p", "prod", "--auto-fix", connections=project)
        assert result.exit_code == 2
        assert "not supported for TM1 connections" in result.output
        assert "No such option" not in result.output

    def test_the_report_does_not_advertise_auto_fix(self, project, service):
        result = invoke("lint", "-p", "prod", connections=project)
        assert "--auto-fix" not in result.output
        assert "Auto-fix is not supported" in result.output


class TestProfileHandling:
    def test_default_profile_is_used_without_p(self, project, service):
        result = invoke("lint", connections=project)
        assert "tm1://prod/" in result.output

    def test_unknown_profile_lists_the_available_ones(self, project, service):
        result = invoke("lint", "-p", "staging", connections=project)
        assert result.exit_code == 2
        assert "dev, prod" in result.output

    def test_profile_without_a_user_is_refused(self, tmp_path, monkeypatch, service):
        connections = tmp_path / "connections.yaml"
        connections.write_text(
            yaml.safe_dump({"profiles": {"p": {"address": "h"}}}), encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        result = invoke("lint", connections=connections)
        assert result.exit_code == 2
        assert "has no 'user'" in result.output

    def test_missing_connections_file_says_where_it_looked(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = invoke("lint", connections=tmp_path / "nope.yaml")
        assert result.exit_code == 2
        assert "nope.yaml" in result.output


class TestProfilesCommand:
    def test_lists_profiles_and_marks_the_default(self, project, monkeypatch):
        monkeypatch.setattr(credentials, "_import_keyring", lambda: FakeKeyring())
        result = invoke("profiles", connections=project)
        assert "prod: admin@tm1.corp.local:8010" in result.output
        assert "default" in result.output

    def test_reports_whether_a_password_is_stored_never_the_value(
        self, project, monkeypatch
    ):
        fake = FakeKeyring()
        monkeypatch.setattr(credentials, "_import_keyring", lambda: fake)
        credentials.store_password("prod", "admin", "hunter2")
        result = invoke("profiles", connections=project)
        assert "password stored" in result.output
        assert "hunter2" not in result.output


class TestLoginLogout:
    def test_login_verifies_before_storing(self, project, service, monkeypatch):
        fake = FakeKeyring()
        monkeypatch.setattr(credentials, "_import_keyring", lambda: fake)
        monkeypatch.setattr(credentials, "prompt_password", lambda *a: "typed-secret")

        result = invoke("login", "prod", connections=project)
        assert result.exit_code == 0
        assert "11.8" in result.output
        assert credentials.password_from_keyring("prod", "admin") == "typed-secret"

    def test_login_stores_nothing_when_the_server_refuses(self, project, monkeypatch):
        from linti.tm1.service import TM1ConnectionError

        fake = FakeKeyring()
        monkeypatch.setattr(credentials, "_import_keyring", lambda: fake)
        monkeypatch.setattr(credentials, "prompt_password", lambda *a: "wrong")

        def refuse(profile, password, label="TM1"):
            raise TM1ConnectionError("401 Unauthorized")

        monkeypatch.setattr(tm1_cli, "connect", refuse)

        result = invoke("login", "prod", connections=project)
        assert result.exit_code == 1
        assert "Nothing was stored." in result.output
        assert credentials.password_from_keyring("prod", "admin") is None

    def test_logout_removes_a_stored_password(self, project, monkeypatch):
        fake = FakeKeyring()
        monkeypatch.setattr(credentials, "_import_keyring", lambda: fake)
        credentials.store_password("prod", "admin", "x")

        result = invoke("logout", "prod", connections=project)
        assert result.exit_code == 0
        assert not credentials.has_stored_password("prod", "admin")

    def test_logout_without_a_stored_password_is_not_an_error(
        self, project, monkeypatch
    ):
        monkeypatch.setattr(credentials, "_import_keyring", lambda: FakeKeyring())
        result = invoke("logout", "prod", connections=project)
        assert result.exit_code == 0
        assert "No password was stored" in result.output
