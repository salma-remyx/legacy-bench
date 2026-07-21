"""Continuous settlement verification for the railcar settlement task.

The binary verifier in ``test_outputs.py`` checks structure, compilation,
record sizes and status flags, but it never checks that the settlement
*amounts* are internally consistent -- a solution can emit arbitrary positive
totals and still pass. This module fills that semantic gap with a continuous,
criteria-decomposed verifier over the decoded EBCDIC outputs.

Adapted (Mode 2) port of "LLM-as-a-Verifier: A General-Purpose Verification
Framework" (arXiv:2607.05391v1). The paper's core mechanism is reproduced at
full fidelity: verification treated as a new scaling axis, expressed through
(1) score granularity, (2) repeated evaluation and (3) criteria decomposition,
producing *continuous* per-criterion scores that aggregate into a ranking
signal rather than a single binary verdict.

Substituted auxiliary component: the paper computes each criterion's continuous
score as an expectation over an LLM's scoring-token logits. No LLM endpoint is
available inside the task container, so each criterion is instead scored by a
parameter-free deterministic proxy over the decoded records. The output shape
-- a continuous ``[0, 1]`` score per criterion plus a binomial standard error
(which realises the repeated-evaluation / variance-reduction axis) aggregated
into an overall ranking score -- matches the paper's verifier interface.
Swapping the proxy for an LLM scorer would change nothing upstream.
"""

import json
import math
import os

# Reuse the existing decoder so this module stays consistent with the binary
# verifier's record model rather than re-implementing it. ``test_outputs`` lives
# next to this file and is on ``sys.path`` when pytest collects the task.
try:
    from test_outputs import decode_comp3 as _decode_comp3
except Exception:  # fallback only when test_outputs is not importable
    def _decode_comp3(data):
        result = 0
        for byte in data[:-1]:
            result = result * 100 + ((byte >> 4) & 0x0F) * 10 + (byte & 0x0F)
        last = data[-1]
        result = result * 10 + ((last >> 4) & 0x0F)
        if (last & 0x0F) == 0x0D:
            result = -result
        return result / 100.0


decode_comp3 = _decode_comp3  # re-exported so callers can confirm reuse

SETTLE_RECORD_SIZE = 52
RECLAIM_RECORD_SIZE = 44
CARLOC_RECORD_SIZE = 245

DECOMP_EPSILON = 0.01  # COMP-3 carries 2 implied decimals
RECLAIM_THRESHOLD = 10.00


def decode_settle(raw):
    """Decode a 52-byte settle/errors record into a field dict."""
    return {
        "car_id": raw[0:10].decode("cp500", errors="replace"),
        "owning_rr": raw[18:22].decode("cp500", errors="replace"),
        "respons_rr": raw[22:26].decode("cp500", errors="replace"),
        "per_diem": decode_comp3(raw[26:31]),
        "mileage": decode_comp3(raw[31:36]),
        "total": decode_comp3(raw[36:41]),
        "status": raw[48:49].decode("cp500", errors="replace"),
        "error_code": raw[49:52].decode("cp500", errors="replace"),
    }


def decode_reclaim(raw):
    """Decode a 44-byte reclaim record into a field dict."""
    return {
        "orig_car_id": raw[10:20].decode("cp500", errors="replace"),
        "disputed": decode_comp3(raw[36:41]),
        "status": raw[43:44].decode("cp500", errors="replace"),
    }


def _ratio(ok, n):
    """Continuous score in [0, 1] plus binomial standard error for n checks.

    The stderr realises the paper's repeated-evaluation / variance-reduction
    axis deterministically: it shrinks as more records are evaluated, exactly
    as repeated evaluation reduces score variance in the original formulation.
    """
    if n == 0:
        return None
    p = ok / n
    stderr = math.sqrt(max(p * (1.0 - p), 0.0) / n)
    return {"score": p, "n": n, "stderr": stderr}


def criterion_total_decomposition(settle):
    """total-amt must equal per-diem-amt + mileage-amt.

    This is the semantic gap the binary verifier cannot see: a solution can
    pass every existing test while emitting totals that do not add up.
    """
    ok = sum(
        1 for r in settle
        if abs(r["total"] - (r["per_diem"] + r["mileage"])) <= DECOMP_EPSILON
    )
    return _ratio(ok, len(settle))


