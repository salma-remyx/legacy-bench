"""
Tests for the Change2Task-style task lifecycle checker.

Exercises tools/task_lifecycle_check.py against a task directory whose
verifier is known to discriminate (the 4b2e17 card-parser task) and against
degenerate inputs, asserting the exit-code contract other tooling relies on.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / 'tools' / 'task_lifecycle_check.py'


def run_checker(task_dir):
    """Run the lifecycle checker; return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(CHECKER), str(task_dir)],
        capture_output=True, text=True, timeout=300,
    )


def test_discriminating_task_reports_verified():
    """4b2e17's verifier fails on the task state and passes on the restored state."""
    task = REPO_ROOT / 'tasks' / '4b2e17-fortran-card-parser-hardening'
    if not task.is_dir():
        pytest.skip('4b2e17 task not present')
    result = run_checker(task)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'VERIFIED' in result.stdout


def test_task_state_leg_actually_fails():
    """The discriminating verdict must come from a real failure, not a skip."""
    task = REPO_ROOT / 'tasks' / '4b2e17-fortran-card-parser-hardening'
    if not task.is_dir():
        pytest.skip('4b2e17 task not present')
    result = run_checker(task)
    task_state_lines = [
        ln for ln in result.stdout.splitlines() if 'task-state:' in ln
    ]
    assert any('FAIL' in ln for ln in task_state_lines), result.stdout
    assert any('restored-state:' in ln and 'PASS' in ln
               for ln in result.stdout.splitlines()), result.stdout


def test_missing_environment_reports_error():
    """A directory without environment/ exits 2 rather than crashing."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = run_checker(Path(tmp))
    assert result.returncode == 2


def test_usage_without_args_exits_nonzero():
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
