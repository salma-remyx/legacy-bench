"""Pytest wiring that emits a continuous, criteria-decomposed ``score.json``
alongside the binary ``reward.txt`` written by ``test.sh``.

pytest discovers ``conftest.py`` next to the collected test file, so this layer
is auto-loaded whenever ``test.sh`` runs ``pytest /tests/test_outputs.py`` --
no existing file is modified. The deterministic oracle is untouched: pass/fail
and the pytest exit code are unchanged, so ``reward.txt`` keeps its exact
meaning. This layer only *adds* a diagnostic ``/logs/verifier/score.json``.

See ``verifier_score.py`` (adapted from "LLM-as-a-Verifier", arXiv:2607.05391)
for the scoring logic.
"""

from __future__ import annotations

import os
import traceback

try:  # never let a scoring import break the deterministic oracle
    import verifier_score
except Exception:  # pragma: no cover - defensive
    verifier_score = None

# Default is the in-container verifier contract path (alongside reward.txt);
# overridable via env so the wiring is observable outside the container.
_SCORE_PATH = os.environ.get("LEGACY_BENCH_SCORE_PATH", "/logs/verifier/score.json")
_ERR_PATH = os.environ.get("LEGACY_BENCH_SCORE_ERR", "/logs/verifier/score.err")

# criterion name -> (passed, message); passed None == not yet evaluated
_OUTCOMES = {}


def _criterion_name(nodeid):
    if "::" in nodeid:
        tail = nodeid.split("::", 1)[1]
        return tail.split("[", 1)[0]
    return nodeid


def _stringify(longrepr):
    if longrepr is None:
        return None
    try:
        return str(longrepr)
    except Exception:  # pragma: no cover - defensive
        return None


def pytest_runtest_logreport(report):
    """Record per-criterion outcomes across setup/call/teardown phases."""
    if verifier_score is None:
        return
    name = _criterion_name(report.nodeid)
    if report.when not in ("setup", "call", "teardown"):
        return
    if report.failed:
        passed, message = _OUTCOMES.get(name, (None, None))
        if message is None:
            message = _stringify(report.longrepr)
        _OUTCOMES[name] = (False, message)
    elif report.when == "call" and report.passed:
        _OUTCOMES[name] = (True, None)


def emit_score(test_path, outcomes, score_path):
    """Score an oracle file against observed outcomes; write ``score_path``.

    Public entry point so the wiring can be exercised directly by tests.
    """
    if verifier_score is None:
        return None
    return verifier_score.score_file(test_path, outcomes, score_path)


def _test_path_from_session(session):
    try:
        items = getattr(session, "items", None)
        if items:
            return str(items[0].path)
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def pytest_sessionfinish(session, exitstatus):
    """Best-effort: emit score.json without affecting the exit status."""
    if verifier_score is None:
        return
    try:
        test_path = _test_path_from_session(session)
        if not test_path:
            return
        emit_score(test_path, dict(_OUTCOMES), _SCORE_PATH)
    except Exception:  # pragma: no cover - never break the oracle
        try:
            with open(_ERR_PATH, "w", encoding="utf-8") as handle:
                handle.write("verifier_score failed:\n" + traceback.format_exc())
        except Exception:
            pass
