#!/usr/bin/env python
"""Seed a complete demo workspace through the public HTTP API.

Creates (idempotently):
  1. an organisation + owner account;
  2. the deterministic synthetic retail dataset (9,266 order lines);
  3. a proposed semantic model, reviewed and approved;
  4. a published dashboard generated from that model;
  5. verified insights and one business-context document.

Usage:
    python apps/api/scripts/seed_demo.py
    python apps/api/scripts/seed_demo.py --email demo@example.com --password '...'
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DEMO_EMAIL = "demo@agenticbi.dev"
DEMO_PASSWORD = "DemoPass123!"
DEMO_ORG = "Northwind Retail Group"


def api(client: TestClient, method: str, path: str, token: str | None = None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, f"/api/v1{path}", headers=headers, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("success") is False:
        raise SystemExit(f"{method} {path} failed ({response.status_code}): {payload}")
    return payload["data"]


def wait(client: TestClient, token: str, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = api(client, "GET", f"/jobs/{job_id}", token)
        if job["status"] in ("completed", "failed", "cancelled"):
            if job["status"] != "completed":
                raise SystemExit(f"Job {job_id} failed: {job.get('error')}")
            return job
        time.sleep(0.2)
    raise SystemExit(f"Timed out waiting for job {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Agentic BI demo workspace.")
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    parser.add_argument("--name", default="Demo Analyst")
    parser.add_argument("--organization", default=DEMO_ORG)
    args = parser.parse_args()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": args.email, "password": args.password}
        )
        if login.status_code == 200:
            print(f"✓ Account {args.email} already exists — reusing it.")
            session = login.json()["data"]
        else:
            print("→ Creating organisation, owner and workspace…")
            session = api(
                client,
                "POST",
                "/auth/register",
                json={
                    "email": args.email,
                    "password": args.password,
                    "full_name": args.name,
                    "organization_name": args.organization,
                },
            )
        token = session["token"]
        workspace_id = session["workspaces"][0]["id"]

        datasets = api(client, "GET", f"/datasets?workspace_id={workspace_id}", token)
        if datasets:
            dataset = datasets[0]
            print(f"✓ Dataset '{dataset['name']}' already present — skipping ingestion.")
        else:
            print("→ Generating the synthetic retail dataset (9,266 order lines)…")
            created = api(client, "POST", "/datasets/demo", token, json={"workspace_id": workspace_id})
            job = wait(client, token, created["job_id"])
            print(
                f"✓ Ingested {job['result']['row_count']:,} rows × {job['result']['column_count']} columns "
                f"(quality {job['result']['quality_score']}/100)"
            )
            dataset = api(client, "GET", f"/datasets/{created['dataset_id']}", token)

        dataset_id = dataset["id"]
        model = api(client, "GET", f"/semantic-models/dataset/{dataset_id}", token)
        if model["status"] != "approved":
            approved = api(client, "POST", f"/semantic-models/{model['id']}/approve", token, json={"approved": True})
            print(
                f"✓ Approved semantic model v{approved['version']} "
                f"({len(approved['definition']['metrics'])} metrics, "
                f"{len(approved['definition']['dimensions'])} dimensions)"
            )
        else:
            print("✓ Semantic model already approved.")

        dashboards = api(client, "GET", f"/dashboards?workspace_id={workspace_id}", token)
        if dashboards:
            dashboard = dashboards[0]
            print(f"✓ Dashboard '{dashboard['title']}' already exists.")
        else:
            dashboard = api(
                client, "POST", "/dashboards/generate", token,
                json={"dataset_id": dataset_id, "mode": "automatic"},
            )
            print(f"✓ Generated dashboard '{dashboard['title']}' with {dashboard['widget_count']} widgets.")

        insights = api(client, "GET", f"/insights?workspace_id={workspace_id}", token)
        if not insights:
            insights = api(client, "POST", "/insights/generate", token, json={"dataset_id": dataset_id})
            print(f"✓ Generated {len(insights)} verified insights.")

        documents = api(client, "GET", f"/documents?workspace_id={workspace_id}", token)
        if not any(doc["document_type"] == "business_note" for doc in documents):
            api(
                client, "POST", "/documents", token,
                json={
                    "workspace_id": workspace_id,
                    "dataset_id": dataset_id,
                    "title": "Commercial definitions and discount policy",
                    "document_type": "business_note",
                    "content": (
                        "Total amount is net of discount and excludes tax and refunds. "
                        "Enterprise customers receive volume discounts up to 35% in the West and South regions. "
                        "The commercial team reviews regional performance monthly and treats a quarter-on-quarter "
                        "revenue decline of more than 15% as a trigger for a pricing review."
                    ),
                },
            )
            print("✓ Indexed a business-context note for retrieval.")

        print("\nDemo workspace ready.")
        print("  URL       http://localhost:3000/login")
        print(f"  Email     {args.email}")
        print(f"  Password  {args.password}")
        print(f"  Dataset   {dataset['name']} ({dataset['row_count']:,} rows)")
        print(f"  Dashboard /app/dashboards/{dashboard['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
