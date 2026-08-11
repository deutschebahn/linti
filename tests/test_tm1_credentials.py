"""Tests for password resolution.

The precedence chain is the security-relevant part: a stale keyring entry must
never win over an explicit environment variable, and nothing may prompt when
there is no terminal.
"""

import pytest

from linti.tm1 import credentials
from linti.tm1.credentials import CredentialsError
from tm1_fakes import FakeKeyring

PROFILE = "prod"
USER = "admin"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No inherited LINTI_TM1_* variables leaking into a test."""
    for name in list(__import__("os").environ):
        if name.startswith("LINTI_TM1"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(credentials, "_import_keyring", lambda: fake)
    return fake


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.setattr(credentials.sys.stdin, "isatty", lambda: True)


class TestPrecedence:
    def test_profile_env_var_wins_over_everything(self, monkeypatch, keyring, tty):
        keyring.set_password(credentials.keyring_service(PROFILE), USER, "from-keyring")
        monkeypatch.setenv("LINTI_TM1_PASSWORD", "from-generic-env")
        monkeypatch.setenv("LINTI_TM1_PROD_PASSWORD", "from-profile-env")
        monkeypatch.setattr(credentials, "prompt_password", lambda *a: "from-prompt")

        assert credentials.resolve_password(PROFILE, USER) == "from-profile-env"

    def test_generic_env_var_wins_over_the_keyring(self, monkeypatch, keyring):
        keyring.set_password(credentials.keyring_service(PROFILE), USER, "from-keyring")
        monkeypatch.setenv("LINTI_TM1_PASSWORD", "from-generic-env")
        assert credentials.resolve_password(PROFILE, USER) == "from-generic-env"

    def test_keyring_wins_over_the_prompt(self, monkeypatch, keyring):
        keyring.set_password(credentials.keyring_service(PROFILE), USER, "from-keyring")
        monkeypatch.setattr(credentials, "prompt_password", lambda *a: "from-prompt")
        assert credentials.resolve_password(PROFILE, USER) == "from-keyring"

    def test_prompt_is_the_last_resort(self, monkeypatch, keyring):
        monkeypatch.setattr(credentials, "prompt_password", lambda *a: "typed")
        assert credentials.resolve_password(PROFILE, USER) == "typed"


class TestEnvVarNaming:
    @pytest.mark.parametrize(
        "profile,expected",
        [
            ("prod", "LINTI_TM1_PROD_PASSWORD"),
            ("my-dev", "LINTI_TM1_MY_DEV_PASSWORD"),
            ("pa.cloud", "LINTI_TM1_PA_CLOUD_PASSWORD"),
        ],
    )
    def test_profile_names_become_valid_variable_names(self, profile, expected):
        assert credentials.env_var_name(profile) == expected


class TestNoKeyringAvailable:
    def test_missing_package_degrades_to_no_stored_password(self, monkeypatch):
        monkeypatch.setattr(credentials, "_import_keyring", lambda: None)
        assert credentials.password_from_keyring(PROFILE, USER) is None

    def test_broken_backend_degrades_instead_of_raising(self, monkeypatch):
        monkeypatch.setattr(
            credentials, "_import_keyring", lambda: FakeKeyring(broken=True)
        )
        assert credentials.password_from_keyring(PROFILE, USER) is None

    def test_env_var_still_works_without_any_keyring(self, monkeypatch):
        monkeypatch.setattr(credentials, "_import_keyring", lambda: None)
        monkeypatch.setenv("LINTI_TM1_PASSWORD", "ci-secret")
        assert credentials.resolve_password(PROFILE, USER) == "ci-secret"

    def test_storing_without_the_extra_names_the_extra(self, monkeypatch):
        monkeypatch.setattr(credentials, "_import_keyring", lambda: None)
        with pytest.raises(CredentialsError, match=r"linti\[tm1\]"):
            credentials.store_password(PROFILE, USER, "x")


class TestNonInteractive:
    def test_no_terminal_means_no_prompt(self, monkeypatch, keyring):
        monkeypatch.setattr(credentials.sys.stdin, "isatty", lambda: False)
        with pytest.raises(CredentialsError) as exc_info:
            credentials.resolve_password(PROFILE, USER)
        message = str(exc_info.value)
        # Must name both non-interactive ways out, or CI is stuck.
        assert "LINTI_TM1_PROD_PASSWORD" in message
        assert "linti tm1 login" in message

    def test_allow_prompt_false_never_touches_the_terminal(
        self, monkeypatch, keyring, tty
    ):
        def boom(*args):
            raise AssertionError("should not prompt")

        monkeypatch.setattr(credentials, "prompt_password", boom)
        with pytest.raises(CredentialsError, match="linti tm1 login"):
            credentials.resolve_password(PROFILE, USER, allow_prompt=False)


class TestStoreAndDelete:
    def test_store_then_read_back(self, keyring):
        credentials.store_password(PROFILE, USER, "s3cret")
        assert credentials.password_from_keyring(PROFILE, USER) == "s3cret"
        assert credentials.has_stored_password(PROFILE, USER)

    def test_entries_are_namespaced_per_profile(self, keyring):
        credentials.store_password("prod", USER, "a")
        credentials.store_password("dev", USER, "b")
        assert credentials.password_from_keyring("prod", USER) == "a"
        assert credentials.password_from_keyring("dev", USER) == "b"

    def test_delete_reports_whether_there_was_anything(self, keyring):
        assert credentials.delete_password(PROFILE, USER) is False
        credentials.store_password(PROFILE, USER, "x")
        assert credentials.delete_password(PROFILE, USER) is True
        assert not credentials.has_stored_password(PROFILE, USER)

    def test_failures_do_not_leak_the_password(self, monkeypatch):
        monkeypatch.setattr(
            credentials, "_import_keyring", lambda: FakeKeyring(broken=True)
        )
        with pytest.raises(CredentialsError) as exc_info:
            credentials.store_password(PROFILE, USER, "hunter2")
        assert "hunter2" not in str(exc_info.value)
