"""
Locksmith-style witness search for deterministic migration parity validation.

Adapted (Mode 3 -- inspired experiment) from:

    "Agentic Method for Deterministic Validation of Legacy Code Migration"
    arXiv:2607.28271v1  -- the "Locksmith Loop".

The paper's core insight, applied to this benchmark's COBOL -> Python railroad
retirement migration task: the verifier already runs *two runtime environments
off-mainframe* (the COBOL source under GnuCOBOL, and the migrated Python target)
under a *deterministic parity oracle* (byte-for-byte BENEFITS output). What it
lacks is the Locksmith Loop's contribution -- a systematic *Witness Search* over
input mocks that penetrates the calculation branches, plus an analyzer that
surfaces the input-space condition (a "Locked Paragraph") under which source and
target diverge. The existing suite only probes one fixed record and one random
record; this module searches a branch-covering witness set.

Target-native reframings (cited per the honesty discipline):
  * The paper's LLM-driven agentic witness generation is replaced by a
    deterministic, parameterized witness generator. The verifier must be a
    deterministic oracle (the paper's own emphasis is *deterministic*
    validation), so no LLM is invoked here.
  * The paper's code-level "Locked Paragraph" (a condition blocking deeper
    exploration) is reframed as the witness branch signature shared by every
    divergent input -- the input-space condition that blocks parity.
  * The paper's COBOL -> Java pair is this task's COBOL -> Python pair.

The module is runtime-agnostic: ``run_locksmith_loop`` takes injected runtimes
so it is unit-testable without /app. ``run_from_env`` wires the real runtimes
reused from the existing ``test_outputs`` call-site module.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# Fixed-width EMPLOYEE.DAT record layout (matches environment/data and the
# existing ``test_no_hardcoded_output`` witness). All witnesses stay inside this
# proven structure so a *correct* migration passes every witness.
SSN_LEN = 9
NAME_LEN = 30
DOB_LEN = 8
RET_LEN = 8
SVC_LEN = 3
EARNINGS_LEN = 585


@dataclass
class Witness:
    """A single synthesized input mock, tagged by the branches it penetrates."""

    witness_id: str
    label: str
    tags: dict  # branch name -> human-readable value (drives Locked-Paragraph analysis)
    record: str  # one fixed-width EMPLOYEE.DAT line (no trailing newline)


@dataclass
class ParityResult:
    passed: bool
    total_records: int
    divergent_indices: list = field(default_factory=list)
    note: str = ""


@dataclass
class LockedParagraph:
    """An input-space condition under which source and target diverged."""

    condition: str  # e.g. "retirement_year=2020"
    divergent_witnesses: int


@dataclass
class LoopReport:
    witnesses_run: int
    witnesses_covered: int  # produced non-empty reference output
    parity_passed: int
    divergences: list  # list of dict(witness=Witness, result=ParityResult)
    locked_paragraphs: list  # list of LockedParagraph

    @property
    def pass_rate(self) -> float:
        covered = self.witnesses_covered
        return 1.0 if covered == 0 else self.parity_passed / covered


def build_employee_record(
    ssn: str, name: str, dob: str, ret_date: str, svc: str, earnings_by_year: dict
) -> str:
    """Assemble one fixed-width EMPLOYEE.DAT line from typed fields."""
    ssn = "".join(c for c in ssn if c.isdigit()).ljust(SSN_LEN, "0")[:SSN_LEN]
    name = name.ljust(NAME_LEN)[:NAME_LEN]
    dob = "".join(c for c in dob if c.isdigit()).ljust(DOB_LEN, "0")[:DOB_LEN]
    ret_date = "".join(c for c in ret_date if c.isdigit()).ljust(RET_LEN, "0")[:RET_LEN]
    svc = "".join(c for c in svc if c.isdigit()).ljust(SVC_LEN, "0")[:SVC_LEN]

    earnings = ""
    for year in range(1990, 2020):
        cents = earnings_by_year.get(year, 0)
        earnings += f"{year}{cents:09d}"
    earnings = earnings.ljust(EARNINGS_LEN, "0")[:EARNINGS_LEN]
    return f"{ssn}{name}{dob}{ret_date}{svc}{earnings}"


# Branch dimensions for Witness Search. Each tuple is (tag_value, ctor args)
# chosen to drive a distinct calculation path in the RRB benefit logic.
_DOB_BRANCHES = [
    ("birth_year=1955", "19550314"),  # early indexing era
    ("birth_year=1965", "19650801"),
    ("birth_year=1975", "19751120"),  # later indexing era
]
_RET_BRANCHES = [
    ("retirement_year=2020", "20200630"),
    ("retirement_year=2024", "20240115"),
    ("retirement_year=2025", "20250909"),
]
_SVC_BRANCHES = [
    ("service_years=low", "080"),
    ("service_years=mid", "220"),
    ("service_years=high", "380"),
]
_EARNINGS_BRANCHES = [
    ("earnings=low", lambda rng: {y: rng.randint(20000, 35000) * 100 for y in range(1990, 2020)}),
    ("earnings=mid", lambda rng: {y: rng.randint(40000, 60000) * 100 for y in range(1990, 2020)}),
    ("earnings=high", lambda rng: {y: rng.randint(70000, 95000) * 100 for y in range(1990, 2020)}),
    ("earnings=sparse", lambda rng: {y: rng.randint(30000, 80000) * 100 for y in range(1990, 2020) if rng.random() < 0.4}),
]


def generate_witnesses(seed: int = 20260728) -> list:
    """Synthesize a branch-covering witness set (deterministic for a given seed)."""
    rng = random.Random(seed)
    witnesses: list[Witness] = []

    def add(tags, dob, ret_date, svc, earnings_fn):
        wid = f"w{len(witnesses):02d}"
        ssn = f"{rng.randint(100000000, 999999999)}"
        name = f"LOCKSMITH {wid} X".ljust(NAME_LEN)[:NAME_LEN]
        record = build_employee_record(
            ssn, name, dob, ret_date, svc, earnings_fn(rng)
        )
        label = ",".join(tags.values())
        witnesses.append(Witness(wid, label, dict(tags), record))

    # Orthogonal sweep: vary one branch dimension per witness while holding the
    # others at a representative baseline, so a divergence localizes cleanly.
    base_dob, base_ret, base_svc, base_earn = (
        _DOB_BRANCHES[1], _RET_BRANCHES[1], _SVC_BRANCHES[1], _EARNINGS_BRANCHES[1],
    )
    for tag, val in _DOB_BRANCHES:
        add({"baseline": "dob-sweep", tag: tag}, val, base_ret[1], base_svc[1], base_earn[1])
    for tag, val in _RET_BRANCHES:
        add({"baseline": "ret-sweep", tag: tag}, base_dob[1], val, base_svc[1], base_earn[1])
    for tag, val in _SVC_BRANCHES:
        add({"baseline": "svc-sweep", tag: tag}, base_dob[1], base_ret[1], val, base_earn[1])
    for tag, fn in _EARNINGS_BRANCHES:
        add({"baseline": "earn-sweep", tag: tag}, base_dob[1], base_ret[1], base_svc[1], fn)

    return witnesses


def parity_check(cobol_bytes: bytes, python_bytes: bytes, record_size: int) -> ParityResult:
    """Deterministic, record-aligned byte-for-byte parity oracle."""
    if not cobol_bytes and not python_bytes:
        return ParityResult(True, 0, note="both empty")
    if not cobol_bytes:
        return ParityResult(False, 0, note="cobol reference empty")
    if not python_bytes:
        return ParityResult(False, 0, note="python target empty")

    cobol_count = len(cobol_bytes) // record_size
    python_count = len(python_bytes) // record_size
    if cobol_count != python_count:
        return ParityResult(
            False, max(cobol_count, python_count),
            note=f"record-count mismatch cobol={cobol_count} python={python_count}",
        )

    divergent = []
    for i in range(0, cobol_count * record_size, record_size):
        if cobol_bytes[i:i + record_size] != python_bytes[i:i + record_size]:
            divergent.append(i // record_size)
    return ParityResult(not divergent, cobol_count, divergent)


def analyze_locked_paragraphs(divergences: list, all_witnesses: list) -> list:
    """
    Surface the witness branch signature shared by every divergence.

    A "Locked Paragraph" is the input-space condition that blocks parity: the
    set of ``tag=value`` pairs present in *every* divergent witness but *not* in
    every witness overall. Returns [] when there are no divergences.
    """
    if not divergences:
        return []

    def pairs(w):
        return {f"{k}={v}" for k, v in w.tags.items()}

    universal = set.intersection(*[pairs(w) for w in all_witnesses]) if all_witnesses else set()
    shared = set.intersection(*[pairs(d["witness"]) for d in divergences])
    locked = sorted(shared - universal)

    return [
        LockedParagraph(condition=p, divergent_witnesses=len(divergences))
        for p in locked
    ] or [LockedParagraph(condition="(no single shared condition; check per-witness tags)",
                          divergent_witnesses=len(divergences))]


def run_locksmith_loop(
    write_record: Callable[[str], None],
    run_cobol: Callable[[], bytes],
    run_python: Callable[[], bytes],
    record_size: int,
    witnesses: Optional[list] = None,
    report_path: Optional[Path] = None,
) -> LoopReport:
    """
    Execute the Locksmith Loop over the witness set.

    For each witness: install the input mock, run the COBOL reference and the
    migrated target, and apply the deterministic parity oracle. Witnesses that
    fail to produce reference output are treated as "routing boundaries"
    (uncovered) rather than divergences -- they do not gate the verdict.
    """
    witnesses = witnesses if witnesses is not None else generate_witnesses()
    divergences = []
    covered = 0
    passed = 0

    for w in witnesses:
        write_record(w.record)
        cobol_out = run_cobol()
        if not cobol_out:
            continue  # witness did not penetrate -- a routing boundary, skip
        covered += 1
        python_out = run_python()
        result = parity_check(cobol_out, python_out, record_size)
        if result.passed:
            passed += 1
        else:
            divergences.append({"witness": w, "result": result})

    locked = analyze_locked_paragraphs(divergences, witnesses)
    report = LoopReport(
        witnesses_run=len(witnesses),
        witnesses_covered=covered,
        parity_passed=passed,
        divergences=divergences,
        locked_paragraphs=locked,
    )

    if report_path is not None:
        try:
            report_path.write_text(summarize_report(report))
        except OSError:
            pass  # report is advisory; never gate on write failure
    return report


def summarize_report(report: LoopReport) -> str:
    """Human + machine readable JSON report of the loop's findings."""
    payload = {
        "witnesses_run": report.witnesses_run,
        "witnesses_covered": report.witnesses_covered,
        "parity_passed": report.parity_passed,
        "parity_pass_rate": round(report.pass_rate, 4),
        "locked_paragraphs": [
            {"condition": lp.condition, "divergent_witnesses": lp.divergent_witnesses}
            for lp in report.locked_paragraphs
        ],
        "divergences": [
            {
                "witness_id": d["witness"].witness_id,
                "label": d["witness"].label,
                "tags": d["witness"].tags,
                "note": d["result"].note,
                "divergent_records": d["result"].divergent_indices,
            }
            for d in report.divergences
        ],
    }
    return json.dumps(payload, indent=2)


