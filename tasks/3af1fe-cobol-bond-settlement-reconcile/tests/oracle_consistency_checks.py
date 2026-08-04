"""Oracle-validated consistency checks for the bond-settlement verifier.

Adapts the Generator-Validation (G-V) method from *Klear-CodeTest: Scalable
Test Case Generation for Code Reinforcement Learning* (arXiv:2508.05710):

  * **Generate** candidate corner-case checks from the task spec
    (instruction.md) -- one per trade/field plus cross-record invariants.
  * **Validate** every candidate's *expected* value against a pure-Python
    reference oracle that encodes the correct settlement logic (the gold
    solution in ``solution/solve.sh``). Candidates whose synthesized
    expectation the oracle cannot confirm are *dropped*.
  * **Emit** only the validated checks as runnable test callables.

Mode 2 substitutions (auxiliary components swapped for target-native
equivalents; the G-V core mechanism is preserved at full fidelity):

  * The paper's LLM *generator* is replaced by a deterministic,
    spec-driven generator (a parameter-free table of corner cases).
  * The paper's *gold reference solution* (a COBOL binary) is replaced by
    this Python reference oracle -- the gold binary is not present in the
    agent's environment at test-run time, so the validated expectations are
    baked into the emitted checks and compared against whatever the agent's
    solution produced.

The reference input data below is the exact dataset shipped in
``environment/generate_data.py``; the oracle reimplements the fixed
day-count / accrued-interest / SEC-fee logic from ``solution/solve.sh``.
"""

import datetime
import math
import os

# Output location is configurable for testability; the verifier harness uses
# the /app/output default (see instruction.md).
_OUTPUT_DIR = os.environ.get("BENCH_OUTPUT_DIR", "/app/output")
SETTLEMENT_PATH = os.path.join(_OUTPUT_DIR, "settlement.dat")
RULE606_PATH = os.path.join(_OUTPUT_DIR, "rule606.dat")
RECORD_LEN = 45
RULE606_LEN = 30


# --------------------------------------------------------------------------- #
# Reference input data (mirror of environment/generate_data.py)               #
# --------------------------------------------------------------------------- #
TRADES = {
    "00000001": {"cusip": "912810AA1", "trade_date": "20240315",
                 "settle": "20240318", "qty": 1000, "price": 98.5000,
                 "bs": "B", "venue": "NYS"},
    "00000002": {"cusip": "912810BB2", "trade_date": "20240315",
                 "settle": "20240318", "qty": 500, "price": 101.2500,
                 "bs": "S", "venue": "NAS"},
    "00000003": {"cusip": "912810CC3", "trade_date": "20240315",
                 "settle": "20240318", "qty": 2000, "price": 99.7500,
                 "bs": "B", "venue": "ARC"},
    "00000004": {"cusip": "912810AA1", "trade_date": "20240316",
                 "settle": "20240319", "qty": 750, "price": 98.6250,
                 "bs": "S", "venue": "NYS"},
}

BONDS = {
    "912810AA1": {"rate": 5.2500, "conv": "A", "freq": 4, "par": 100.00},
    "912810BB2": {"rate": 4.7500, "conv": "B", "freq": 2, "par": 100.00},
    "912810CC3": {"rate": 6.0000, "conv": "C", "freq": 4, "par": 100.00},
}

COUPONS = {
    "912810AA1": [("20231215", "4"), ("20240315", "4"), ("20240615", "4")],
    "912810BB2": [("20231215", "2"), ("20240615", "2")],
    "912810CC3": [("20231215", "4"), ("20240315", "4"), ("20240615", "4")],
}

# Rates as the COBOL actually reads them: RATE-PER-MIL is PIC S9(3)V9(6), so
# 0.0000229 is stored with 6 implied decimals and rounds to 0.000023 (the
# generate_data.py encoder confirms this round-trip).
SEC_RATES = [("20190101", 0.000008), ("20230101", 0.000020),
             ("20240101", 0.000023)]


# --------------------------------------------------------------------------- #
# Reference oracle: the correct settlement logic (from solution/solve.sh)     #
# --------------------------------------------------------------------------- #
def _trunc2(value):
    """Truncate to 2 decimal places, mirroring COBOL V99 MOVE semantics."""
    return math.floor(value * 100) / 100.0


def _d(yyyymmdd):
    return datetime.date(int(yyyymmdd[0:4]), int(yyyymmdd[4:6]),
                         int(yyyymmdd[6:8]))


def actual_days(start, end):
    return (_d(end) - _d(start)).days


def days_30_360(start, end):
    sy, sm, sd = int(start[0:4]), int(start[4:6]), int(start[6:8])
    ey, em, ed = int(end[0:4]), int(end[4:6]), int(end[6:8])
    if sd == 31:
        sd = 30
    if ed == 31 and sd >= 30:
        ed = 30
    return (ey - sy) * 360 + (em - sm) * 30 + (ed - sd)


