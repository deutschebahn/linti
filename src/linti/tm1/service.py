"""Opening a TM1py session — the only module in linti that imports TM1py.

Keeping the import here, inside the functions, is what makes the ``tm1`` extra
genuinely optional: ``import linti`` never touches TM1py, and everything that
consumes a connection (:class:`linti.provider.tm1.TM1Provider`) is duck-typed
against it, so the whole read path is testable without the package installed.
"""

from typing import Any, Optional

from linti.tm1.connections import ConnectionProfile


class TM1ConnectionError(Exception):
    """The TM1 extra is missing, or the server refused the connection."""


def require_tm1py() -> Any:
    """Return TM1py's ``TM1Service``, or explain how to get it."""
    try:
        from TM1py import TM1Service
    except ImportError as exc:
        raise TM1ConnectionError(
            "Linting a TM1 server needs the 'tm1' extra: pip install \"linti[tm1]\""
        ) from exc
    return TM1Service


def connection_kwargs(profile: ConnectionProfile, password: str) -> dict[str, Any]:
    """Map a profile plus its password onto ``TM1Service(**kwargs)``.

    Only fields the profile actually set are passed on, so TM1py's own defaults
    stay in charge of everything the user did not mention.
    """
    kwargs: dict[str, Any] = {
        "ssl": profile.ssl,
        "verify": profile.verify,
        "session_context": profile.session_context,
        "password": password,
    }
    optional = {
        "address": profile.address,
        "port": profile.port,
        "base_url": profile.base_url,
        "user": profile.user,
        "namespace": profile.namespace,
        "instance": profile.instance,
        "database": profile.database,
        "timeout": profile.timeout,
    }
    kwargs.update({key: value for key, value in optional.items() if value is not None})
    return kwargs


def connect(profile: ConnectionProfile, password: str, *, label: str = "TM1") -> Any:
    """Open a TM1py session for *profile*.

    The caller owns the session and should close it — ``TM1Service`` is a
    context manager, so ``with connect(...) as tm1:`` is the intended use.

    Raises:
        TM1ConnectionError: naming the failure's type but never the password.
            TM1py's exceptions carry the request, and a caught exception is
            re-raised by class name and message only.
    """
    tm1_service = require_tm1py()
    try:
        return tm1_service(**connection_kwargs(profile, password))
    except Exception as exc:
        raise TM1ConnectionError(
            f"Cannot connect to {label}: {type(exc).__name__}: {exc}"
        ) from exc


def server_version(tm1: Any) -> Optional[str]:
    """The server's version, used to prove a login actually works.

    Returns ``None`` when the connection object does not expose one — a test
    double, say. Callers treat that as "connected, version unknown" rather than
    as a failure.
    """
    server = getattr(tm1, "server", None)
    get_version = getattr(server, "get_product_version", None)
    if get_version is None:
        return None
    return get_version()
