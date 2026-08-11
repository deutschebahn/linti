"""Read-only provider for TI processes living on a TM1 server.

This module deliberately does **not** import TM1py. :class:`ProcessProvider` is
a structural protocol, so a provider over a live server only needs an object
that behaves like a connected TM1py service:

- ``tm1.processes`` with ``get_all_names()`` and ``get(name)``
- process objects with ``name``, ``prolog_procedure``, ``metadata_procedure``,
  ``data_procedure``, ``epilog_procedure``, ``parameters`` and ``variables``

Keeping the import out has two payoffs: the whole provider is testable against
a hand-written double with no server and no TM1py installed, and ``linti`` stays
importable without the ``tm1`` extra. Constructing the connection is
:mod:`linti.tm1.service`'s job — the only module that imports TM1py.

The provider is read-only: :meth:`TM1Provider.save_process` raises. Everything
a write-back path would need is already carried on the IR; see that method.
"""

from typing import Any, Callable, NoReturn, Optional

from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import (
    DEFAULT_MAX_FILE_SIZE,
    ProviderError,
    ensure_text_within_size_limit,
    extract_named_entries,
)
from linti.provider.tm1_code import TM1Code, decode_procedure

# TM1's four execution blocks, in execution order. Matches the ProcessIR
# attribute names and the order extract_procedures yields.
SECTIONS = ("prolog", "metadata", "data", "epilog")

# TM1 names its own internal objects with these prefixes. They are not
# user-authored code and linting them is noise.
_CONTROL_PREFIXES = ("}", "{")

#: ``provider_data`` key holding ``{section: TM1Code}``. Namespaced like the
#: other providers' hints (``pa_json_properties``, ``ti_has_regions``).
PROCEDURES_KEY = "tm1_procedures"


class TM1ProviderError(ProviderError):
    """Talking to the TM1 server failed, or its answer could not be used."""


def _procedure_attr(section: str) -> str:
    return f"{section}_procedure"


def process_ir_from_tm1(process: Any) -> ProcessIR:
    """Build a :class:`ProcessIR` from a TM1py-like process object.

    *process* is anything exposing the attributes listed in the module
    docstring — a TM1py ``Process``, or a process object a caller assembled
    themselves. A caller who already holds one needs nothing else::

        issues = lint_process_model(process_ir_from_tm1(process), linter)

    Only the four procedures are interpreted. Parameters and variables are read
    for the context-aware rules but never written back.

    The returned IR holds no reference to *process*: it stays a plain data
    snapshot, so nothing keeps the process object (and its session) alive.
    """
    decoded: dict[str, TM1Code] = {}
    procedures: dict[str, ProcedureInfo] = {}

    for section in SECTIONS:
        raw = getattr(process, _procedure_attr(section), None) or ""
        code = decode_procedure(raw)
        decoded[section] = code
        # reporter.format_issue renders `source_line + issue.line - 1`, so
        # handing it TM1's own line number for code line 1 makes reported
        # positions match tm1.processes.compile() and the process editor.
        line_count = code.code.count("\n") + 1 if code.code else 1
        procedures[section] = ProcedureInfo(
            code=code.code,
            source_line=code.first_line,
            source_end_line=code.first_line + line_count - 1,
        )

    parameters, parameter_lines = extract_named_entries(
        getattr(process, "parameters", None)
    )
    variables, variable_lines = extract_named_entries(
        getattr(process, "variables", None)
    )

    return ProcessIR(
        name=process.name,
        # All four sections always exist on a TM1 process, so keep empty ones
        # rather than dropping them: they cost nothing (empty code yields no
        # issues) and every section is then treated alike.
        prolog=procedures["prolog"],
        metadata=procedures["metadata"],
        data=procedures["data"],
        epilog=procedures["epilog"],
        parameters=parameters,
        parameter_lines=parameter_lines,
        variables=variables,
        variable_lines=variable_lines,
        datasource_type=getattr(process, "datasource_type", None),
        datasource_query=getattr(process, "datasource_query", None),
        provider_data={PROCEDURES_KEY: decoded},
    )