def daycount(start, end, conv):
    if conv in ("A", "C"):
        return actual_days(start, end)
    return days_30_360(start, end)


def last_coupon(cusip, settle, freq):
    best = None
    for cdate, cfreq in COUPONS[cusip]:
        if int(cfreq) == freq and cdate < settle:
            if best is None or cdate > best:
                best = cdate
    return best


def sec_rate(trade_date):
    current = 0.0
    for eff, rate in SEC_RATES:
        if eff <= trade_date:
            current = rate
    return current


def oracle_trade(trade_id):
    """Return the oracle's expected settlement fields for one trade."""
    t = TRADES[trade_id]
    bond = BONDS[t["cusip"]]
    principal = _trunc2(t["qty"] * t["price"])
    lc = last_coupon(t["cusip"], t["settle"], bond["freq"])
    days = daycount(lc, t["settle"], bond["conv"]) if lc else 0
    period = {"A": 365, "B": 360, "C": 360}[bond["conv"]] // bond["freq"]
    accr = _trunc2((bond["rate"] / 100.0) * bond["par"] * t["qty"]
                   * days / period / bond["freq"]) if lc else 0.0
    if t["bs"] == "S":
        fee = max(_trunc2(principal * sec_rate(t["trade_date"])), 0.01)
    else:
        fee = 0.0
    net = principal + accr - (fee if t["bs"] == "S" else 0.0)
    return {"principal": principal, "accr_int": accr, "sec_fee": fee,
            "days_accr": days, "net_amount": _trunc2(net)}


# --------------------------------------------------------------------------- #
# Output parsing (mirrors tests/test_outputs.py decode logic)                 #
# --------------------------------------------------------------------------- #
def _decode_comp3(data):
    result = 0
    for byte in data[:-1]:
        result = result * 100 + ((byte >> 4) & 0x0F) * 10 + (byte & 0x0F)
    last = data[-1]
    result = result * 10 + ((last >> 4) & 0x0F)
    if (last & 0x0F) == 0x0D:
        result = -result
    return result


def parse_settlement_record(record):
    return {
        "trade_id": record[0:8].decode("ascii").strip(),
        "cusip": record[8:17].decode("ascii").strip(),
        "principal": _decode_comp3(record[17:24]) / 100.0,
        "accr_int": _decode_comp3(record[24:30]) / 100.0,
        "sec_fee": _decode_comp3(record[30:35]) / 100.0,
        "net_amount": _decode_comp3(record[35:42]) / 100.0,
        "days_accr": int(_decode_comp3(record[42:45])),
    }


def parse_rule606_record(record):
    return {
        "venue": record[0:3].decode("ascii").strip(),
        "total_orders": int(_decode_comp3(record[3:8])),
        "total_shares": int(_decode_comp3(record[8:14])),
        "market_ord": int(_decode_comp3(record[14:19])),
        "limit_ord": int(_decode_comp3(record[19:24])),
        "pfof_amt": _decode_comp3(record[24:30]) / 100.0,
    }


def _read_records(path, length, parser):
    with open(path, "rb") as handle:
        data = handle.read()
    return [parser(data[i:i + length]) for i in range(0, len(data), length)]


def settlement_records():
    return _read_records(SETTLEMENT_PATH, RECORD_LEN, parse_settlement_record)


def rule606_records():
    return _read_records(RULE606_PATH, RULE606_LEN, parse_rule606_record)


# --------------------------------------------------------------------------- #
# Generator (G): synthesized candidate checks with claimed expectations       #
# --------------------------------------------------------------------------- #
# Each field check: (trade_id, field, claim, tolerance). `claim` is the
# *synthesized* expectation (as an LLM might produce); the Validator
# independently recomputes the truth via oracle_trade and drops any claim
# the oracle does not confirm.
FIELD_CHECKS = [
    ("00000001", "principal", 98500.00, 0.01),
    ("00000001", "accr_int", 43.26, 0.50),
    ("00000001", "days_accr", 3, None),
    ("00000001", "sec_fee", 0.00, 0.001),
    ("00000002", "principal", 50625.00, 0.01),
    ("00000002", "accr_int", 613.54, 1.0),
    ("00000002", "days_accr", 93, None),
    ("00000002", "sec_fee", 1.16, 0.10),
    ("00000003", "principal", 199500.00, 0.01),
    ("00000003", "accr_int", 100.00, 0.50),
    ("00000003", "days_accr", 3, None),
    ("00000003", "sec_fee", 0.00, 0.001),
    ("00000004", "principal", 73968.75, 0.01),
    ("00000004", "accr_int", 43.26, 0.50),
    ("00000004", "days_accr", 4, None),
    ("00000004", "sec_fee", 1.70, 0.10),
]


