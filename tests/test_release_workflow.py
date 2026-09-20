"""The release tag must be data for the shell, never executable script text."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/python-publish.yml"
STEP_ID = "verify_release_tag"


@pytest.fixture
def step():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["release-build"]["steps"]
    found = next((s for s in steps if s.get("id") == STEP_ID), None)
    assert found is not None, f"no step with id '{STEP_ID}' in release-build"
    return found


@pytest.fixture
def run_tag(step, tmp_path):
    """Run the step's script in a fake checkout pinned to version 0.7.0."""
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.7.0"\n')

    def run(tag):
        return subprocess.run(
            [shutil.which("bash") or "bash", "-e", "-c", step["run"]],
            cwd=tmp_path,
            env={**os.environ, "RELEASE_TAG": tag},
            text=True,
            capture_output=True,
            timeout=10,
        )

    return run


def test_tag_reaches_the_script_as_env_var(step):
    assert step["env"]["RELEASE_TAG"] == "${{ github.event.release.tag_name }}"
    assert "${{" not in step["run"]


def test_malicious_tag_is_not_executed(run_tag, tmp_path):
    assert run_tag("v0.7.0$(touch${IFS}pwned)").returncode == 1
    assert not (tmp_path / "pwned").exists()


@pytest.mark.parametrize("tag, accepted", [("v0.7.0", True), ("v0.7.1", False)])
def test_tag_must_match_pyproject_version(run_tag, tag, accepted):
    pytest.importorskip("tomllib")  # the step reads the version with tomllib
    assert (run_tag(tag).returncode == 0) is accepted
