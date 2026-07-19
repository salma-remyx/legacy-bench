"""Continuous, criteria-decomposed scoring for the Legacy-Bench verifier.

Adapted (Mode 2) from "LLM-as-a-Verifier: A General-Purpose Verification
Framework" (arXiv:2607.05391).

The paper's insight
-------------------
Verification should yield a FINE-GRAINED, CONTINUOUS, CRITERIA-DECOMPOSED
signal with explanations, instead of a single binary pass/fail. Legacy-Bench's
headline finding -- "In 97% of failures the agent believes it has solved the
task" and "COBOL bugs are silent -- wrong output looks correct" -- is exactly
the symptom this addresses: a binary ``reward.txt`` hides *which* requirement
failed and *why*.

What is preserved (the contribution)
------------------------------------
- Criteria decomposition: each ``test_*`` function in a task's
  ``test_outputs.py`` is one scored criterion; its docstring (especially the
  ``Task requirement:`` line) is the human-readable criterion text.
- Score granularity: instead of 2 levels (pass / fail) the score ranges over
  ``n_criteria + 1`` levels, giving calibrated separation between partial and
  full solutions.
- Failure explanation: every failed criterion carries its requirement text
  plus the assertion message extracted from the failing test, turning a silent
  ``0`` into a diagnostic.

What is substituted (the auxiliary, Mode 2)
-------------------------------------------
The paper computes continuous scores as an expectation over the distribution
of *LLM scoring-token logits*, and scales further via repeated evaluation. That
needs an LLM endpoint with logit access and (for repeated evaluation)
non-determinism to average over -- neither of which Legacy-Bench verifier
containers provision, and the latter is meaningless against a deterministic
oracle. We substitute a parameter-free scorer that derives the continuous,
per-criterion signal from the structured pytest oracle itself. The
decomposition, granularity, and explanation -- the paper's actual contribution
-- are preserved at full fidelity; only the LLM logit backend (and the
repeated-evaluation axis, N/A here) is swapped out.

Output
------
The result is written to ``/logs/verifier/score.json`` alongside the binary
``/logs/verifier/reward.txt`` that ``test.sh`` already produces. The
deterministic oracle is untouched and remains the source of ground truth.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import re
from typing import Optional


@dataclasses.dataclass
class Criterion:
    """One scored requirement, derived from a ``test_*`` function."""

    name: str
    description: str
    weight: float = 1.0


@dataclasses.dataclass
class Outcome:
    """Observed result for a criterion (name matches a Criterion)."""

    name: str
    passed: Optional[bool]  # None == not evaluated / skipped
    message: Optional[str] = None


@dataclasses.dataclass
class CriterionResult:
    name: str
    description: str
    weight: float
    passed: Optional[bool]
    explanation: Optional[str]


@dataclasses.dataclass
class VerifierReport:
    score: float  # continuous in [0, 1]
    binary: int  # 1 iff every evaluated criterion passed (mirrors reward.txt)
    n_passed: int
    n_total: int
    n_evaluated: int
    summary: str
    criteria: list  # list[CriterionResult]


_REQUIREMENT_RE = re.compile(r"Task requirement:\s*(.+)", re.IGNORECASE)


def _docstring_to_description(doc):
    """Prefer the 'Task requirement:' line; fall back to the summary line."""
    if not doc:
        return ""
    text = doc.strip()
    match = _REQUIREMENT_RE.search(text)
    if match:
        return match.group(1).strip().rstrip(".")
    first_line = text.splitlines()[0].strip() if text else ""
    return first_line.rstrip(".")


def _humanize(name):
    body = name[len("test_"):] if name.startswith("test_") else name
    return body.replace("_", " ").strip().capitalize()


def extract_criteria(test_path):
    """Parse ``test_outputs.py`` and return one :class:`Criterion` per test_* fn."""
    with open(test_path, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=test_path)
    criteria = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node)
            description = _docstring_to_description(doc) or _humanize(node.name)
            criteria.append(Criterion(name=node.name, description=description))
    return criteria


def _clean_message(message):
    """Pull the most informative line from a pytest longrepr string."""
    if not message:
        return ""
    lines = [line.strip() for line in str(message).splitlines() if line.strip()]
    if not lines:
        return ""
    chosen = lines[-1]
    for needle in ("AssertionError", "assert ", "Error:"):
        hit = next((line for line in lines if needle in line), None)
        if hit is not None:
            chosen = hit
            break
    # drop pytest's traceback marker ("E" + spaces) if present
    chosen = re.sub(r"^E\s+", "", chosen).strip()
    return chosen


def _explain(criterion, passed, message):
    if passed is True:
        return None
    parts = []
    if criterion.description:
        parts.append("Requirement: " + criterion.description + ".")
    if passed is False and message:
        cleaned = _clean_message(message)
        if cleaned:
            parts.append("Failure: " + cleaned + ".")
        else:
            parts.append("Requirement not met.")
    elif passed is None:
        parts.append("Not evaluated (test did not run).")
    else:
        parts.append("Requirement not met.")
    return " ".join(parts)


def _summary(score, n_passed, n_evaluated, n_total):
    if n_total == 0:
        return "No criteria found."
    if n_evaluated == 0:
        return "0 of {} criteria evaluated.".format(n_total)
    return "{}/{} evaluated criteria passed (score {:.3f}, {} total).".format(
        n_passed, n_evaluated, score, n_total
    )


def build_report(criteria, outcomes):
    """Merge criterion metadata with observed outcomes into a :class:`VerifierReport`.

    ``outcomes`` is either a ``dict`` mapping criterion name to
    ``(passed, message)`` or an iterable of :class:`Outcome`-like objects
    exposing ``.name``, ``.passed`` and (optionally) ``.message``.
    """
    if isinstance(outcomes, dict):
        outcome_map = dict(outcomes)
    else:
        outcome_map = {}
        for outcome in outcomes:
            outcome_map[outcome.name] = (
                outcome.passed,
                getattr(outcome, "message", None),
            )

    results = []
    n_passed = 0
    n_evaluated = 0
    weight_passed = 0.0
    weight_evaluated = 0.0
    for criterion in criteria:
        passed, message = outcome_map.get(criterion.name, (None, None))
        results.append(
            CriterionResult(
                name=criterion.name,
                description=criterion.description,
                weight=criterion.weight,
                passed=passed,
                explanation=_explain(criterion, passed, message),
            )
        )
        if passed is None:
            continue
        n_evaluated += 1
        weight_evaluated += criterion.weight
        if passed:
            n_passed += 1
            weight_passed += criterion.weight

    if weight_evaluated > 0:
        score = weight_passed / weight_evaluated
    else:
        score = 0.0

    binary = 1 if (n_evaluated > 0 and n_passed == n_evaluated) else 0
    return VerifierReport(
        score=score,
        binary=binary,
        n_passed=n_passed,
        n_total=len(criteria),
        n_evaluated=n_evaluated,
        summary=_summary(score, n_passed, n_evaluated, len(criteria)),
        criteria=results,
    )


def write_report(report, path):
    """Serialize a :class:`VerifierReport` to ``path`` as ``score.json``."""
    payload = {
        "score": round(report.score, 6),
        "binary_reward": report.binary,
        "n_passed": report.n_passed,
        "n_total": report.n_total,
        "n_evaluated": report.n_evaluated,
        "summary": report.summary,
        "criteria": [dataclasses.asdict(item) for item in report.criteria],
    }
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path


def score_file(test_path, outcomes, out_path):
    """End-to-end: parse criteria, score against ``outcomes``, write ``out_path``."""
    criteria = extract_criteria(test_path)
    report = build_report(criteria, outcomes)
    write_report(report, out_path)
    return report
