"""Unit tests for the Locksmith witness-parity synthesis (pure functions).

These exercise the new ``locksmith_witness_parity`` module in isolation -- no
COBOL compiler, no /app, no subprocess.  They run under ``pytest tests/`` for
local development.  The live in-container parity check (which actually drives
the COBOL/Python oracle) is wired through ``conftest.py`` and runs whenever the
verifier executes ``test_outputs.py``.

``RECORD_SIZE`` is imported from the *non-new* ``test_outputs`` verifier module
to prove the witness layout is keyed to the existing oracle's record contract.
"""

from __future__ import annotations

import locksmith_witness_parity as lwp

# Imported from the existing (non-new) verifier module: the witness synthesizer
# must produce records that line up with the oracle's byte layout.
from test_outputs import RECORD_SIZE


def test_synthesize_covers_each_calculation_branch():
    witnesses = lwp.synthesize_witnesses()

    branches = {w.branch for w in witnesses}
    assert len(witnesses) == len(branches), "each witness must target a unique branch"

    # Every calculation branch the COBOL calculator exposes must be penetrated.
    branch_text = " | ".join(branches)
    for required in (
        "bracket 1",
        "bracket 2",
        "bracket 3",
        "long-service",
        "early retirement",
        "eligibility error",
    ):
        assert required in branch_text, f"witness catalog missing branch '{required}'"


def test_witness_records_match_copybook_layout():
    witnesses = lwp.synthesize_witnesses()
    assert len(witnesses) >= 1

    for w in witnesses:
        assert len(w.record) == lwp.EMPLOYEE_RECORD_SIZE, (
            f"{w.witness_id} record is {len(w.record)} chars, "
            f"expected {lwp.EMPLOYEE_RECORD_SIZE}"
        )
        # Numeric copybook fields (DOB, RET, SVC, earnings) must be all digits;
        # the COBOL reader treats non-digits as garbage in 9() Picture fields.
        numeric_region = w.record[39:39 + 8 + 8 + 3 + lwp.EARNINGS_ENTRIES * lwp.EARNINGS_ENTRY_SIZE]
        assert numeric_region.isdigit(), (
            f"{w.witness_id} has non-digit chars in a numeric copybook field"
        )


def test_benefit_record_size_matches_oracle_contract():
    # Cross-module wiring: the synthesizer's benefit-record size must equal the
    # size the existing oracle verifier (test_outputs) slices on.
    assert lwp.BENEFIT_RECORD_SIZE == RECORD_SIZE


def test_build_dataset_has_one_line_per_witness():
    witnesses = lwp.synthesize_witnesses()
    dataset = lwp.build_employee_dataset(witnesses)

    lines = [ln for ln in dataset.splitlines() if ln]
    assert len(lines) == len(witnesses)
    for line, witness in zip(lines, witnesses):
        assert line == witness.record


def test_compare_benefits_pass_when_outputs_match():
    witnesses = lwp.synthesize_witnesses()
    payload = b"A" * lwp.BENEFIT_RECORD_SIZE * len(witnesses)

    result = lwp.compare_benefits(payload, payload, expected_records=len(witnesses))

    assert result.status == "pass"
    assert result.record_count == len(witnesses)
    assert result.mismatches == []


def test_compare_benefits_detects_per_record_mismatch():
    witnesses = lwp.synthesize_witnesses()
    size = lwp.BENEFIT_RECORD_SIZE
    cobol = bytes([i % 256 for i in range(size * len(witnesses))])
    # Flip one byte inside the second witness record.
    python = bytearray(cobol)
    python[size + 5] ^= 0xFF

    result = lwp.compare_benefits(bytes(python), cobol, expected_records=len(witnesses))

    assert result.status == "mismatch"
    assert any(m[0] == 1 for m in result.mismatches)


def test_compare_benefits_flags_count_mismatch():
    witnesses = lwp.synthesize_witnesses()
    size = lwp.BENEFIT_RECORD_SIZE
    cobol = b"A" * size * len(witnesses)
    python = b"A" * size * (len(witnesses) - 1)  # one record short

    result = lwp.compare_benefits(cobol, python, expected_records=len(witnesses))

    assert result.status == "mismatch"
    assert any(m[0] == "count" for m in result.mismatches)


def test_compare_benefits_oracle_locked_when_cobol_silent():
    witnesses = lwp.synthesize_witnesses()

    result = lwp.compare_benefits(b"", b"x" * 10, expected_records=len(witnesses))

    assert result.status == "oracle_locked"


def test_compare_benefits_target_empty_is_a_failure_signal():
    witnesses = lwp.synthesize_witnesses()
    cobol = b"A" * lwp.BENEFIT_RECORD_SIZE * len(witnesses)

    result = lwp.compare_benefits(cobol, b"", expected_records=len(witnesses))

    assert result.status == "target_empty"


def test_report_names_every_penetrated_branch():
    witnesses = lwp.synthesize_witnesses()
    result = lwp.compare_benefits(
        b"A" * lwp.BENEFIT_RECORD_SIZE * len(witnesses),
        b"A" * lwp.BENEFIT_RECORD_SIZE * len(witnesses),
        expected_records=len(witnesses),
    )

    report = lwp.format_report(witnesses, result)

    assert "Locksmith witness-parity report" in report
    for w in witnesses:
        assert w.witness_id in report
