"""Upload, profiling, cleaning and preview behaviour."""
from __future__ import annotations

import io
import json

import pytest

from app.analytics.retail import retail_csv_bytes
from tests.conftest import load_demo, wait_for_job


def _upload(account, filename: str, data: bytes, *, sheet_name: str | None = None, name: str | None = None):
    files = {"file": (filename, data, "text/csv")}
    form = {"workspace_id": account.workspace_id}
    if sheet_name:
        form["sheet_name"] = sheet_name
    if name:
        form["name"] = name
    return account.client.post("/api/v1/datasets/upload", files=files, data=form, headers=account.headers)


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    orders = workbook.active
    orders.title = "orders"
    orders.append(["order_id", "order_date", "region", "quantity", "unit_price", "total_amount"])
    for index in range(1, 61):
        orders.append([f"O-{index:04d}", f"2026-0{(index % 9) + 1}-15", ["North", "South", "East"][index % 3], index % 5 + 1, 10.5, (index % 5 + 1) * 10.5])
    notes = workbook.create_sheet("notes")
    notes.append(["note"])
    notes.append(["Synthetic sheet used in tests"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_csv_upload_profiles_and_registers_versions(account):
    response = _upload(account, "retail_sales.csv", retail_csv_bytes(), name="Retail CSV")
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    job = wait_for_job(account, payload["job_id"])
    assert job["status"] == "completed", job
    result = job["result"]
    assert result["row_count"] == 9266
    assert result["column_count"] == 12
    assert 0 < result["quality_score"] <= 100

    dataset = account.get(f"/datasets/{payload['dataset_id']}").json()["data"]
    assert dataset["status"] in ("needs_review", "ready")
    assert dataset["active_version"] == 1
    assert dataset["semantic_status"] == "proposed"
    profile = dataset["active_version_detail"]["profile"]
    assert profile["quality_score"] == result["quality_score"]
    assert {column["name"] for column in profile["columns"]} >= {"order_id", "region", "total_amount"}
    assert profile["quality_formula"]["expression"]
    assert profile["recommendations"]

    schema = account.get(f"/datasets/{payload['dataset_id']}/schema").json()["data"]
    assert schema["table_name"].startswith("ds_")
    assert len(schema["columns"]) == 12

    preview = account.get(f"/datasets/{payload['dataset_id']}/preview?limit=5").json()["data"]
    assert preview["row_count"] == 5
    assert preview["columns"]


def test_quality_score_matches_documented_formula(account):
    payload = _upload(account, "retail.csv", retail_csv_bytes()).json()["data"]
    job = wait_for_job(account, payload["job_id"])
    profile = account.get(f"/datasets/{payload['dataset_id']}/profile").json()["data"]["profile"]
    components = profile["quality_components"]
    expected = 100 * (
        0.35 * components["completeness"]
        + 0.15 * components["uniqueness"]
        + 0.20 * components["validity"]
        + 0.15 * components["consistency"]
        + 0.15 * components["outlier_control"]
    )
    assert abs(expected - profile["quality_score"]) < 0.11
    assert profile["row_count"] == 9266


def test_excel_sheet_selection_and_inspect(account):
    data = _xlsx_bytes()
    inspect = account.client.post(
        "/api/v1/datasets/inspect", files={"file": ("book.xlsx", data)}, headers=account.headers
    )
    assert inspect.status_code == 200, inspect.text
    sheets = inspect.json()["data"]["sheets"]
    assert sheets == ["orders", "notes"]

    response = _upload(account, "book.xlsx", data, sheet_name="orders")
    assert response.status_code == 200, response.text
    job = wait_for_job(account, response.json()["data"]["job_id"])
    assert job["status"] == "completed", job
    assert job["result"]["row_count"] == 60

    dataset = account.get(f"/datasets/{response.json()['data']['dataset_id']}").json()["data"]
    assert dataset["active_version_detail"]["sheet_name"] == "orders"


def test_upload_validation(account):
    bad_extension = _upload(account, "notes.txt", b"hello")
    assert bad_extension.status_code == 415
    assert bad_extension.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    empty = _upload(account, "empty.csv", b"")
    assert empty.status_code in (400, 422)

    # formula-looking cells are data, never executed
    tricky = b"region,total_amount\n=cmd|' /C calc'!A0,10\nNorth,20\n"
    response = _upload(account, "tricky.csv", tricky)
    assert response.status_code == 200
    job = wait_for_job(account, response.json()["data"]["job_id"])
    assert job["status"] == "completed"
    dataset_id = response.json()["data"]["dataset_id"]
    preview = account.get(f"/datasets/{dataset_id}/preview?limit=5").json()["data"]
    assert "cmd" in json.dumps(preview["rows"])


def test_cleaning_creates_new_version(account):
    payload = _upload(account, "retail.csv", retail_csv_bytes()).json()["data"]
    wait_for_job(account, payload["job_id"])
    dataset_id = payload["dataset_id"]

    response = account.post(
        f"/datasets/{dataset_id}/clean",
        json={"operations": ["trim_whitespace", "drop_duplicates"]},
    )
    assert response.status_code == 200, response.text
    job = wait_for_job(account, response.json()["data"]["job_id"])
    assert job["status"] == "completed", job

    dataset = account.get(f"/datasets/{dataset_id}").json()["data"]
    assert dataset["active_version"] == 2
    assert dataset["version_count"] == 2
    versions = account.get(f"/datasets/{dataset_id}/versions").json()["data"]
    assert versions[0]["version_number"] in (1, 2)
    applied = dataset["active_version_detail"]["applied_transformations"]
    assert applied
    assert applied[-1]["rows_after"] <= applied[-1]["rows_before"]


def test_values_endpoint_is_validated(account):
    dataset = load_demo(account)
    dataset_id = dataset["dataset_id"]
    response = account.get(f"/datasets/{dataset_id}/values?field=region")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert set(payload["values"]) == {"North", "South", "East", "West"}

    unknown = account.get(f"/datasets/{dataset_id}/values?field=password")
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "UNKNOWN_DIMENSION"


def test_dataset_delete_removes_versions(account):
    payload = _upload(account, "small.csv", b"a,b\n1,2\n3,4\n").json()["data"]
    wait_for_job(account, payload["job_id"])
    assert account.delete(f"/datasets/{payload['dataset_id']}").status_code == 200
    assert account.get(f"/datasets/{payload['dataset_id']}").status_code == 404


def test_failed_job_is_recorded_and_retryable(account):
    """A job whose payload cannot be processed must fail cleanly, not hang."""
    from app.db.session import SessionLocal
    from app.models import Dataset, Job
    from app.workers.tasks import run_job

    created = _upload(account, "retail.csv", retail_csv_bytes()).json()["data"]
    wait_for_job(account, created["job_id"])

    db = SessionLocal()
    try:
        dataset = db.get(Dataset, created["dataset_id"])
        job = Job(
            workspace_id=account.workspace_id,
            job_type="ingest_dataset",
            status="queued",
            progress=0,
            created_by=account.user_id,
            payload={"dataset_id": dataset.id, "version": 999, "storage_key": "missing.parquet", "sheet_name": None},
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    result = run_job(job_id)
    assert result["ok"] is False
    detail = account.get(f"/jobs/{job_id}").json()["data"]
    assert detail["status"] == "failed"
    assert detail["error"]
    assert detail["attempts"] == 1

    retried = account.post(f"/jobs/{job_id}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["status"] in ("queued", "running", "failed")
    wait_for_job(account, job_id)

    # Retries are bounded: exhaust the budget then expect a clear rejection.
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        job.attempts = 99
        job.status = "failed"
        db.commit()
    finally:
        db.close()
    exhausted = account.post(f"/jobs/{job_id}/retry")
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["code"] == "JOB_RETRY_EXHAUSTED"


def test_job_cancel_and_ownership(account):
    from app.db.session import SessionLocal
    from app.models import Job

    db = SessionLocal()
    try:
        job = Job(
            workspace_id=account.workspace_id,
            job_type="ingest_dataset",
            status="queued",
            progress=0,
            created_by=account.user_id,
            payload={},
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    cancelled = account.post(f"/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert account.post(f"/jobs/{job_id}/cancel").status_code == 409

    from tests.conftest import register

    outsider = register(account.client, organization="Jobs Outsider")
    assert outsider.get(f"/jobs/{job_id}").status_code == 404
