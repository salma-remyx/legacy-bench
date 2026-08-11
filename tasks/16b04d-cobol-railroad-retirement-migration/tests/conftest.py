"""Verifier wiring for the Locksmith witness-parity check.

This conftest is auto-loaded by pytest when the verifier runs
``pytest /tests/test_outputs.py`` (see ``test.sh``).  The session-scoped
autouse fixture below runs the branch-targeted witness synthesis from
``locksmith_witness_parity`` through this task's *existing* deterministic
parity oracle -- the COBOL reference compiled and executed by the helpers in
the non-new ``test_outputs`` module -- and asserts the agent's Python target
reproduces the oracle byte-for-byte on every witness.

No existing file is modified: the wiring is delivered purely through pytest's
conftest auto-discovery, which is this benchmark's native extension point for
per-task verifiers.

The fixture is environment-guarded so it only does live oracle work inside the
verifier container (where ``cobc`` and ``/app/src`` exist).  Elsewhere -- e.g.
running the pure-function unit tests in ``test_locksmith_witness.py`` locally --
it no-ops, so those tests stay green without a COBOL toolchain.
"""

from __future__ import annotations

import subprocess

import pytest


def _in_verifier_container(test_outputs) -> bool:
    """True only when the COBOL oracle toolchain is actually present."""
    return (
        test_outputs.COBC_COMPILER.exists()
        and test_outputs.COBOL_SRC.exists()
        and test_outputs.COPYBOOKS_DIR.exists()
    )


def _ensure_oracle_compiled(test_outputs, request) -> bool:
    """Compile the COBOL oracle binary, reusing the shared fixture if registered.

    During the real verifier run ``test_outputs.py`` is collected, so its
    ``compile_cobol`` session fixture is available and we defer to it (keeping a
    single compile for the whole session).  If it is not registered -- someone
    invoked only a sibling test file -- we compile here.  Either way the binary
    is ready before any witness is run.
    """
    try:
        request.getfixturevalue("compile_cobol")
    except Exception:
        subprocess.run(
            [
                "cobc", "-x", "-febcdic-table=ebcdic500_latin1",
                "-I", str(test_outputs.COPYBOOKS_DIR),
                "-o", str(test_outputs.COBOL_BIN),
                str(test_outputs.COBOL_SRC),
                str(test_outputs.COBOL_T1),
                str(test_outputs.COBOL_T2),
            ],
            capture_output=True,
            cwd="/app",
        )
    return test_outputs.COBOL_BIN.exists()


@pytest.fixture(scope="session", autouse=True)
def locksmith_witness_parity(request):
    """Run branch-targeted witnesses through the COBOL/Python parity oracle.

    Strengthens the deterministic oracle exactly where the benchmark README
    says it is weakest ("COBOL bugs are silent -- wrong output looks correct"):
    instead of checking parity only on the seeded dataset, we synthesize one
    employee record per calculation branch and require the target to match the
    COBOL reference on each.  A correct migration passes; a migration that is
    silently wrong on any penetrated branch fails the verifier.
    """
    # Imported lazily so collection order never matters: ``test_outputs`` is the
    # non-new call-site module whose oracle helpers we drive, and
    # ``locksmith_witness_parity`` is the new capability.
    import test_outputs
    import locksmith_witness_parity as lwp

    # Outside the verifier container (no cobc / no /app) there is no oracle to
    # drive -- e.g. when the pure-function unit tests run locally.  No-op so the
    # rest of the session is unaffected.
    if not _in_verifier_container(test_outputs):
        yield
        return

    # If the agent never produced a migration target, there is nothing to
    # validate against the oracle; test_outputs.test_python_file_exists already
    # reports that failure.  Do not turn a missing target into an error here --
    # just yield so the rest of the suite runs normally.
    if not test_outputs.PYTHON_SRC.exists():
        yield
        return

    if not _ensure_oracle_compiled(test_outputs, request):
        pytest.fail(
            "Locksmith witness-parity could not compile the COBOL oracle; "
            "unable to run the deterministic parity check.",
            pytrace=False,
        )

    employee_path = test_outputs.DATA_DIR / "EMPLOYEE.DAT"
    original_employee = employee_path.read_bytes()

    try:
        witnesses = lwp.synthesize_witnesses()
        employee_path.write_text(lwp.build_employee_dataset(witnesses))

        # ``run_python`` clears the COBOL outputs first (anti-cheat), so capture
        # the oracle bytes from ``run_cobol``'s return value before it runs.
        cobol_output = test_outputs.run_cobol()
        python_output = test_outputs.run_python()

        result = lwp.compare_benefits(
            cobol_output, python_output, expected_records=len(witnesses)
        )
        report = lwp.format_report(witnesses, result)
        print("\n" + report + "\n")

        # An "oracle_locked" result means the COBOL oracle itself declined to
        # judge the witness set (Locked Paragraph) -- report it, but do not fail
        # the target on the oracle's account.  Anything else that is not a clean
        # pass is a real parity failure.
        if result.status not in ("pass", "oracle_locked"):
            pytest.fail(report, pytrace=False)
    finally:
        # Always restore the seeded dataset so the rest of the verifier suite
        # runs against the original employee records.
        employee_path.write_bytes(original_employee)

    yield
