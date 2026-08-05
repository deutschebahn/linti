"""Provider for TI processes living on a TM1 server.

This module deliberately does **not** import TM1py, and linti does not depend
on it. :class:`ProcessProvider` is a structural protocol, so a provider over a
live server only needs an object that behaves like a connected TM1py service:

- ``tm1.processes`` with ``get_all_names()``, ``get(name)``, ``update(process)``
  and, optionally, ``get_all()`` and ``compile_process(process)``
- process objects with ``name``, ``prolog_procedure``, ``metadata_procedure``,
  ``data_procedure``, ``epilog_procedure``, ``parameters``, ``variables``,
  ``datasource_type`` and ``datasource_query``

The connection is always injected, never constructed here. That is what keeps
both integration directions open: a TM1py-driven script hands in its own
``TM1Service``, and a future linti-driven CLI would be just another caller of
the same constructor — neither one is baked into this module.
"""

import warnings
from typing import Any, Callable, Optional

from linti.model.process_ir import ProcedureInfo, ProcessIR
from linti.provider.base import (
    DEFAULT_MAX_FILE_SIZE,
    ProviderError,
    count_code_lines,
    ensure_text_within_size_limit,
    extract_named_entries,
)
from linti.provider.tm1_code import TM1Code, decode_procedure, encode_procedure

# TM1's four execution blocks, in execution order. Matches the ProcessIR
# attribute names and the order extract_procedures yields.
_SECTIONS = ("prolog", "metadata", "data", "epilog")

# TM1 names its own internal objects with these prefixes. They are not
# user-authored code and linting them is noise.
_CONTROL_PREFIXES = ("}", "{")

# provider_data keys. Namespaced like the other providers' hints
# (``pa_json_properties``, ``ti_has_regions``).
PROCEDURES_KEY = "tm1_procedures"
PROCESS_KEY = "tm1_process"


class TM1ProviderError(ProviderError):
    """Talking to the TM1 server failed, or its answer could not be used."""


def _procedure_attr(section: str) -> str:
    return f"{section}_procedure"


def process_ir_from_tm1(process: Any) -> ProcessIR:
    """Build a :class:`ProcessIR` from a TM1py-like process object.

    *process* is anything exposing the attributes listed in the module
    docstring — a TM1py ``Process``, or a process object a caller assembled
    themselves. This function is the whole read side of the integration
    contract; a caller who already holds a process object needs nothing else::

        issues = lint_process_model(process_ir_from_tm1(process), linter)

    Only the four procedures are interpreted. Parameters and variables are read
    for the context-aware rules but never written back — TM1py exposes them
    without setters, so linti cannot alter them even by accident.
    """
    decoded: dict[str, TM1Code] = {}
    procedures: dict[str, ProcedureInfo] = {}

    for section in _SECTIONS:
        raw = getattr(process, _procedure_attr(section), None) or ""
        code = decode_procedure(raw)
        decoded[section] = code
        # Line 1 of `code` is TM1 line prefix_lines + 1, so reported line
        # numbers line up with tm1.processes.compile() errors and with what the
        # process editor shows. reporter.format_issue adds source_line - 1.
        source_line = code.prefix_lines + 1
        procedures[section] = ProcedureInfo(
            code=code.code,
            source_line=source_line,
            source_end_line=source_line + max(count_code_lines(code.code), 1) - 1,
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
        # issues) and save_process can then treat every section alike.
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
        provider_data={PROCEDURES_KEY: decoded, PROCESS_KEY: process},
    )


def apply_to_tm1_process(ir: ProcessIR, process: Any) -> bool:
    """Write *ir*'s procedure code back onto a TM1py-like *process* object.

    Re-attaches each section's original prefix and line endings, so a section
    that picked up no fixes is written back as the exact bytes the server sent.
    Nothing but the four procedures is touched.

    Returns ``True`` if any procedure actually changed, letting callers skip a
    pointless round trip to the server.

    Raises:
        TM1ProviderError: if a written procedure does not read back as the code
            it was given. TM1py's procedure setters are transforms, not stores —
            they re-add the generated-statements block when it is missing — so
            what was assigned is verified rather than trusted. The check is on
            the decoded code, not the raw text: a wrapper the process object
            adds for itself is fine, altered code is not.
    """
    decoded: dict[str, TM1Code] = ir.provider_data.get(PROCEDURES_KEY, {})
    changed = False

    for section in _SECTIONS:
        info = getattr(ir, section, None)
        if info is None:
            continue

        code = decoded.get(section)
        if code is None:
            # ProcessIR built without going through process_ir_from_tm1 (a
            # brand-new process, say). No prefix to restore — let TM1py add its
            # own generated-statements block.
            prefix, newline = "", "\r\n"
        else:
            prefix, newline = code.prefix, code.newline

        attr = _procedure_attr(section)
        expected = encode_procedure(info.code, prefix, newline)
        if getattr(process, attr, None) == expected:
            continue

        setattr(process, attr, expected)
        stored = getattr(process, attr, None) or ""
        if decode_procedure(stored).code != info.code:
            raise TM1ProviderError(
                f"Writing the {section} procedure of {ir.name!r} did not store the "
                f"intended code: the process object rewrote it on assignment. "
                f"Refusing to save a process whose content linti cannot predict."
            )
        changed = True

    return changed


