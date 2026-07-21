"""Pytest hooks for the railcar settlement task.

pytest auto-discovers this ``conftest.py`` (it sits next to
``test_outputs.py``), so no existing file is modified to wire it in. After the
binary tests finish, ``pytest_sessionfinish`` runs the continuous settlement
verifier and writes a separate continuous-score artifact.

The continuous pass is strictly additive: it never raises and never changes the
session exit status, so the binary reward written by ``test.sh`` to
``/logs/verifier/reward.txt`` remains driven solely by ``test_outputs.py``.

Continuous verification adapted from "LLM-as-a-Verifier: A General-Purpose
Verification Framework" (arXiv:2607.05391v1); see
``continuous_settlement_verifier.py`` for the adapted-port rationale.
"""

import os

OUTPUT_DIR = "/app/output"
DATA_DIR = "/app/data"
REPORT_PATH = "/logs/verifier/llm_verifier_scores.json"


def pytest_sessionfinish(session, exitstatus):
    """Run the continuous verifier and emit its report; never affect reward."""
    # Additive only: every step is guarded so a verifier failure can never flip
    # the binary reward. The import is deferred so a collection-time import
    # error cannot break the test session either.
    try:
        from continuous_settlement_verifier import verify_outputs, write_report

        report = verify_outputs(OUTPUT_DIR, DATA_DIR)
        try:
            os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
            write_report(report, REPORT_PATH)
        except OSError:
            # /logs/verifier may be unwritable in some environments; the
            # continuous score is best-effort and must not break grading.
            pass
        # Deliberately do NOT touch session.exitstatus: the binary reward in
        # /logs/verifier/reward.txt must stay driven solely by test_outputs.py.
        overall = report.get("overall_score")
        print("\n[llm-as-a-verifier] continuous overall score:", overall)
    except Exception as exc:  # never propagate -- reward is binary-only
        print("\n[llm-as-a-verifier] continuous pass skipped:", exc)
