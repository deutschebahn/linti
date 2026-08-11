"""Test doubles for a connected TM1py service.

Hand-written rather than ``MagicMock`` so the duck-type contract the provider
relies on is written down somewhere: anything with these attributes works, and a
test that needs a new one has to add it here deliberately.

Nothing in this module imports TM1py — the whole read path is exercised without
the ``tm1`` extra installed.
"""

CRLF = "\r\n"

#: What TM1 actually wraps every procedure in.
GENERATED_BLOCK = (
    "#****Begin: Generated Statements***"
    + CRLF
    + "NULL;"
    + CRLF
    + "#****End: Generated Statements****"
    + CRLF
)


def server_procedure(*lines: str) -> str:
    """A procedure the way a server hands it over: generated block, CRLF."""
    return GENERATED_BLOCK + CRLF.join(lines) + CRLF if lines else GENERATED_BLOCK


class FakeProcess:
    """A TM1py-like ``Process``."""

    def __init__(
        self,
        name,
        prolog="",
        metadata="",
        data="",
        epilog="",
        parameters=None,
        variables=None,
        datasource_type=None,
        datasource_query=None,
    ):
        self.name = name
        self.prolog_procedure = prolog
        self.metadata_procedure = metadata
        self.data_procedure = data
        self.epilog_procedure = epilog
        self.parameters = parameters if parameters is not None else []
        self.variables = variables if variables is not None else []
        self.datasource_type = datasource_type
        self.datasource_query = datasource_query


class FakeProcessService:
    """A TM1py-like ``ProcessService`` over an in-memory dict."""

    def __init__(self, processes=None, fail_on=None):
        #: name -> FakeProcess
        self.processes = {p.name: p for p in (processes or [])}
        #: names whose get() raises, to exercise the per-process failure path
        self.fail_on = set(fail_on or ())
        self.get_calls = []

    def get_all_names(self):
        return list(self.processes)

    def get(self, name):
        self.get_calls.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"simulated server failure for {name}")
        return self.processes.get(name)


class FakeServerService:
    def __init__(self, version="11.8.00000.10"):
        self.version = version

    def get_product_version(self):
        return self.version


class FakeTM1Service:
    """A TM1py-like ``TM1Service``, usable as a context manager."""

    def __init__(self, processes=None, fail_on=None, version="11.8.00000.10"):
        self.processes = FakeProcessService(processes, fail_on)
        self.server = FakeServerService(version)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed = True
        return False


class FakeKeyring:
    """An in-memory stand-in for the ``keyring`` module."""

    def __init__(self, broken=False):
        self.store = {}
        #: When set, every operation raises — a machine with no usable backend.
        self.broken = broken

    def _check(self):
        if self.broken:
            raise RuntimeError("no keyring backend available")

    def get_password(self, service, user):
        self._check()
        return self.store.get((service, user))

    def set_password(self, service, user, password):
        self._check()
        self.store[(service, user)] = password

    def delete_password(self, service, user):
        self._check()
        del self.store[(service, user)]
