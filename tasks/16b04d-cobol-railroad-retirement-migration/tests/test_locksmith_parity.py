"""
Tests for the Locksmith parity witness-search loop.

These prove the integration with the EXISTING call-site module ``test_outputs``
(it imports ``RECORD_SIZE`` and reuses the same EMPLOYEE.DAT record layout that
``test_outputs`` compares under), plus the loop's own logic. The loop's runtimes
are injected as fakes so the tests run anywhere -- no /app or GnuCOBOL needed.
"""

import locksmith_parity
from locksmith_parity import (
    build_employee_record, generate_witnesses, parity_check,
    run_locksmith_loop, analyze_locked_paragraphs, Witness,
)

# Imported from the NON-NEW call-site module -- this is the integration surface.
from test_outputs import RECORD_SIZE


class _FakeRuntimes:
    """In-memory stand-in for the COBOL reference + Python target runtimes."""

    def __init__(self, record_size, diverge_indices=()):
        self.record_size = record_size
        self.diverge_indices = set(diverge_indices)
        self.current = -1
        self.written = []

    def write_record(self, record_line):
        self.current += 1
        self.written.append(record_line)

    def run_cobol(self):
        # Reference: two distinct records.
        return bytes([1]) * self.record_size + bytes([2]) * self.record_size

    def run_python(self):
        out = bytearray(self.run_cobol())
        if self.current in self.diverge_indices:
            out[self.record_size] ^= 0xFF  # corrupt the second record
        return bytes(out)


def _manual_witnesses():
    return [
        Witness("a", "a", {"region": "west", "tier": "1"}, "x" * 643),
        Witness("b", "b", {"region": "west", "tier": "2"}, "x" * 643),
        Witness("c", "c", {"region": "east", "tier": "1"}, "x" * 643),
        Witness("d", "d", {"region": "east", "tier": "2"}, "x" * 643),
    ]


def test_witnesses_match_employee_layout():
    """Generated witnesses must fit the EMPLOYEE.DAT layout the verifier reads."""
    witnesses = generate_witnesses()
    assert len(witnesses) >= 10
    for w in witnesses:
        assert len(w.record) == 643, f"{w.witness_id} record not 643 bytes"
        assert w.record[0:9].isdigit(), "ssn must be 9 digits"
        assert w.record[39:47].isdigit(), "dob must be 8 digits at [39:47]"
        assert w.record[47:55].isdigit(), "ret_date must be 8 digits at [47:55]"
        assert w.record[55:58].isdigit(), "svc must be 3 digits at [55:58]"


def test_build_employee_record_round_trips_layout():
    rec = build_employee_record(
        "123456789", "LOCKSMITH T X", "19650801", "20240115", "220",
        {1990: 50000 * 100, 1995: 60000 * 100},
    )
    assert len(rec) == 643
    assert rec[0:9] == "123456789"
    assert rec[39:47] == "19650801"
    assert rec[47:55] == "20240115"
    assert rec[55:58] == "220"


def test_parity_check_uses_call_site_record_size():
    """parity_check must align on test_outputs.RECORD_SIZE (the integration)."""
    base = bytes([1]) * RECORD_SIZE + bytes([2]) * RECORD_SIZE
    assert parity_check(base, base, RECORD_SIZE).passed

    flipped = bytearray(base)
    flipped[RECORD_SIZE] ^= 0xFF
    result = parity_check(base, bytes(flipped), RECORD_SIZE)
    assert not result.passed
    assert result.divergent_indices == [1]


def test_loop_passes_for_matching_runtimes(tmp_path):
    rt = _FakeRuntimes(RECORD_SIZE, diverge_indices=())
    report = run_locksmith_loop(
        rt.write_record, rt.run_cobol, rt.run_python, RECORD_SIZE,
        witnesses=_manual_witnesses(), report_path=tmp_path / "report.json",
    )
    assert report.witnesses_covered == 4
    assert report.parity_passed == 4
    assert report.divergences == []
    assert report.locked_paragraphs == []
    assert report.pass_rate == 1.0
    assert (tmp_path / "report.json").exists()  # advisory report was written


def test_loop_localizes_locked_paragraph():
    """Divergences sharing a tag surface that tag as the Locked Paragraph."""
    witnesses = _manual_witnesses()
    rt = _FakeRuntimes(RECORD_SIZE, diverge_indices={0, 1})  # the two 'west' witnesses
    report = run_locksmith_loop(
        rt.write_record, rt.run_cobol, rt.run_python, RECORD_SIZE,
        witnesses=witnesses,
    )
    assert len(report.divergences) == 2
    conditions = [lp.condition for lp in report.locked_paragraphs]
    assert "region=west" in conditions
    assert "region=east" not in conditions


def test_analyze_returns_empty_when_no_divergence():
    assert analyze_locked_paragraphs([], _manual_witnesses()) == []


def test_run_from_env_skips_without_dual_runtime():
    """Outside the task container (no /app) the env wiring must be a no-op."""
    assert locksmith_parity.run_from_env() is None


def test_conftest_registers_autouse_session_fixture():
    """The call-site hook exposes the locksmith session fixture pytest loads."""
    import conftest

    assert callable(conftest.locksmith_witness_search)
