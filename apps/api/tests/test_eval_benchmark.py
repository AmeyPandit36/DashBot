"""AI evaluation benchmark: 55 real retail questions, executed end to end.

The benchmark scores routing, SQL evidence, verification and keyword grounding.
It is intentionally strict: the transport of every answer is checked against the
dataset contract, and the run fails if the suite regresses below the threshold.
"""
from __future__ import annotations

import json
import time

import pytest

from tests.eval_questions import EVAL_QUESTIONS
from tests.conftest import register

THRESHOLD = 0.92


@pytest.fixture(scope="module")
def benchmark(seeded):
    account = seeded["account"]
    dataset_id = seeded["dataset"]["id"]
    results = []
    started = time.time()
    for case in EVAL_QUESTIONS:
        response = account.post(
            "/chat",
            json={"workspace_id": account.workspace_id, "dataset_id": dataset_id, "question": case["q"]},
        )
        assert response.status_code == 200, f"{case['q']} -> {response.status_code} {response.text[:300]}"
        payload = response.json()["data"]
        answer = payload["answer"] or ""
        failures = []
        if payload["route"] not in case["routes"]:
            failures.append(f"route {payload['route']} not in {case['routes']}")
        if not answer.strip():
            failures.append("empty answer")
        if case.get("requires_sql") and payload["route"] != "clarify" and not payload["evidence"]:
            failures.append("no SQL evidence")
        if case.get("requires_sql") and payload["route"] != "clarify" and payload["result"] is None:
            failures.append("no result set")
        status = (payload.get("verification") or {}).get("status")
        if status not in case["verification"]:
            failures.append(f"verification {status} not in {case['verification']}")
        for keyword in case.get("keywords", []):
            if keyword.lower() not in answer.lower():
                failures.append(f"missing keyword '{keyword}'")
        for forbidden in case.get("forbidden", []):
            if forbidden in answer:
                failures.append(f"leaked forbidden token '{forbidden}'")
        results.append({"question": case["q"], "route": payload["route"], "status": status, "failures": failures})
    elapsed = time.time() - started
    passed = [r for r in results if not r["failures"]]
    summary = {
        "total": len(results),
        "passed": len(passed),
        "accuracy": len(passed) / len(results),
        "elapsed_seconds": round(elapsed, 2),
        "routes": {},
        "failures": [r for r in results if r["failures"]],
    }
    for result in results:
        summary["routes"][result["route"]] = summary["routes"].get(result["route"], 0) + 1
    print("\n=== AI EVAL BENCHMARK ===")
    print(json.dumps(summary, indent=2))
    return summary


def test_benchmark_has_at_least_50_questions():
    assert len(EVAL_QUESTIONS) >= 50


def test_benchmark_accuracy(benchmark):
    assert benchmark["accuracy"] >= THRESHOLD, json.dumps(benchmark["failures"], indent=2)


def test_every_answer_is_routed(benchmark):
    assert benchmark["routes"].keys() <= {"sql", "rag", "hybrid", "metadata", "clarify"}
    assert benchmark["routes"].get("sql", 0) >= 20


def test_benchmark_latency_is_reasonable(benchmark):
    per_question = benchmark["elapsed_seconds"] / benchmark["total"]
    assert per_question < 3.0