class TM1Provider:
    """Read-only provider over an injected, already-connected TM1py-like service.

    Args:
        tm1: A connected service exposing ``processes`` (a TM1py ``TM1Service``,
            or anything with the same shape). Never constructed here — see
            :mod:`linti.tm1.service`.
        skip_control_processes: Drop TM1's own ``}``/``{``-prefixed processes
            from :meth:`list_processes`.
        max_process_size: Reject processes whose combined procedure text exceeds
            this many bytes, mirroring the file providers' ``max_file_size``.
        label: How the server is named in error messages.
    """

    def __init__(
        self,
        tm1: Any,
        *,
        skip_control_processes: bool = True,
        max_process_size: int = DEFAULT_MAX_FILE_SIZE,
        label: str = "TM1",
    ) -> None:
        self._tm1 = tm1
        self._skip_control_processes = skip_control_processes
        self._max_process_size = max_process_size
        self._label = label

    # -- internals ---------------------------------------------------------

    @property
    def _processes(self) -> Any:
        processes = getattr(self._tm1, "processes", None)
        if processes is None:
            raise TM1ProviderError(
                f"{self._label} connection has no 'processes' service; expected a "
                f"TM1py TM1Service or an object with the same shape"
            )
        return processes

    def _call(self, what: str, fn: Callable[..., Any], *args: Any) -> Any:
        """Run a server call, translating any failure into a TM1ProviderError.

        linti cannot catch TM1py's exception types — it does not import them,
        and half of them (``TM1pyTimeout``, ``TM1pyPermissionException``, …) do
        not even share a base class, while ``requests`` errors leak through on
        top. So catch broadly and *name* the original instead: the class name
        carries the diagnosis, and the ``__cause__`` chain keeps the traceback.
        """
        try:
            return fn(*args)
        except ProviderError:
            raise
        except Exception as exc:
            raise TM1ProviderError(f"{what}: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def is_control_process(name: str) -> bool:
        """Whether *name* is one of TM1's own internal processes."""
        return name.startswith(_CONTROL_PREFIXES)

    # -- ProcessProvider ---------------------------------------------------

    def list_processes(self) -> list[str]:
        """Return the names of the processes available on the server."""
        names = self._call(
            f"Cannot list processes on {self._label}",
            self._processes.get_all_names,
        )
        if self._skip_control_processes:
            names = [name for name in names if not self.is_control_process(name)]
        return sorted(names)

    def get_process(self, name: str) -> ProcessIR:
        """Fetch *name* from the server and normalise it to a ``ProcessIR``."""
        process = self._call(
            f"Cannot load process {name!r} from {self._label}",
            self._processes.get,
            name,
        )
        if process is None:
            raise TM1ProviderError(
                f"Cannot load process {name!r} from {self._label}: not found"
            )

        actual: Optional[str] = getattr(process, "name", None)
        if actual != name:
            raise TM1ProviderError(
                f"Cannot load process {name!r} from {self._label}: the server "
                f"returned {actual!r}"
            )

        # Measured in encoded bytes, so max_process_size means the same thing
        # here as the file providers' max_file_size does.
        size = sum(
            len(
                (getattr(process, _procedure_attr(section), None) or "").encode("utf-8")
            )
            for section in SECTIONS
        )
        ensure_text_within_size_limit(
            size, self._max_process_size, f"{self._label}:{name}"
        )

        return process_ir_from_tm1(process)

    def save_process(self, process: ProcessIR) -> NoReturn:
        """Always raises: linti does not write to a TM1 server yet.

        The seam for a future write-back path. The IR already carries what it
        needs — ``provider_data[PROCEDURES_KEY]`` holds each section's original
        prefix and line endings, so an unfixed section can be re-serialised to
        the exact bytes the server sent. What is still missing is the encode
        step, verifying that TM1py's procedure setters stored what they were
        given (they re-add the generated block on assignment), and a
        server-side ``compile_process`` check before the write.
        """
        raise TM1ProviderError(
            f"Cannot save process {process.name!r} to {self._label}: linti does "
            f"not write processes back to a TM1 server yet, so auto-fix is not "
            f"supported for TM1 connections"
        )
