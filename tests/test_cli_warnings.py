"""Tests for clean CLI rendering of linti config warnings."""

import warnings

from linti.cli.main import _install_config_warning_handler
from linti.config import LintiConfigWarning


def test_linti_config_warning_is_rendered_cleanly(capsys):
    with warnings.catch_warnings():  # restores showwarning + filters on exit
        _install_config_warning_handler()
        warnings.warn("bad setting", LintiConfigWarning)

    err = capsys.readouterr().err
    assert "⚠" in err
    assert "bad setting" in err
    # Not the raw Python warning format (file:line: Category: ...).
    assert "LintiConfigWarning" not in err
    assert ".py:" not in err


def test_non_linti_warning_is_delegated_to_default_handler(capsys):
    # Own the recorder so the delegated warning is consumed here and never
    # leaks into pytest's warnings summary.
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _install_config_warning_handler()
        warnings.warn("unrelated", UserWarning)

    # Passed through to the default handler unchanged (not given the ⚠ format).
    assert [str(w.message) for w in recorded] == ["unrelated"]
    assert recorded[0].category is UserWarning
    assert "⚠" not in capsys.readouterr().err