def criterion_component_positivity(settle):
    """A real settlement attributes a non-zero charge.

    Catches all-zero stub output, which the non-negative-total check in
    ``test_outputs.py`` treats as acceptable.
    """
    ok = sum(1 for r in settle if r["per_diem"] > 0 or r["mileage"] > 0)
    return _ratio(ok, len(settle))


def criterion_reclaim_threshold(reclaim):
    """disputed-amt < $10 -> 'R' (rejected), otherwise 'P' (pending)."""
    ok = 0
    for r in reclaim:
        expected = "R" if r["disputed"] < RECLAIM_THRESHOLD else "P"
        if r["status"] == expected:
            ok += 1
    return _ratio(ok, len(reclaim))


def criterion_error_well_formedness(errors):
    """errors.dat rows should carry status 'E', a non-empty error-code and a
    negative total (per the spec, negative totals route to errors.dat)."""
    ok = sum(
        1 for r in errors
        if r["status"] == "E"
        and r["error_code"].strip() != ""
        and r["total"] < 0
    )
    return _ratio(ok, len(errors))


def criterion_record_conservation(settle_count, error_count, input_count):
    """How closely produced records conserve the input record count.

    Continuous form of the data-flow-integrity check: partial credit when the
    counts are off, rather than a hard pass/fail.
    """
    if input_count == 0:
        return None
    produced = settle_count + error_count
    score = 1.0 - abs(input_count - produced) / input_count
    return {
        "score": max(0.0, min(1.0, score)),
        "n": input_count,
        "stderr": 0.0,
        "produced": produced,
        "expected": input_count,
    }


def score_criteria(settle, errors, reclaim, input_count):
    """Score every decomposed criterion and aggregate into a ranking score."""
    criteria = {
        "total_decomposition_consistency": criterion_total_decomposition(settle),
        "settle_component_positivity": criterion_component_positivity(settle),
        "reclaim_threshold_consistency": criterion_reclaim_threshold(reclaim),
        "error_record_well_formedness": criterion_error_well_formedness(errors),
        "record_count_conservation": criterion_record_conservation(
            len(settle), len(errors), input_count),
    }
    evaluated = [c for c in criteria.values() if c is not None]
    overall = (
        sum(c["score"] for c in evaluated) / len(evaluated) if evaluated else None
    )
    return {
        "overall_score": overall,
        "criteria": criteria,
        "counts": {
            "settle": len(settle),
            "errors": len(errors),
            "reclaim": len(reclaim),
            "input": input_count,
        },
    }


def _read_records(path, size, decoder):
    """Return decoded records, or None when the file is absent.

    An empty or mis-sized file yields an empty list (zero records) rather than
    None, so the verifier can still score the remaining criteria.
    """
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) == 0 or len(data) % size != 0:
        return []
    return [decoder(data[i:i + size]) for i in range(0, len(data), size)]


def _count_input(path):
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as handle:
        data = handle.read()
    return len(data) // CARLOC_RECORD_SIZE if data else 0


def verify_outputs(output_dir="/app/output", data_dir="/app/data"):
    """Run the continuous verifier against the task's output directory."""
    settle = _read_records(os.path.join(output_dir, "settle.dat"),
                           SETTLE_RECORD_SIZE, decode_settle)
    errors = _read_records(os.path.join(output_dir, "errors.dat"),
                           SETTLE_RECORD_SIZE, decode_settle)
    reclaim = _read_records(os.path.join(output_dir, "reclaim.dat"),
                            RECLAIM_RECORD_SIZE, decode_reclaim)
    if settle is None and errors is None and reclaim is None:
        return {
            "overall_score": None,
            "criteria": {},
            "note": "no output files present; solution produced no output",
        }
    input_count = _count_input(os.path.join(data_dir, "carloc.dat"))
    return score_criteria(settle or [], errors or [], reclaim or [], input_count)


def write_report(report, path):
    """Persist a verifier report as JSON, creating parent dirs as needed."""
    text = json.dumps(report, indent=2, sort_keys=True)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)
    return path
