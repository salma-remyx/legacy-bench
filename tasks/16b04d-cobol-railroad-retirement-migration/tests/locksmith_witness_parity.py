"""Branch-targeted witness synthesis for deterministic migration parity.

Adapted (Mode 2) from:

    "Agentic Method for Deterministic Validation of Legacy Code Migration"
    (arXiv:2607.28271v1) -- the "Locksmith Loop".

The paper's core mechanism is *Witness Search*: synthesize program inputs
designed to drive the legacy program down specific calculation branches, then
assert the migrated target reproduces the legacy reference's output under a
deterministic parity check.  Branches the oracle cannot judge are surfaced as
*Locked Paragraphs* rather than silently treated as passes.

This module delivers that core mechanism for the Railroad Retirement COBOL ->
Python migration task.

Kept at full fidelity (the paper's contribution):
  * Witness Search -- a curated catalog of employee records, each built from
    the copybook PIC layout to drive the calculator down a distinct branch:
    the three PIA bend-point brackets, the age-reduction tiers, the long-
    service no-reduction path, and the eligibility-error path.
  * Deterministic parity -- witnesses are run through both the COBOL reference
    (the oracle) and the target; the BENEFITS output is compared record by
    record.
  * Locked-Paragraph reporting -- when the oracle yields no output for a
    witness set, that is reported instead of counting as a silent pass.

Substituted with target-native equivalents (Mode 2):
  * The paper's agentic / LLM-driven witness search is replaced by a
    parameter-free, schema-driven generator: witnesses are constructed
    directly from the copybook record layout and the calculator's known
    branch conditions.  (The LLM search is the paper's auxiliary engine; the
    signal it produces -- inputs that penetrate branches -- is what we emit.)
  * The paper's off-mainframe COBOL + Java instrumentation is replaced by this
    benchmark's existing ``cobc``-compiled COBOL oracle and the agent's Python
    target, driven through the existing verifier helpers
    (``test_outputs.run_cobol`` / ``run_python``).
  * The paper's standalone coverage framework is cut; branch penetration is
    reported inline as part of the verifier output.

The module is intentionally pure: no I/O, no subprocess.  It builds witness
records and reasons about parity bytes.  The verifier wiring that actually
runs the COBOL/Python oracle lives in ``conftest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Benefit record layout (copybook BENREC.cpy): fixed 105-byte records.
BENEFIT_RECORD_SIZE = 105

# Employee record layout (copybook EMPREC.cpy), fixed-width text:
#   SSN X(9) NAME X(30) DOB 9(8) RET 9(8) SVC 9(2)V9 EARNINGS 45 * (year 9(4) amt 9(7)V99)
EMPLOYEE_RECORD_SIZE = 643
EARNINGS_ENTRIES = 45
EARNINGS_ENTRY_SIZE = 13  # year(4) + amount(9)
EARNINGS_YEARS = list(range(1990, 2025))  # 35 indexed earnings years


@dataclass(frozen=True)
class Witness:
    """One synthesized employee record targeting a calculation branch."""

    witness_id: str
    branch: str  # short label of the code path being penetrated
    record: str  # full EMPLOYEE_RECORD_SIZE-char text line

    @property
    def label(self) -> str:
        return f"{self.witness_id} [{self.branch}]"


@dataclass
class ParityResult:
    """Outcome of comparing oracle and target output over the witness set."""

    status: str  # "pass" | "mismatch" | "oracle_locked" | "target_empty"
    record_count: int = 0
    mismatches: list = field(default_factory=list)  # list of (index, cobol, python)
    notes: str = ""


def _earnings_block(base_amount: float) -> str:
    """Build the 45-entry earnings table; 35 real years then zero-padded.

    Each entry is year(4) + amount(9) where amount is whole cents (PIC 9(7)V99).
    """
    cents = int(round(base_amount * 100))
    entries = []
    for i in range(EARNINGS_ENTRIES):
        if i < len(EARNINGS_YEARS):
            year = EARNINGS_YEARS[i]
            entries.append(f"{year}{cents:09d}")
        else:
            entries.append("0000" + "0" * 9)
    return "".join(entries)


def _employee_record(
    ssn: int,
    name: str,
    dob: str,
    retire: str,
    svc_tenths: int,
    base_amount: float,
) -> str:
    """Assemble one fixed-width employee record from copybook fields.

    ``svc_tenths`` is service-years * 10 (PIC 9(2)V9): 100 = 10.0, 350 = 35.0.
    """
    line = (
        f"{ssn:09d}"
        f"{name.ljust(30)[:30]}"
        f"{dob}"
        f"{retire}"
        f"{svc_tenths:03d}"
        f"{_earnings_block(base_amount)}"
    )
    # Guard the layout: a malformed witness would itself be a test bug, and the
    # COBOL reader would misparse every field after the break.
    assert len(line) == EMPLOYEE_RECORD_SIZE, (
        f"witness record is {len(line)} bytes, expected {EMPLOYEE_RECORD_SIZE}"
    )
    return line


def synthesize_witnesses() -> list[Witness]:
    """Return the curated witness catalog, one per calculation branch.

    Each witness is constructed to land clearly inside its target branch (well
    away from bend-point / age boundaries) so that a *correct* migration must
    reproduce the COBOL oracle byte-for-byte on every one of them.  Branch
    targeting was validated against the reference calculator's AIME/bracket
    math; values are chosen to be parity-safe, not boundary-precise.
    """
    specs = [
        # (id, branch, ssn, name, dob, retire, svc_tenths, base_amount)
        (
            "low_pia_bracket",
            "PIA bracket 1 (aime <= bp1, 90% factor)",
            111000001,
            "LOW PIA BRANCH WITNESS",
            "19600115",
            "20240115",
            100,
            8000.0,
        ),
        (
            "mid_pia_bracket",
            "PIA bracket 2 (bp1 < aime <= bp2, 32% factor)",
            222000002,
            "MID PIA BRANCH WITNESS",
            "19570115",
            "20240115",
            100,
            45000.0,
        ),
        (
            "high_pia_bracket",
            "PIA bracket 3 (aime > bp2, 15% factor)",
            333000003,
            "HIGH PIA BRANCH WITNESS",
            "19570115",
            "20240115",
            100,
            130000.0,
        ),
        (
            "long_service",
            "long-service (svc >= 30y, no age reduction)",
            444000004,
            "LONG SERVICE WITNESS",
            "19570115",
            "20240115",
            350,
            80000.0,
        ),
        (
            "deep_early_retire",
            "deep early retirement (>36mo age reduction, both tiers)",
            555000005,
            "EARLY RETIREMENT WITNESS",
            "19640115",
            "20240115",
            100,
            45000.0,
        ),
        (
            "insufficient_service",
            "eligibility error (svc < 5y, status E)",
            666000006,
            "INSUFFICIENT SERVICE WITNESS",
            "19600115",
            "20240115",
            30,
            45000.0,
        ),
    ]
    witnesses = []
    for wid, branch, ssn, name, dob, retire, svc, base in specs:
        record = _employee_record(ssn, name, dob, retire, svc, base)
        witnesses.append(Witness(witness_id=wid, branch=branch, record=record))
    return witnesses


def build_employee_dataset(witnesses: list[Witness]) -> str:
    """Render witnesses as an EMPLOYEE.DAT body (newline-terminated records)."""
    return "\n".join(w.record for w in witnesses) + "\n"


def compare_benefits(
    cobol_output: bytes,
    python_output: bytes,
    expected_records: int,
) -> ParityResult:
    """Compare oracle (COBOL) and target (Python) BENEFITS bytes record by record.

    Status semantics:
      * ``pass``          -- every produced record matches byte-for-byte.
      * ``mismatch``      -- at least one record (or the record count) differs.
      * ``oracle_locked`` -- the COBOL oracle produced no output, so it cannot
                             judge the target (reported as a Locked Paragraph,
                             not a failure).
      * ``target_empty``  -- the oracle produced output but the target did not,
                             a real parity failure.
    """
    if len(cobol_output) == 0:
        return ParityResult(
            status="oracle_locked",
            notes="COBOL oracle produced no output for the witness set "
            "(Locked Paragraph: oracle cannot judge these branches).",
        )
    if len(python_output) == 0:
        return ParityResult(
            status="target_empty",
            notes="Target produced no output while the COBOL oracle did.",
        )

    size = BENEFIT_RECORD_SIZE
    cobol_count = len(cobol_output) // size
    python_count = len(python_output) // size
    mismatches: list = []

    for i in range(min(cobol_count, python_count)):
        cobol_rec = cobol_output[i * size : (i + 1) * size]
        python_rec = python_output[i * size : (i + 1) * size]
        if cobol_rec != python_rec:
            mismatches.append((i, cobol_rec, python_rec))

    if cobol_count != python_count:
        mismatches.append(("count", cobol_count, python_count))

    status = "pass" if not mismatches else "mismatch"
    return ParityResult(
        status=status,
        record_count=cobol_count,
        mismatches=mismatches,
        notes=f"compared {min(cobol_count, python_count)} of {expected_records} "
        f"witness records (cobol={cobol_count}, python={python_count}).",
    )


def format_report(witnesses: list[Witness], result: ParityResult) -> str:
    """Render a human-readable branch-penetration / parity report.

    This is the Locksmith Loop's analyzer output: which branches were targeted,
    whether parity held, and any Locked Paragraphs.
    """
    lines = [
        "Locksmith witness-parity report",
        f"  witnesses synthesized: {len(witnesses)} "
        f"(targeting {len({w.branch for w in witnesses})} distinct branches)",
    ]
    for w in witnesses:
        lines.append(f"    - {w.label}")

    lines.append(f"  parity status: {result.status}")
    if result.notes:
        lines.append(f"  {result.notes}")

    if result.status == "mismatch":
        lines.append("  mismatches:")
        for entry in result.mismatches:
            if entry[0] == "count":
                _, cobol_n, python_n = entry
                lines.append(f"    record count: cobol={cobol_n} python={python_n}")
            else:
                idx, cobol_rec, python_rec = entry
                witness = witnesses[idx] if idx < len(witnesses) else None
                where = witness.label if witness else f"record #{idx}"
                lines.append(f"    {where}")
                lines.append(f"      cobol : {cobol_rec!r}")
                lines.append(f"      python: {python_rec!r}")
    elif result.status == "oracle_locked":
        lines.append("  locked paragraphs: oracle declined to judge; "
                     "treat witness set as not penetrated, not as passed.")
    return "\n".join(lines)
