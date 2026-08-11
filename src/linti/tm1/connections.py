"""Connection profiles for TM1 servers — deliberately secret-free.

Profiles live outside the project, in a per-user file, because a connection is a
property of the machine and the person, not of the repository. ``linti.yaml`` is
normally checked in; putting internal host names and service accounts there
leaks them into the repo.

**No profile field holds a password.** Secrets go to the system keyring (see
:mod:`linti.tm1.credentials`); this file only names which profile a secret
belongs to. That is enforced, not merely documented: the model forbids extra
fields, and the known secret keys are rejected with an explicit pointer to
``linti tm1 login`` rather than pydantic's generic "extra field" complaint. A
password pasted in here therefore fails loudly on the next run instead of
quietly sitting on disk.
"""

import os
from pathlib import Path
from typing import Optional, Union

import typer
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Environment variable pointing at an alternative profile file.
CONNECTIONS_ENV = "LINTI_CONNECTIONS"

#: Base name of the profile file inside the per-user config directory.
CONNECTIONS_FILENAME = "connections.yaml"

# Fields that would carry a secret. Listed explicitly so the error can name the
# right alternative instead of leaving the user with "extra inputs are not
# permitted".
_SECRET_FIELDS = frozenset(
    {
        "password",
        "cam_passport",
        "api_key",
        "application_client_secret",
        "decode_b64",
    }
)


def _secret_key_message(key: str, profile: str) -> str:
    return (
        f"'{key}' is not allowed in {CONNECTIONS_FILENAME} (profile {profile!r}): "
        f"linti never stores secrets on disk. Remove it and run "
        f"'linti tm1 login {profile}' to save the password in your system "
        f"keyring, or set LINTI_TM1_PASSWORD for CI."
    )


def _reject_secret_keys(raw: dict) -> None:
    """Refuse secret-bearing keys before pydantic ever sees the data.

    Deliberately ahead of model validation: a pydantic ``ValidationError``
    renders the offending input back into its message, so letting it handle a
    stray ``password:`` would print the password itself — straight into
    whatever log the run writes to. Raising here keeps the value out of every
    message linti produces.
    """
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        return
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        for key in profile:
            if key in _SECRET_FIELDS:
                raise ConnectionsError(_secret_key_message(key, str(profile_name)))


class ConnectionsError(ValueError):
    """The profile file is missing, unreadable, or does not define the profile."""


def default_connections_path() -> Path:
    """Where profiles live when neither the env var nor a CLI flag says otherwise.

    ``typer.get_app_dir`` is click's platform-correct helper: ``~/.config/linti``
    on Linux, ``~/Library/Application Support/linti`` on macOS,
    ``%APPDATA%\\linti`` on Windows.
    """
    override = os.environ.get(CONNECTIONS_ENV)
    if override:
        return Path(override).expanduser()
    return Path(typer.get_app_dir("linti")) / CONNECTIONS_FILENAME


class ConnectionProfile(BaseModel):
    """One TM1 server, addressed the way TM1py's ``TM1Service`` expects.

    Either ``address`` (+ ``port``) or ``base_url`` identifies the server;
    TM1py accepts both and this model does not duplicate its precedence rules
    beyond requiring that one of them is present.
    """

    # extra="forbid" is the backstop; _reject_secrets below turns the two cases
    # that actually matter into a message that says what to do instead.
    model_config = ConfigDict(extra="forbid")

    address: Optional[str] = None
    port: Optional[int] = None
    ssl: bool = True
    base_url: Optional[str] = None
    user: Optional[str] = None
    namespace: Optional[str] = None
    instance: Optional[str] = None
    database: Optional[str] = None
    #: ``True``/``False`` or a path to a ``.cer`` bundle, as TM1py takes it.
    verify: Union[bool, str] = True
    timeout: Optional[float] = None
    #: Shows up in the "Context" column in Arc and TM1top, so a linting session
    #: is recognisable as one.
    session_context: str = "linti"

    @model_validator(mode="after")
    def _require_an_address(self) -> "ConnectionProfile":
        if not self.address and not self.base_url:
            raise ValueError(
                "a profile needs either 'address' (with 'port') or 'base_url'"
            )
        return self


class ConnectionsFile(BaseModel):
    """The parsed profile file."""

    model_config = ConfigDict(extra="forbid")

    profiles: dict[str, ConnectionProfile] = Field(default_factory=dict)
    default_profile: Optional[str] = None

    #: Where this came from, for error messages. Not part of the YAML.
    path: Optional[Path] = Field(default=None, exclude=True)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ConnectionsFile":
        """Read and validate the profile file.

        Raises:
            ConnectionsError: if the file is missing or cannot be parsed. A
                missing file is an error rather than an empty result: every
                caller here needs a profile, so "no profiles" would only
                surface as a confusing lookup failure one step later.
        """
        path = path or default_connections_path()
        if not path.is_file():
            raise ConnectionsError(
                f"No TM1 connection profiles found at {path}. Create the file "
                f"with a 'profiles:' block (see the README), or point "
                f"{CONNECTIONS_ENV} at an existing one."
            )

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConnectionsError(f"Cannot read {path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ConnectionsError(
                f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
            )

        # Before pydantic, so a stray password is never rendered into an error.
        _reject_secret_keys(raw)

        try:
            parsed = cls(**raw)
        except ConnectionsError:
            raise
        except ValueError as exc:
            raise ConnectionsError(f"{path}: {exc}") from exc

        parsed.path = path
        return parsed

    def resolve(self, name: Optional[str] = None) -> tuple[str, ConnectionProfile]:
        """Return ``(name, profile)`` for *name*, or for the default profile.

        With no *name*, ``default_profile`` wins; failing that, a file holding
        exactly one profile makes that one the default. Anything else is
        ambiguous and says so.
        """
        where = self.path or default_connections_path()

        if not self.profiles:
            raise ConnectionsError(f"{where} defines no profiles")

        if name is None:
            name = self.default_profile
        if name is None and len(self.profiles) == 1:
            name = next(iter(self.profiles))
        if name is None:
            raise ConnectionsError(
                f"{where} defines several profiles and no 'default_profile'. "
                f"Pick one with --profile: {self.profile_names()}"
            )

        profile = self.profiles.get(name)
        if profile is None:
            raise ConnectionsError(
                f"{where} has no profile named {name!r}. Available: "
                f"{self.profile_names()}"
            )
        return name, profile

    def profile_names(self) -> str:
        """Comma-separated profile names, for error messages."""
        return ", ".join(sorted(self.profiles)) or "(none)"
