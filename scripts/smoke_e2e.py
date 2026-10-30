"""End-to-end smoke test executed against the real application.

Run with the project virtualenv:
    python scripts/smoke_e2e.py

Exercises the complete user journey with a real SQLite database, real Polars
ingestion, real DuckDB execution and the real LangGraph workflow.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{REPO / 'apps' / 'api' / 'data' / 'smoke.db'}")
os.environ.setdefault("SECRET_KEY", "smoke-test-secret-key-not-for-production")
os.environ.setdefault("STORAGE_LOCAL_ROOT", str(REPO / "apps" / "api" / "data" / "smoke-storage"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def step(name: str) -> None:
    print(f"\n=== {name} ===")


def main() -> int:
    failures: list[str] = []
    with TestClient(app) as client:
        step("Health")
        health = client.get("/api/v1/health")
        print(health.status_code, health.json()["status"], health.json()["llm"])
        if health.status_code != 200:
            failures.append("health")

        step("Register")
        email = f"smoke-{int(time.time())}@example.com"
        response = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "AgenticBI2026!",
            "full_name": "Smoke Tester",
            "organization_name": "Smoke Retail Co",
        })
        print(response.status_code)
        if response.status_code != 200:
            print(response.text)
            return 1
        data = response.json()["data"]
        workspace_id = data["workspaces"][0]["id"]
        print("workspace:", workspace_id, "role:", data["role"])

        step("Create demo dataset")
        response = client.post("/api/v1/datasets/demo", json={"workspace_id": workspace_id})
        print(response.status_code)
        payload = response.json()["data"]
        dataset_id, job_id = payload["dataset_id"], payload["job_id"]
        print("dataset:", dataset_id, "job:", job_id)

        for _ in range(90):
            job = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
            if job["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.5)
        print("job:", job["status"], job["message"], job.get("error"))
        if job["status"] != "completed":
            failures.append(f"ingestion: {job.get('error')}")
            print(json.dumps(job, indent=2)[:2000])
            return 1

        step("Dataset profile")
        profile = client.get(f"/api/v1/datasets/{dataset_id}/profile").json()["data"]["profile"]
        print("rows:", profile["row_count"], "cols:", profile["column_count"], "score:", profile["quality_score"])
        print("formula:", profile["quality_formula"]["expression"])

        step("Semantic model")
        semantic = client.get(f"/api/v1/semantic-models/dataset/{dataset_id}").json()["data"]
        print("metrics:", [m["name"] for m in semantic["definition"]["metrics"]])
        print("dimensions:", [d["name"] for d in semantic["definition"]["dimensions"]][:8])
        approval = client.post(f"/api/v1/semantic-models/{semantic['id']}/approve", json={"approved": True})
        print("approve:", approval.status_code, approval.json()["data"]["status"])
        if approval.status_code != 200:
            failures.append("semantic approval")

        step("Generate dashboard (automatic)")
        dash = client.post("/api/v1/dashboards/generate", json={
            "dataset_id": dataset_id, "mode": "automatic"
        })
        dashboard = dash.json()["data"]
        print("status:", dash.status_code, "widgets:", len(dashboard["specification"]["widgets"]),
              "queries:", len(dashboard["specification"]["queries"]))
        dashboard_id = dashboard["id"]
        if dash.status_code != 200:
            failures.append("dashboard generation")
            print(dash.text[:2000])
            return 1

        step("Widget data (real DuckDB execution)")
        widget = dashboard["specification"]["widgets"][0]
        wd = client.post(f"/api/v1/dashboards/{dashboard_id}/widgets/{widget['id']}/data", json={"filters": []})
        print(widget["type"], widget["title"], "->", wd.status_code, wd.json()["data"]["rows"])
        if wd.status_code != 200:
            failures.append("widget data")
            print(wd.text[:1500])

        step("AI analyst questions")
        questions = [
            "What is total revenue?",
            "Which region generated the highest revenue?",
            "What are the monthly sales trends?",
            "Why did revenue decrease recently?",
            "What does average order value mean?",
            "How many unique customers do we have?",
        ]
        for question in questions:
            response = client.post("/api/v1/chat", json={
                "workspace_id": workspace_id,
                "dataset_id": dataset_id,
                "question": question,
            })
            if response.status_code != 200:
                failures.append(f"chat: {question} -> {response.status_code}")
                print("FAILED:", response.status_code, response.text[:800])
                continue
            answer = response.json()["data"]
            print(f"\nQ: {question}")
            print("A:", answer["answer"][:400].replace("\n", " "))
            print("verification:", answer["verification"]["status"],
                  "| rows:", (answer.get("result") or {}).get("row_count"),
                  "| route:", answer.get("route"))
            if answer["verification"]["status"] != "verified":
                failures.append(f"verification: {question} -> {answer['verification']}")
            if answer.get("evidence"):
                print("SQL:", answer["evidence"][0]["sql"][:180].replace("\n", " "))

        step("Conversation history")
        conv = client.get(f"/api/v1/conversations?workspace_id={workspace_id}").json()["data"]
        print("conversations:", len(conv))
        if conv:
            detail = client.get(f"/api/v1/conversations/{conv[0]['id']}").json()["data"]
            print("messages:", len(detail["messages"]))

        step("Insights")
        response = client.post("/api/v1/insights/generate", json={"dataset_id": dataset_id})
        insights = response.json()["data"]
        print("insights:", len(insights))
        for insight in insights[:4]:
            print(" -", insight["title"])
        if not insights:
            failures.append("insights empty")

        step("Tenant isolation")
        client.post("/api/v1/auth/logout")
        other = f"smoke-other-{int(time.time())}@example.com"
        client.post("/api/v1/auth/register", json={
            "email": other, "password": "AgenticBI2026!", "full_name": "Other Tenant",
        })
        cross = client.get(f"/api/v1/datasets/{dataset_id}")
        print("cross-tenant dataset access:", cross.status_code)
        if cross.status_code not in (403, 404):
            failures.append("tenant isolation")

    print("\n=== RESULT ===")
    if failures:
        print("FAILURES:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