class TM1Provider:
    """Provider over an injected, already-connected TM1py-like service.

    Args:
        tm1: A connected service exposing ``processes`` (a TM1py ``TM1Service``,
            or anything with the same shape). Never constructed here — see the
            module docstring.
        skip_control_processes: Drop TM1's own ``}``/``{``-prefixed processes
            from :meth:`list_processes`.
        prefetch: Fetch every process in one ``get_all()`` call instead of one
            ``get()`` per name. Turns 1 + N round trips into 1 for a whole-server
            run; costs memory proportional to the model.
        verify_before_save: Ask the server to compile a process before writing
            it, and refuse the write if it reports syntax errors. Uses the
            unbound compile endpoint, which persists nothing.
        max_process_size: Reject processes whose combined procedure text exceeds
            this many characters, mirroring the file providers' size ceiling.
        label: How the server is named in error messages.
    """

    def __init__(
        self,
        tm1: Any,
        *,
        skip_control_processes: bool = True,
        prefetch: bool = False,
        verify_before_save: bool = True,
        max_process_size: int = DEFAULT_MAX_FILE_SIZE,
        label: str = "TM1",
    ) -> None:
        self._tm1 = tm1
        self._skip_control_processes = skip_control_processes
        self._prefetch = prefetch
        self._verify_before_save = verify_before_save
        self._max_process_size = max_process_size
        self._label = label
        self._cache: Optional[dict[str, Any]] = None

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

    @staticmethod
    def _call(what: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run a server call, translating any failure into a TM1ProviderError.

        linti cannot catch TM1py's exception types — it does not import them,
        and half of them (``TM1pyTimeout``, ``TM1pyPermissionException``, …) do
        not even share a base class, while ``requests`` errors leak through on
        top. So catch broadly and *name* the original instead: the class name
        carries the diagnosis, and the ``__cause__`` chain keeps the traceback.
        """
        try:
            return fn(*args, **kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            raise TM1ProviderError(f"{what}: {type(exc).__name__}: {exc}") from exc

    def _is_control_process(self, name: str) -> bool:
        return name.startswith(_CONTROL_PREFIXES)

    def _fetch(self, name: str) -> Any:
        """Return the server's process object for *name*."""
        if self._prefetch:
            if self._cache is None:
                self.list_processes()
            # A miss is normal after save_process invalidates an entry; fall
            # through and re-read that one process from the server.
            cached = (self._cache or {}).get(name)
            if cached is not None:
                return cached

        process = self._call(
            f"Cannot load process {name!r} from {self._label}",
            self._processes.get,
            name,
        )
        if process is None:
            raise TM1ProviderError(
                f"Cannot load process {name!r} from {self._label}: not found"
            )
        return process

    # -- ProcessProvider ---------------------------------------------------

    def list_processes(self) -> list[str]:
        """Return the names of the processes available on the server."""
        if self._prefetch:
            # get_all() is called without kwargs and control processes are
            # filtered here, so the duck-type contract stays a plain no-argument
            # call that every TM1py version and every test double satisfies.
            processes = self._call(
                f"Cannot list processes on {self._label}",
                self._processes.get_all,
            )
            self._cache = {process.name: process for process in processes}
            names = list(self._cache)
        else:
            names = self._call(
                f"Cannot list processes on {self._label}",
                self._processes.get_all_names,
            )

        if self._skip_control_processes:
            names = [name for name in names if not self._is_control_process(name)]
        return sorted(names)

    def get_process(self, name: str) -> ProcessIR:
        """Fetch *name* from the server and normalise it to a ``ProcessIR``."""
        process = self._fetch(name)

        actual = getattr(process, "name", None)
        if actual != name:
            raise TM1ProviderError(
                f"Cannot load process {name!r} from {self._label}: the server "
                f"returned {actual!r}"
            )

        size = sum(
            len(getattr(process, _procedure_attr(section), None) or "")
            for section in _SECTIONS
        )
        ensure_text_within_size_limit(size, self._max_process_size, name)

        return process_ir_from_tm1(process)

    def save_process(self, process: ProcessIR) -> None:
        """Write *process*'s procedure code back to the server.

        A process whose procedures are unchanged is not written at all, so a
        clean auto-fix run causes no server-side modification.
        """
        target = process.provider_data.get(PROCESS_KEY)
        if target is None:
            raise TM1ProviderError(
                f"Cannot save process {process.name!r} to {self._label}: it was not "
                f"loaded through this provider, so there is no server object to "
                f"update"
            )

        if not apply_to_tm1_process(process, target):
            return

        if self._verify_before_save:
            self._verify(process.name, target)

        self._call(
            f"Cannot save process {process.name!r} to {self._label}",
            self._processes.update,
            target,
        )
        if self._cache is not None:
            self._cache.pop(process.name, None)

    def _verify(self, name: str, target: Any) -> None:
        """Refuse the write if the server rejects the fixed code.

        Uses the unbound compile endpoint: it validates a process body without
        creating or modifying anything on the server, so a rejected process is
        left exactly as it was.
        """
        compile_process = getattr(self._processes, "compile_process", None)
        if compile_process is None:
            warnings.warn(
                f"{self._label} does not support pre-save compilation; saving "
                f"{name!r} without server-side verification",
                RuntimeWarning,
                stacklevel=2,
            )
            return

        errors = self._call(
            f"Cannot verify process {name!r} on {self._label}",
            compile_process,
            target,
        )
        if errors:
            raise TM1ProviderError(
                f"Cannot save process {name!r} to {self._label}: the server "
                f"rejected the fixed code: {errors!r}"
            )
