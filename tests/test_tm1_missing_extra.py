"""linti must stay usable, and honest, without the ``tm1`` extra installed.

The extra is optional, so the failure mode when it is absent is part of the
contract: it has to name the install command rather than surface an ImportError
traceback, and nothing on the file-linting path may depend on it at all.
"""

import builtins

import pytest

from linti.tm1.credentials import CredentialsError, require_keyring
from linti.tm1.service import TM1ConnectionError, require_tm1py


@pytest.fixture
def without(monkeypatch):
    """Make named top-level imports fail, as if the package were not installed."""

    def hide(*names):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in names or name.split(".")[0] in names:
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

    return hide


def test_connecting_without_tm1py_names_the_extra(without):
    without("TM1py")
    with pytest.raises(TM1ConnectionError) as exc_info:
        require_tm1py()
    assert 'pip install "linti[tm1]"' in str(exc_info.value)


def test_storing_credentials_without_keyring_names_the_extra(without):
    without("keyring")
    with pytest.raises(CredentialsError) as exc_info:
        require_keyring()
    assert 'pip install "linti[tm1]"' in str(exc_info.value)


# Run in a fresh interpreter rather than by reloading modules in-process:
# reloading rebinds the module's classes, so every other test still holding the
# old TM1ProviderError would stop recognising the one actually raised.
_BLOCKED_IMPORT_SCRIPT = """
import sys

class Blocker:
    def find_module(self, name, path=None):
        return self if name.split(".")[0] in ("TM1py", "keyring") else None

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("TM1py", "keyring"):
            raise ImportError(f"blocked: {name}")
        return None

sys.meta_path.insert(0, Blocker())

import linti
assert linti.TM1Provider is not None
assert "TM1py" not in sys.modules, "importing linti pulled in TM1py"
assert "keyring" not in sys.modules, "importing linti pulled in keyring"

# The whole read path has to work without the extra.
from linti.provider.tm1 import TM1Provider, process_ir_from_tm1
assert TM1Provider is not None and process_ir_from_tm1 is not None
print("OK")
"""


def test_linti_imports_and_lints_without_the_extra_installed():
    """The extra is optional, so a fresh interpreter without it must work.

    Also pins that the provider is duck-typed: if it ever grew a top-level
    ``import TM1py``, this fails.
    """
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONPATH="src")
    result = subprocess.run(
        [sys.executable, "-c", _BLOCKED_IMPORT_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
