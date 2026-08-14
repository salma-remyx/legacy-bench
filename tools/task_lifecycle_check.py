#!/usr/bin/env python3
"""Verify a task's verifier discriminates: fails on the task state, passes on the restored state.

Change2Task-style lifecycle validation for Legacy-Bench tasks. A task is only
useful if its verifier fails on the state the agent receives (environment/)
and passes on the reference fix (environment/ + solution/ overlay). This
script checks both legs locally, without Docker: it lays each state out in a
temp dir with the task's own path layout, rewrites the absolute /app/... and
/tests/... paths the verifier uses to point into that layout, and runs pytest.

Usage:
    python3 tools/task_lifecycle_check.py tasks/<task-id>

Adapted from Change2Task: From Repository Changes to Executable Coding Agent
Tasks and Environments (arXiv:2607.28591) -- "validates the lifecycle from a
healthy base to a task state and a restored state".
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_ROOT = 'environment'
SOLUTION_DIRS = ('solution',)  # overlays onto the environment tree by relative path


def _overlay(env_dir: Path, task_dir: Path) -> Path:
    """Copy the environment and overlay solution files onto it."""
    state = Path(tempfile.mkdtemp(prefix='task-state-'))
    shutil.copytree(env_dir, state, dirs_exist_ok=True)
    for sol in SOLUTION_DIRS:
        sol_dir = task_dir / sol
        if not sol_dir.is_dir():
            continue
        for src in sol_dir.rglob('*'):
            if src.is_file():
                rel = src.relative_to(sol_dir)
                dest = state / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    return state


def _reroot(text: str, env_dir: Path) -> str:
    """Rewrite the verifier's absolute container paths into the local layout."""
    text = text.replace('/tests/', 'TESTS/')
    text = re.sub(r'/app(?![\w-])', str(env_dir), text)
    return text


def _run_verifier(task_dir: Path, state_dir: Path, label: str) -> bool:
    """Run the task's pytest verifier against state_dir; True iff it passes."""
    tests_dir = task_dir / 'tests'
    tests = sorted(p for p in tests_dir.glob('*.py') if p.name != 'conftest.py')
    if not tests:
        print(f'  {label}: no test file found under tests/')
        return False
    workdir = Path(tempfile.mkdtemp(prefix='task-run-'))
    passed_all = True
    for test in tests:
        rerooted = workdir / test.name
        rerooted.write_text(_reroot(test.read_text(), state_dir))
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', str(rerooted)],
            capture_output=True, text=True, timeout=300,
        )
        ok = result.returncode == 0
        print(f'  {label}: {test.name}: {"PASS" if ok else "FAIL"}')
        passed_all = passed_all and ok
    shutil.rmtree(workdir, ignore_errors=True)
    return passed_all


def check(task_dir: Path) -> int:
    """Run both lifecycle legs for one task; exit 0 iff they discriminate."""
    env_dir = task_dir / ENV_ROOT
    if not env_dir.is_dir():
        print(f'no environment/ under {task_dir}')
        return 2

    print(f'{task_dir.name}: task-state leg (verifier MUST fail)')
    task_fails = not _run_verifier(task_dir, env_dir, 'task-state')
    print(f'{task_dir.name}: restored-state leg (verifier MUST pass)')
    restored = _overlay(env_dir, task_dir)
    try:
        restored_passes = _run_verifier(task_dir, restored, 'restored-state')
    finally:
        shutil.rmtree(restored, ignore_errors=True)

    print(f'  task-state fails:     {task_fails}')
    print(f'  restored-state passes: {restored_passes}')
    if task_fails and restored_passes:
        print('VERIFIED: verifier discriminates task state from restored state')
        return 0
    print('NOT VERIFIED: verifier does not discriminate')
    return 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(check(Path(sys.argv[1])))
