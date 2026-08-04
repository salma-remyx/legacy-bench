"""Auto-discovered pytest wiring for the oracle-validated G-V checks.

``test.sh`` invokes ``pytest /tests/test_outputs.py``. pytest always loads a
``conftest.py`` sitting next to the collected test file, so this file is
picked up with no edit to ``test.sh`` or ``test_outputs.py``. We use the
``pytest_collection_modifyitems`` hook to append the Generator-Validation
checks (synthesized, then oracle-validated -- see ``oracle_consistency_checks``)
as runnable test items, so they contribute to the verifier's pass/fail.

The injected items run after the existing ``test_outputs.py`` items, i.e.
after ``test_cobol_compiles_and_executes`` has produced the output files.
"""

import pytest

import oracle_consistency_checks as _checks


def pytest_collection_modifyitems(session, config, items):
    """Inject oracle-validated G-V checks into the collected test run."""
    if not items:
        return
    parent = items[0].parent
    for name, run in _checks.checks():
        items.append(pytest.Function.from_parent(parent, name=name,
                                                 callobj=run))
