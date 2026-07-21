"""Integration tests for the continuous settlement verifier.

These exercise the verifier end-to-end and prove it integrates with the
existing call-site module ``test_outputs`` (its COMP-3 decoder and record-size
constants are reused, not re-implemented) and with the auto-discovered
``conftest.py`` hook that wires the verifier into the grading session.
"""

import importlib.util
import json
import os
import types

import pytest

import continuous_settlement_verifier as csv_mod
import test_outputs  # existing (non-new) call-site module


# --- record builders -------------------------------------------------------

def encode_comp3(value, nbytes=5):
    """Inverse of test_outputs.decode_comp3 for building fixture records."""
    scaled = int(round(abs(value) * 100))
    digits = str(scaled).rjust(2 * nbytes - 1, "0")[-(2 * nbytes - 1):]
    out = bytearray()
    for i in range(nbytes - 1):
        out.append((int(digits[2 * i]) << 4) | int(digits[2 * i + 1]))
    sign = 0x0D if value < 0 else 0x0F
    out.append((int(digits[-1]) << 4) | sign)
    return bytes(out)


def settle_record(per_diem, mileage, total, status="V", error_code="   "):
    rec = bytearray(b"\x40" * test_outputs.SETTLE_RECORD_SIZE)  # EBCDIC spaces
    rec[26:31] = encode_comp3(per_diem)
    rec[31:36] = encode_comp3(mileage)
    rec[36:41] = encode_comp3(total)
    rec[48:49] = status.encode("cp500")
    rec[49:52] = error_code.ljust(3).encode("cp500")[:3]
    return bytes(rec)


def reclaim_record(disputed, status):
    rec = bytearray(b"\x40" * test_outputs.RECLAIM_RECORD_SIZE)
    rec[36:41] = encode_comp3(disputed)
    rec[43:44] = status.encode("cp500")
    return bytes(rec)


# --- unit-level scoring ----------------------------------------------------

def test_decode_roundtrips_through_existing_helper():
    # The new module reuses test_outputs.decode_comp3 rather than redefining it.
    assert csv_mod.decode_comp3 is test_outputs.decode_comp3
    assert csv_mod.decode_comp3(encode_comp3(12.34)) == 12.34
    assert csv_mod.decode_comp3(encode_comp3(-7.50)) == -7.50


def test_score_criteria_detects_the_semantic_gap():
    # One consistent record (total == per_diem + mileage) and one broken.
    settle = [
        csv_mod.decode_settle(settle_record(12.34, 5.66, 18.00)),
        csv_mod.decode_settle(settle_record(12.34, 5.66, 99.99)),
    ]
    report = csv_mod.score_criteria(settle, [], [], input_count=2)

    decomposition = report["criteria"]["total_decomposition_consistency"]
    assert decomposition["score"] == pytest.approx(0.5)
    # The binary verifier cannot see this: both records have non-negative totals.
    assert all(r["total"] >= 0 for r in settle)
    assert report["criteria"]["settle_component_positivity"]["score"] == 1.0


def test_reclaim_threshold_scored_continuously():
    reclaim = [
        csv_mod.decode_reclaim(reclaim_record(5.00, "R")),    # correct (< 10 -> R)
        csv_mod.decode_reclaim(reclaim_record(20.00, "P")),   # correct (>= 10 -> P)
        csv_mod.decode_reclaim(reclaim_record(5.00, "P")),    # wrong
    ]
    report = csv_mod.score_criteria([], [], reclaim, input_count=0)
    score = report["criteria"]["reclaim_threshold_consistency"]["score"]
    assert score == pytest.approx(2 / 3)


def test_overall_orders_correct_above_broken():
    good = csv_mod.score_criteria(
        [csv_mod.decode_settle(settle_record(10.00, 5.00, 15.00))], [], [], 1)
    bad = csv_mod.score_criteria(
        [csv_mod.decode_settle(settle_record(10.00, 5.00, 99.00))], [], [], 1)
    assert good["overall_score"] > bad["overall_score"]


# --- end-to-end via the file-reading path ----------------------------------

def test_verify_outputs_end_to_end(tmp_path):
    out_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    out_dir.mkdir()
    data_dir.mkdir()

    (out_dir / "settle.dat").write_bytes(
        settle_record(12.34, 5.66, 18.00) + settle_record(12.34, 5.66, 99.99))
    (out_dir / "reclaim.dat").write_bytes(
        reclaim_record(5.00, "R") + reclaim_record(20.00, "P"))
    (out_dir / "errors.dat").write_bytes(b"")
    (data_dir / "carloc.dat").write_bytes(b"\x40" * test_outputs.CARLOC_RECORD_SIZE * 2)

    report = csv_mod.verify_outputs(str(out_dir), str(data_dir))

    assert report["criteria"]["total_decomposition_consistency"]["score"] == pytest.approx(0.5)
    assert report["criteria"]["record_count_conservation"]["score"] == pytest.approx(1.0)
    assert isinstance(report["overall_score"], float)


def test_verify_outputs_handles_missing_outputs(tmp_path):
    report = csv_mod.verify_outputs(str(tmp_path / "missing"), str(tmp_path))
    assert report["overall_score"] is None
    assert report["criteria"] == {}


# --- conftest hook wiring --------------------------------------------------

def _load_conftest():
    here = os.path.dirname(__file__)
    spec = importlib.util.spec_from_file_location(
        "conftest_under_test", os.path.join(here, "conftest.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conftest_hook_writes_artifact_without_flipping_reward(tmp_path):
    conftest = _load_conftest()

    out_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    out_dir.mkdir()
    data_dir.mkdir()
    (out_dir / "settle.dat").write_bytes(settle_record(10.00, 5.00, 15.00))
    (data_dir / "carloc.dat").write_bytes(b"\x40" * test_outputs.CARLOC_RECORD_SIZE)

    # Redirect the hook's targets into the tmp tree.
    conftest.OUTPUT_DIR = str(out_dir)
    conftest.DATA_DIR = str(data_dir)
    conftest.REPORT_PATH = str(tmp_path / "verifier" / "scores.json")

    session = types.SimpleNamespace(exitstatus=0)
    # Must not raise and must not change the reward-determining exit status.
    conftest.pytest_sessionfinish(session, 0)

    assert session.exitstatus == 0
    with open(conftest.REPORT_PATH) as handle:
        artifact = json.load(handle)
    assert isinstance(artifact["overall_score"], (int, float))


def test_conftest_hook_never_raises_on_missing_outputs(tmp_path):
    conftest = _load_conftest()
    conftest.OUTPUT_DIR = str(tmp_path / "nope")
    conftest.DATA_DIR = str(tmp_path / "nope")
    conftest.REPORT_PATH = str(tmp_path / "out.json")
    session = types.SimpleNamespace(exitstatus=0)
    conftest.pytest_sessionfinish(session, 0)  # must not raise
    assert session.exitstatus == 0
