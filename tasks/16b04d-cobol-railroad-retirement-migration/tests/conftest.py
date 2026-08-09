"""
Pytest auto-discovered hook for the Locksmith witness-search parity loop.

The task verifier (``test.sh``) runs ``pytest /tests/test_outputs.py``. pytest
always loads ``conftest.py`` from the directory of the collected tests, so this
file is picked up with no change to the existing test files -- it is the
integration point (the "call site") for ``locksmith_parity``.

A session-scoped autouse fixture runs the Locksmith Loop once, after the COBOL
reference is buildable and (if present) the agent's Python migration exists.
Outside the task container (no /app), or before a solution exists, it is a
silent no-op so it can never break collection or the rest of the suite.
"""

import pytest

import locksmith_parity


@pytest.fixture(scope="session", autouse=True)
def locksmith_witness_search():
    """Run the Locksmith witness search; gate the verdict on any divergence."""
    report = locksmith_parity.run_from_env()
    if report is None:
        # Dual runtime not available (e.g. local checkout, or no solution yet).
        return

    if report.witnesses_covered == 0:
        # Nothing penetrated -- nothing to assert. Don't gate on an empty search.
        return

    if report.divergences:
        locked = "; ".join(lp.condition for lp in report.locked_paragraphs) or "(unlocalized)"
        pytest.fail(
            f"Locksmith parity search found {len(report.divergences)} divergent "
            f"witness(es) of {report.witnesses_covered} covered "
            f"(pass rate {report.pass_rate:.2%}). Locked paragraph(s): {locked}. "
            f"Full report: /app/locksmith_report.json"
        )
