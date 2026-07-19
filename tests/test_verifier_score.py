"""Integration tests for the verifier scoring capability.

These exercise the scorer against the REAL existing oracle at
``tasks/2831b5-java7-rating-engine-repair/tests/test_outputs.py`` (a non-new
module in the repo) -- proving the integration decomposes that oracle's actual
criteria rather than operating on synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TASK_TESTS = REPO / "tasks" / "2831b5-java7-rating-engine-repair" / "tests"
ORACLE = TASK_TESTS / "test_outputs.py"
SCORE_MOD = TASK_TESTS / "verifier_score.py"
CONFTEST = TASK_TESTS / "conftest.py"


def _load_by_path(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_modules():
    # The task's tests/ dir must be importable so conftest's bare
    # ``import verifier_score`` resolves.
    sys.path.insert(0, str(TASK_TESTS))
    importlib.import_module("verifier_score")  # registers real name in sys.modules
    scorer = sys.modules["verifier_score"]
    conftest = _load_by_path(CONFTEST, "task_conftest_under_test")
    return scorer, conftest


def test_extracts_criteria_from_real_oracle():
    scorer, _ = _load_modules()
    criteria = scorer.extract_criteria(str(ORACLE))
    names = {c.name for c in criteria}
    assert "test_total_billable_amount" in names
    assert "test_rating_errors_zero" in names
    assert "test_output_not_hardcoded" in names
    assert len(criteria) == 7  # the seven criteria defined in this oracle

    total = next(c for c in criteria if c.name == "test_total_billable_amount")
    assert "892.67" in total.description
    assert "total_billable" in total.description.lower()


def test_continuous_score_and_failure_explanations():
    scorer, _ = _load_modules()
    criteria = scorer.extract_criteria(str(ORACLE))
    failed = {"test_total_billable_amount", "test_rating_errors_zero"}
    outcomes = {
        c.name: (
            False,
            "AssertionError: Expected total_billable Decimal('892.67'), "
            "got Decimal('127.43')",
        )
        if c.name in failed
        else (True, None)
        for c in criteria
    }
    report = scorer.build_report(criteria, outcomes)

    assert abs(report.score - 5 / 7) < 1e-9
    assert report.binary == 0
    assert report.n_passed == 5
    assert report.n_evaluated == 7
    assert report.n_total == 7

    failed_result = next(
        cr for cr in report.criteria if cr.name == "test_total_billable_amount"
    )
    assert failed_result.passed is False
    assert failed_result.explanation is not None
    # The silent binary failure is now explained: requirement AND the surfaced
    # wrong value are both present.
    assert "892.67" in failed_result.explanation
    assert "127.43" in failed_result.explanation


def test_all_pass_yields_full_score_and_binary_reward_one():
    scorer, _ = _load_modules()
    criteria = scorer.extract_criteria(str(ORACLE))
    outcomes = {c.name: (True, None) for c in criteria}
    report = scorer.build_report(criteria, outcomes)
    assert report.score == 1.0
    assert report.binary == 1  # mirrors what test.sh would write to reward.txt


def test_write_report_roundtrip(tmp_path):
    scorer, _ = _load_modules()
    criteria = scorer.extract_criteria(str(ORACLE))
    report = scorer.build_report(
        criteria, {c.name: (True, None) for c in criteria}
    )
    out = tmp_path / "score.json"
    scorer.write_report(report, str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["binary_reward"] == 1
    assert data["score"] == 1.0
    assert data["n_total"] == 7
    assert len(data["criteria"]) == 7
    assert data["criteria"][0]["name"].startswith("test_")


def test_conftest_emit_score_writes_diagnostic(tmp_path):
    # Exercises the exact wiring path that test.sh's pytest run triggers
    # (conftest.emit_score -> verifier_score.score_file).
    _, conftest = _load_modules()
    outcomes = {
        name: (False, "AssertionError: rating_errors 0 expected, got 3")
        if name == "test_rating_errors_zero"
        else (True, None)
        for name in (
            "test_settlement_report_file_exists",
            "test_total_billable_amount",
            "test_rating_errors_zero",
            "test_calls_rated_count",
            "test_call_charges_sum_to_total",
            "test_output_not_hardcoded",
            "test_with_alternative_input",
        )
    }
    out = tmp_path / "score.json"
    report = conftest.emit_score(str(ORACLE), outcomes, str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert report is not None
    assert data["n_total"] == 7
    assert data["binary_reward"] == 0
    assert data["score"] < 1.0
    failed = [c for c in data["criteria"] if c["passed"] is False]
    assert len(failed) == 1
    assert "rating_errors" in failed[0]["explanation"]