def _ensure_compiled(test_outputs):
    """Compile the COBOL reference binary once if it is missing."""
    import subprocess

    if test_outputs.COBOL_BIN.exists():
        return True
    if not test_outputs.COBOL_SRC.exists():
        return False
    result = subprocess.run(
        ["cobc", "-x", "-febcdic-table=ebcdic500_latin1",
         "-I", str(test_outputs.COPYBOOKS_DIR), "-o", str(test_outputs.COBOL_BIN),
         str(test_outputs.COBOL_SRC), str(test_outputs.COBOL_T1),
         str(test_outputs.COBOL_T2)],
        capture_output=True, cwd="/app",
    )
    return result.returncode == 0


def run_from_env():
    """
    Wire the loop to the task's real dual runtime, reusing the existing
    ``test_outputs`` call-site module. Returns None when the dual runtime is not
    available (e.g. outside the task container) so callers can skip cleanly.
    """
    import test_outputs  # the existing call-site module (its helpers are reused below)

    # Guard: only run where the COBOL source, the GnuCOBOL compiler, and the
    # migrated Python target all exist (i.e. inside the task container after the
    # agent has produced a solution). Otherwise this is a no-op.
    if not (test_outputs.COBOL_SRC.exists()
            and test_outputs.PYTHON_SRC.exists()
            and test_outputs.COBC_COMPILER.exists()):
        return None
    if not _ensure_compiled(test_outputs):
        return None

    employee_path = test_outputs.DATA_DIR / "EMPLOYEE.DAT"
    original_employee = None
    if employee_path.exists():
        original_employee = employee_path.read_bytes()

    def write_record(record_line: str) -> None:
        employee_path.write_text(record_line + "\n")

    try:
        report = run_locksmith_loop(
            write_record=write_record,
            run_cobol=test_outputs.run_cobol,
            run_python=test_outputs.run_python,
            record_size=test_outputs.RECORD_SIZE,
            witnesses=generate_witnesses(),
            report_path=Path("/app/locksmith_report.json"),
        )
    finally:
        # Restore the original input data so the remainder of the suite (which
        # also reads EMPLOYEE.DAT) is unaffected by the witness search.
        if original_employee is not None and employee_path.exists():
            employee_path.write_bytes(original_employee)

    return report
