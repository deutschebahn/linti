"""Where a TM1 password comes from — and the only place it is allowed to.

Resolution order, first hit wins:

1. ``LINTI_TM1_<PROFILE>_PASSWORD`` — per profile.
2. ``LINTI_TM1_PASSWORD`` — for a single-connection CI job.
3. The system keyring, under ``linti:tm1:<profile>``.
4. An interactive prompt, only when there is a terminal to prompt on.

Deliberately absent: a ``--password`` flag. A password in ``argv`` is visible in
the process list and lands in shell history, so the environment variable is the
documented path for automation instead.

``keyring`` is an optional dependency (the ``tm1`` extra) and, even when
installed, has no usable backend on a headless box. Both cases degrade to "no
stored password" rather than failing, so the environment variable and the prompt
keep working; only :func:`store_password` — where the user explicitly asked for
the keyring — reports the problem.
"""

import getpass
import os
import re
import sys
from typing import Any, Optional

#: Keyring service name. Namespaced so linti's entries are identifiable in the
#: OS credential store and cannot collide with another tool's.
KEYRING_SERVICE_PREFIX = "linti:tm1"

_ENV_PREFIX = "LINTI_TM1"
_ENV_GENERIC = f"{_ENV_PREFIX}_PASSWORD"


class CredentialsError(Exception):
    """No password could be resolved, or the keyring refused to store one."""


def keyring_service(profile: str) -> str:
    """The keyring service name holding *profile*'s password."""
    return f"{KEYRING_SERVICE_PREFIX}:{profile}"


def env_var_name(profile: str) -> str:
    """The per-profile environment variable name for *profile*."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", profile).strip("_").upper()
    return f"{_ENV_PREFIX}_{slug}_PASSWORD"


def _import_keyring() -> Optional[Any]:
    """The ``keyring`` module, or ``None`` when the extra is not installed."""
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def require_keyring() -> Any:
    """The ``keyring`` module, or a CredentialsError naming the extra."""
    keyring = _import_keyring()
    if keyring is None:
        raise CredentialsError(
            "Storing credentials needs the 'tm1' extra: pip install \"linti[tm1]\""
        )
    return keyring


def password_from_env(profile: str) -> Optional[str]:
    """The password from either environment variable, per-profile first."""
    for name in (env_var_name(profile), _ENV_GENERIC):
        value = os.environ.get(name)
        if value:
            return value
    return None


def password_from_keyring(profile: str, user: str) -> Optional[str]:
    """The stored password, or ``None`` if there is none or no keyring at all.

    Never raises: a missing keyring package, a missing backend, or a locked
    store all mean "linti has no stored password here", and the caller still has
    the environment variable and the prompt to fall back on.
    """
    keyring = _import_keyring()
    if keyring is None:
        return None
    try:
        return keyring.get_password(keyring_service(profile), user)
    except Exception:
        # keyring.errors.NoKeyringError and friends cannot be caught by type
        # without importing the package unconditionally, and a broken backend
        # must not take the whole run down.
        return None


def store_password(profile: str, user: str, password: str) -> None:
    """Save *password* for *profile*/*user* in the system keyring."""
    keyring = require_keyring()
    try:
        keyring.set_password(keyring_service(profile), user, password)
    except Exception as exc:
        raise CredentialsError(
            f"Cannot store the password for profile {profile!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def delete_password(profile: str, user: str) -> bool:
    """Remove the stored password. Returns whether there was one to remove."""
    keyring = require_keyring()
    try:
        if keyring.get_password(keyring_service(profile), user) is None:
            return False
        keyring.delete_password(keyring_service(profile), user)
        return True
    except Exception as exc:
        raise CredentialsError(
            f"Cannot delete the password for profile {profile!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def has_stored_password(profile: str, user: str) -> bool:
    """Whether a password is stored — never what it is."""
    return password_from_keyring(profile, user) is not None


def prompt_password(profile: str, user: str) -> str:
    """Ask for the password on the terminal.

    Raises:
        CredentialsError: when there is no terminal, naming both non-interactive
            ways to supply the password. Prompting into a pipe would hang a CI
            job until it timed out.
    """
    if not sys.stdin.isatty():
        raise CredentialsError(
            f"No password for profile {profile!r} (user {user!r}) and no "
            f"terminal to ask on. Set {env_var_name(profile)} (or "
            f"{_ENV_GENERIC}), or run 'linti tm1 login {profile}' on a machine "
            f"with a keyring."
        )
    return getpass.getpass(f"Password for {user}@{profile}: ")


def resolve_password(profile: str, user: str, *, allow_prompt: bool = True) -> str:
    """Return the password for *profile*/*user*, trying every source in order.

    The value is returned, never logged: no caller may put it in a message, and
    the errors raised here name only the profile and user.
    """
    return (
        password_from_env(profile)
        or password_from_keyring(profile, user)
        or (
            prompt_password(profile, user)
            if allow_prompt
            else _no_password(profile, user)
        )
    )


def _no_password(profile: str, user: str) -> str:
    raise CredentialsError(
        f"No password for profile {profile!r} (user {user!r}). Run "
        f"'linti tm1 login {profile}' or set {env_var_name(profile)}."
    )
