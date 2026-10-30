"""Shared pytest fixtures.

Every test runs against a real FastAPI app, a real SQLite database, real Parquet
files and real DuckDB queries. Nothing is mocked: the Gemini key is simply
absent (which the platform explicitly supports through its deterministic mode).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="agentic-bi-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-secret-key-not-for-production-use",
        "DATABASE_URL": f"sqlite:///{TMP_ROOT / 'test.db'}",
        "STORAGE_BACKEND": "local",
        "STORAGE_LOCAL_ROOT": str(TMP_ROOT / "storage"),
        "LLM_ENABLED": "false",
        "GEMINI_API_KEY": "",
        "COOKIE_SECURE": "false",
        "RATE_LIMIT_PER_MINUTE": "100000",
        "LOGIN_RATE_LIMIT_PER_MINUTE": "100000",
        "USE_CELERY": "false",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    yield
    engine.dispose()
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _isolated_cookie_jar(client):
    """Keep the shared TestClient from leaking sessions between tests."""
    client.cookies.clear()
    yield
    client.cookies.clear()


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


class Account:
    def __init__(self, client: TestClient, email: str, password: str, payload: dict):
        self.client = client
        self.email = email
        self.password = password
        self.payload = payload["data"]
        self.token = self.payload["token"]
        self.user_id = self.payload["user"]["id"]
        self.organization_id = self.payload["organization"]["id"]
        self.role = self.payload["role"]
        self.workspace_id = self.payload["workspaces"][0]["id"]

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, path: str, **kwargs):
        return self.client.get(f"/api/v1{path}", headers=self.headers, **kwargs)

    def post(self, path: str, json=None, **kwargs):
        return self.client.post(f"/api/v1{path}", headers=self.headers, json=json, **kwargs)

    def put(self, path: str, json=None, **kwargs):
        return self.client.put(f"/api/v1{path}", headers=self.headers, json=json, **kwargs)

    def patch(self, path: str, json=None, **kwargs):
        return self.client.patch(f"/api/v1{path}", headers=self.headers, json=json, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.client.delete(f"/api/v1{path}", headers=self.headers, **kwargs)


def register(client: TestClient, *, name: str = "Test Analyst", organization: str | None = None) -> Account:
    email = unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "full_name": name,
            "organization_name": organization or f"Org {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text
    return Account(client, email, "StrongPass123!", response.json())


@pytest.fixture()
def account(client) -> Account:
    return register(client)


def wait_for_job(account: Account, job_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = account.get(f"/jobs/{job_id}")
        assert response.status_code == 200, response.text
        last = response.json()["data"]
        if last["status"] in ("completed", "failed", "cancelled"):
            return last
        time.sleep(0.15)
    raise AssertionError(f"Job {job_id} did not finish in time: {last}")


def load_demo(account: Account) -> dict:
    response = account.post("/datasets/demo", json={"workspace_id": account.workspace_id})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    job = wait_for_job(account, payload["job_id"])
    assert job["status"] == "completed", job
    return job["result"]


def approve_semantic(account: Account, dataset_id: str) -> dict:
    model = account.get(f"/semantic-models/dataset/{dataset_id}").json()["data"]
    response = account.post(f"/semantic-models/{model['id']}/approve", json={"approved": True})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture(scope="module")
def seeded(client):
    """A demo dataset with an approved semantic model and a generated dashboard."""
    account = register(client, name="Seeded Analyst", organization="Seeded Retail")
    load_demo(account)
    datasets = account.get(f"/datasets?workspace_id={account.workspace_id}").json()["data"]
    dataset = datasets[0]
    approved = approve_semantic(account, dataset["id"])
    dashboard = account.post(
        "/dashboards/generate", json={"dataset_id": dataset["id"], "mode": "automatic"}
    )
    assert dashboard.status_code == 200, dashboard.text
    return {
        "account": account,
        "dataset": dataset,
        "semantic": approved,
        "dashboard": dashboard.json()["data"],
    }
