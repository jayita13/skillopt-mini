"""Offline tests: no API key, no network. Run with `pytest -q` (or `make test`)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import skillopt_mini as so  # noqa: E402
import tasks  # noqa: E402


@pytest.mark.parametrize("name", tasks.available())
def test_every_task_has_the_interface_and_disjoint_splits(name):
    task = tasks.load(name)
    train, val, test = task.make_splits(42)
    assert train and val and test
    inputs = [it["input"] for it in train + val + test]
    assert len(inputs) == len(set(inputs)), "splits must not overlap"
    assert task.make_splits(42) == (train, val, test), "splits must be deterministic"


def test_transactions_grading():
    t = tasks.load("transactions")
    item = {"expected": {"date": "2026-11-01", "amount": -62.35, "currency": "EUR", "category": "groceries"}}
    perfect = '```json\n{"date": "2026-11-01", "amount": -62.35, "currency": "EUR", "category": "groceries"}\n```'
    assert t.check(perfect, item) == (True, 1.0)
    wrong_sign = '{"date": "2026-11-01", "amount": 62.35, "currency": "EUR", "category": "groceries"}'
    assert t.check(wrong_sign, item) == (False, 0.75)
    assert t.check("no json here", item) == (False, 0.0)


def test_transactions_eu_number_format():
    t = tasks.load("transactions")
    assert t.eu(1234.5) == "1.234,50"
    assert t.eu(7.8) == "7,80"


def test_apply_edits_only_applies_well_formed_edits():
    skill = "# Skill\n- rule one\n"
    edits = [{"op": "append", "content": "rule two"},
             {"op": "replace", "target": "rule one", "content": "rule 1"},
             {"op": "delete", "target": "text that is not there"},
             {"op": "explode"}]
    new, applied = so.apply_edits(skill, edits)
    assert new == "# Skill\n- rule 1\n- rule two\n"
    assert len(applied) == 2


def test_learning_rate_decays_from_max_to_min():
    lrs = [so.learning_rate(s, 9) for s in range(9)]
    assert lrs[0] == so.LR_MAX and lrs[-1] == so.LR_MIN
    assert lrs == sorted(lrs, reverse=True)


def test_seconds_parses_groq_reset_headers():
    assert so._seconds("929ms") == pytest.approx(0.929)
    assert so._seconds("1m26.4s") == pytest.approx(86.4)


def test_mock_training_loop_end_to_end(tmp_path):
    out = subprocess.run([sys.executable, "skillopt_mini.py", "--task", "dates", "--mock",
                          "--epochs", "3", "--runs-dir", str(tmp_path)],
                         cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "TEST ACCURACY  0% -> 100%" in out.stdout
    assert "REJECTED" in out.stdout, "the deliberately bad mock rule must be rejected by the gate"
    (run,) = tmp_path.iterdir()
    summary = json.loads((run / "summary.json").read_text())
    assert summary["test_after"] == 1.0
