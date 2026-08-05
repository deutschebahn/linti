"""Test doubles for a connected TM1py service.

These stand in for TM1py so the suite runs without the package and without a
server. They are deliberately hand-written rather than mocked: the duck-type
contract in :mod:`linti.provider.tm1` is exactly what these classes spell out,
so they double as its executable specification.

:class:`FakeProcess` reproduces TM1py's procedure setters verbatim — they are
transforms, not stores, re-adding the generated-statements block when it is
absent. A fake that merely assigned the value would let a write-back bug pass.
"""

import copy
import re
from typing import Any, Optional

# Copied from TM1py/Objects/Process.py so the fake behaves like the real thing.
BEGIN_GENERATED_STATEMENTS = "#****Begin: Generated Statements***"
END_GENERATED_STATEMENTS = "#****End: Generated Statements****"
AUTO_GENERATED_STATEMENTS = (
    f"{BEGIN_GENERATED_STATEMENTS}\r\n{END_GENERATED_STATEMENTS}\r\n"
)
_GENERATED_PATTERN = r"(?s)#\*\*\*\*Begin: Generated Statements(.*)#\*\*\*\*End: Generated Statements\*\*\*\*"

SECTIONS = ("prolog", "metadata", "data", "epilog")


class TM1pyRestException(Exception):
    """Stand-in for TM1py's REST exception, to check error message wording.

    linti must surface the originating exception's class name without importing
    TM1py, so the name here is what matters.
    """


def add_generated_string_to_code(code: str) -> str:
    """Mirror of ``TM1py.Objects.Process.add_generated_string_to_code``."""
    if re.search(pattern=_GENERATED_PATTERN, string=code):
        return code
    return AUTO_GENERATED_STATEMENTS + code


class FakeProcess:
    """A TM1py-like ``Process``: procedure setters transform, lists are read-only."""

    def __init__(
        self,
        name: str,
        prolog_procedure: str = "",
        metadata_procedure: str = "",
        data_procedure: str = "",
        epilog_procedure: str = "",
        parameters: Optional[list] = None,
        variables: Optional[list] = None,
        datasource_type: str = "None",
        datasource_query: str = "",
    ) -> None:
        self.name = name
        self._procedures = {
            "prolog": add_generated_string_to_code(prolog_procedure),
            "metadata": add_generated_string_to_code(metadata_procedure),
            "data": add_generated_string_to_code(data_procedure),
            "epilog": add_generated_string_to_code(epilog_procedure),
        }
        self._parameters = list(parameters or [])
        self._variables = list(variables or [])
        self.datasource_type = datasource_type
        self.datasource_query = datasource_query

    @property
    def parameters(self) -> list:
        return self._parameters

    @property
    def variables(self) -> list:
        return self._variables

    @property
    def prolog_procedure(self) -> str:
        return self._procedures["prolog"]

    @prolog_procedure.setter
    def prolog_procedure(self, value: str) -> None:
        self._procedures["prolog"] = add_generated_string_to_code(value)

    @property
    def metadata_procedure(self) -> str:
        return self._procedures["metadata"]

    @metadata_procedure.setter
    def metadata_procedure(self, value: str) -> None:
        self._procedures["metadata"] = add_generated_string_to_code(value)

    @property
    def data_procedure(self) -> str:
        return self._procedures["data"]

    @data_procedure.setter
    def data_procedure(self, value: str) -> None:
        self._procedures["data"] = add_generated_string_to_code(value)

    @property
    def epilog_procedure(self) -> str:
        return self._procedures["epilog"]

    @epilog_procedure.setter
    def epilog_procedure(self, value: str) -> None:
        self._procedures["epilog"] = add_generated_string_to_code(value)


class FakeProcessService:
    """A TM1py-like ``ProcessService`` recording every write."""

    def __init__(
        self,
        processes: list,
        compile_errors: Optional[dict] = None,
        raise_on_get: Optional[dict] = None,
        raise_on_list: Optional[Exception] = None,
        raise_on_update: Optional[Exception] = None,
        supports_compile: bool = True,
    ) -> None:
        self._processes = {process.name: process for process in processes}
        self._compile_errors = compile_errors or {}
        self._raise_on_get = raise_on_get or {}
        self._raise_on_list = raise_on_list
        self._raise_on_update = raise_on_update
        self.updated: list = []
        self.compiled: list = []
        if supports_compile:
            # Bound only when supported, so the attribute is genuinely absent on
            # a service predating the unbound compile endpoint — which is what
            # the provider probes for.
            self.compile_process = self._compile_process

    def _copy(self, process: FakeProcess) -> FakeProcess:
        # The real service deserialises a fresh object per call. Handing out the
        # stored instance would let a test pass on an in-place mutation and hide
        # a missing update().
        return copy.deepcopy(process)

    def get_all_names(self) -> list:
        if self._raise_on_list is not None:
            raise self._raise_on_list
        return list(self._processes)

    def get_all(self) -> list:
        if self._raise_on_list is not None:
            raise self._raise_on_list
        return [self._copy(process) for process in self._processes.values()]

    def get(self, name: str) -> FakeProcess:
        if name in self._raise_on_get:
            raise self._raise_on_get[name]
        if name not in self._processes:
            raise TM1pyRestException(f"Process '{name}' not found")
        return self._copy(self._processes[name])

    def update(self, process: FakeProcess) -> None:
        if self._raise_on_update is not None:
            raise self._raise_on_update
        self.updated.append(process)
        self._processes[process.name] = self._copy(process)

    def _compile_process(self, process: FakeProcess) -> list:
        self.compiled.append(process)
        return self._compile_errors.get(process.name, [])


class FakeTM1:
    """A TM1py-like ``TM1Service``: just a ``processes`` attribute."""

    def __init__(self, *processes: Any, **service_kwargs: Any) -> None:
        self.processes = FakeProcessService(list(processes), **service_kwargs)
