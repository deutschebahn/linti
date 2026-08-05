"""Tests for the top-level ``linti`` package API.

Other tools embed linti through this surface, so it has to import cleanly and
stay free of a TM1py dependency.
"""

import subprocess
import sys

import linti


def test_every_declared_export_exists():
    missing = [name for name in linti.__all__ if not hasattr(linti, name)]
    assert missing == []


def test_star_import_works():
    namespace: dict = {}
    exec("from linti import *", namespace)
    assert "TM1Provider" in namespace
    assert "lint_process_model" in namespace


def test_importing_linti_does_not_pull_in_tm1py():
    # The TM1 provider is duck-typed on purpose: linti must not depend on TM1py,
    # so the integration works in either direction.
    result = subprocess.run(
        [sys.executable, "-c", "import linti, sys; print('TM1py' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_tm1_entry_points_are_reachable():
    assert callable(linti.process_ir_from_tm1)
    assert callable(linti.apply_to_tm1_process)
    assert issubclass(linti.TM1ProviderError, linti.ProviderError)
    assert issubclass(linti.ProviderError, ValueError)