# --------------------------------------------------------------------------- #
# Validator (V): keep only candidates the oracle confirms                     #
# --------------------------------------------------------------------------- #
def validate_field_check(trade_id, field, claim, tolerance):
    """Return the oracle-confirmed expectation, or None if claim is invalid."""
    truth = oracle_trade(trade_id)[field]
    if tolerance is None:
        return truth if claim == truth else None
    return truth if abs(claim - truth) <= tolerance else None


def validated_specs():
    """G then V: list of (test_name, run_callable) for emitted checks."""
    specs = []

    # Per-trade field checks (oracle-validated).
    for trade_id, field, claim, tol in FIELD_CHECKS:
        expected = validate_field_check(trade_id, field, claim, tol)
        if expected is None:
            # Synthesized claim rejected by the oracle -- drop (G-V discipline).
            continue
        specs.append(_field_spec(trade_id, field, expected, tol))

    # Cross-record invariants (derived purely from the parsed output, so they
    # are oracle-validated by construction against the reference dataset).
    specs.extend(_invariant_specs())
    return specs


# --------------------------------------------------------------------------- #
# Check factories                                                             #
# --------------------------------------------------------------------------- #
def _field_spec(trade_id, field, expected, tol):
    def run():
        rec = next((r for r in settlement_records()
                    if r["trade_id"] == trade_id), None)
        assert rec is not None, f"trade {trade_id} missing from settlement.dat"
        actual = rec[field]
        if tol is None:
            assert actual == expected, (
                f"trade {trade_id}.{field}: expected {expected}, got {actual}")
        else:
            assert abs(actual - expected) <= tol, (
                f"trade {trade_id}.{field}: expected ~{expected} (±{tol}), "
                f"got {actual}")

    name = f"test_klear_field_{trade_id}_{field}"
    return (name, run)


def _invariant_specs():
    specs = []

    # Quarterly bonds (AA1, CC3) must accrue non-zero days -- the freq=2
    # hardcoding bug zeros these out, so this invariant catches it broadly.
    def run_days_nonzero():
        for rec in settlement_records():
            assert rec["days_accr"] >= 1, (
                f"trade {rec['trade_id']} days_accr={rec['days_accr']} "
                "should be >= 1 (quarterly coupon accrual)")

    specs.append(("test_klear_invariant_days_nonzero", run_days_nonzero))

    # BUY trades carry no SEC fee; SELL trades do.
    def run_fee_direction():
        by_id = {r["trade_id"]: r for r in settlement_records()}
        for tid, trade in TRADES.items():
            fee = by_id[tid]["sec_fee"]
            if trade["bs"] == "B":
                assert fee == 0.0, f"BUY trade {tid} sec_fee {fee} != 0"
            else:
                assert fee > 0.0, f"SELL trade {tid} sec_fee {fee} <= 0"

    specs.append(("test_klear_invariant_fee_direction", run_fee_direction))

    # Sum of per-venue total shares must equal the sum of all trade qtys
    # (settlement <-> Rule 606 reconciliation consistency).
    def run_total_shares_reconcile():
        venue_shares = sum(r["total_shares"] for r in rule606_records())
        trade_shares = sum(t["qty"] for t in TRADES.values())
        assert venue_shares == trade_shares, (
            f"Rule 606 total shares {venue_shares} != trade qty sum "
            f"{trade_shares}")

    specs.append(("test_klear_invariant_total_shares_reconcile",
                  run_total_shares_reconcile))

    # Net must recompute from principal/accr/fee for every record (internal
    # consistency of the settlement record itself).
    def run_net_recompute():
        for rec in settlement_records():
            trade = TRADES[rec["trade_id"]]
            fee = rec["sec_fee"] if trade["bs"] == "S" else 0.0
            expected_net = _trunc2(rec["principal"] + rec["accr_int"] - fee)
            assert abs(rec["net_amount"] - expected_net) < 0.02, (
                f"trade {rec['trade_id']} net {rec['net_amount']} != "
                f"principal+accr-fee {expected_net}")

    specs.append(("test_klear_invariant_net_recompute", run_net_recompute))

    return specs


# --------------------------------------------------------------------------- #
# Integration check: cross-validate our parser against the existing verifier  #
# --------------------------------------------------------------------------- #
def _integration_spec():
    def run():
        # Import the EXISTING (non-new) verifier module to prove integration
        # with the task's test harness, and assert our parsers agree.
        import test_outputs  # noqa: F401  (existing module in tests/)
        with open(SETTLEMENT_PATH, "rb") as handle:
            data = handle.read()
        for i in range(0, len(data), RECORD_LEN):
            rec = data[i:i + RECORD_LEN]
            ours = parse_settlement_record(rec)
            theirs = test_outputs.parse_settlement_record(rec)
            assert ours == theirs, (
                f"parser drift on {rec!r}: ours={ours} theirs={theirs}")

    return ("test_klear_integration_verifier_parser_matches", run)


def checks():
    """All emitted checks (G-V validated), exposed for conftest injection."""
    specs = validated_specs()
    specs.append(_integration_spec())
    return specs
