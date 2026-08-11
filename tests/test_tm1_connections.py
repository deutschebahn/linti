"""Tests for TM1 connection profiles — above all, that they hold no secrets."""

import pytest
import yaml

from linti.tm1.connections import (
    CONNECTIONS_ENV,
    ConnectionsError,
    ConnectionsFile,
    default_connections_path,
)

TWO_PROFILES = {
    "default_profile": "prod",
    "profiles": {
        "prod": {
            "address": "tm1.corp.local",
            "port": 8010,
            "ssl": True,
            "user": "admin",
        },
        "dev": {"base_url": "https://pa.example.com/api/v1", "user": "svc_lint"},
    },
}


@pytest.fixture
def connections_file(tmp_path):
    def write(data):
        path = tmp_path / "connections.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    return write


class TestSecretsAreRejected:
    """The whole point of a separate, checked-in-free profile file."""

    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "cam_passport",
            "api_key",
            "application_client_secret",
            "decode_b64",
        ],
    )
    def test_secret_bearing_keys_are_refused(self, connections_file, key):
        path = connections_file(
            {"profiles": {"prod": {"address": "h", "user": "u", key: "secret"}}}
        )
        with pytest.raises(ConnectionsError) as exc_info:
            ConnectionsFile.load(path)
        message = str(exc_info.value)
        assert key in message
        # The error has to say what to do instead, not just what is wrong.
        assert "linti tm1 login" in message

    def test_the_secret_value_is_not_echoed_back(self, connections_file):
        path = connections_file(
            {"profiles": {"prod": {"address": "h", "user": "u", "password": "hunter2"}}}
        )
        with pytest.raises(ConnectionsError) as exc_info:
            ConnectionsFile.load(path)
        assert "hunter2" not in str(exc_info.value)

    def test_unknown_fields_are_refused_too(self, connections_file):
        path = connections_file({"profiles": {"prod": {"address": "h", "typo": 1}}})
        with pytest.raises(ConnectionsError, match="typo"):
            ConnectionsFile.load(path)

    def test_the_model_has_no_password_field_at_all(self):
        from linti.tm1.connections import ConnectionProfile

        assert "password" not in ConnectionProfile.model_fields


class TestLoading:
    def test_profiles_are_parsed(self, connections_file):
        parsed = ConnectionsFile.load(connections_file(TWO_PROFILES))
        assert sorted(parsed.profiles) == ["dev", "prod"]
        assert parsed.profiles["prod"].address == "tm1.corp.local"
        assert parsed.profiles["prod"].port == 8010
        assert parsed.profiles["dev"].base_url.endswith("/api/v1")

    def test_defaults_come_from_tm1py_not_from_linti(self, connections_file):
        """Unset optional fields stay None so TM1py's own defaults apply."""
        parsed = ConnectionsFile.load(
            connections_file({"profiles": {"p": {"address": "h", "user": "u"}}})
        )
        profile = parsed.profiles["p"]
        assert profile.port is None
        assert profile.timeout is None
        assert profile.ssl is True
        assert profile.session_context == "linti"

    def test_a_profile_needs_an_address_or_base_url(self, connections_file):
        path = connections_file({"profiles": {"p": {"user": "u"}}})
        with pytest.raises(ConnectionsError, match="address"):
            ConnectionsFile.load(path)

    def test_missing_file_says_where_it_looked(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(ConnectionsError) as exc_info:
            ConnectionsFile.load(missing)
        assert str(missing) in str(exc_info.value)

    def test_malformed_yaml(self, tmp_path):
        path = tmp_path / "connections.yaml"
        path.write_text("profiles: [unclosed", encoding="utf-8")
        with pytest.raises(ConnectionsError):
            ConnectionsFile.load(path)

    def test_non_mapping_top_level(self, tmp_path):
        path = tmp_path / "connections.yaml"
        path.write_text("- just\n- a list\n", encoding="utf-8")
        with pytest.raises(ConnectionsError, match="mapping"):
            ConnectionsFile.load(path)


class TestResolve:
    def test_named_profile(self, connections_file):
        parsed = ConnectionsFile.load(connections_file(TWO_PROFILES))
        name, profile = parsed.resolve("dev")
        assert name == "dev"
        assert profile.user == "svc_lint"

    def test_default_profile_is_used_when_none_is_named(self, connections_file):
        parsed = ConnectionsFile.load(connections_file(TWO_PROFILES))
        assert parsed.resolve()[0] == "prod"

    def test_a_lone_profile_is_the_default(self, connections_file):
        data = {"profiles": {"only": {"address": "h", "user": "u"}}}
        parsed = ConnectionsFile.load(connections_file(data))
        assert parsed.resolve()[0] == "only"

    def test_several_profiles_without_a_default_is_ambiguous(self, connections_file):
        data = dict(TWO_PROFILES)
        data.pop("default_profile")
        parsed = ConnectionsFile.load(connections_file(data))
        with pytest.raises(ConnectionsError) as exc_info:
            parsed.resolve()
        assert "--profile" in str(exc_info.value)
        assert "dev, prod" in str(exc_info.value)

    def test_unknown_profile_lists_the_available_ones(self, connections_file):
        parsed = ConnectionsFile.load(connections_file(TWO_PROFILES))
        with pytest.raises(ConnectionsError) as exc_info:
            parsed.resolve("staging")
        assert "dev, prod" in str(exc_info.value)


class TestDefaultPath:
    def test_env_var_overrides_the_config_dir(self, monkeypatch, tmp_path):
        target = tmp_path / "elsewhere.yaml"
        monkeypatch.setenv(CONNECTIONS_ENV, str(target))
        assert default_connections_path() == target

    def test_falls_back_to_the_app_config_dir(self, monkeypatch):
        monkeypatch.delenv(CONNECTIONS_ENV, raising=False)
        assert default_connections_path().name == "connections.yaml"
