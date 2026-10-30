"""Idempotent background tasks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.session import session_scope
from app.models import Job

logger = logging.getLogger("agentic_bi.tasks")


def run_job(job_id: str) -> dict:
    """Entry point for both Celery and the in-process runner."""
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job_not_found"}
        if job.status in ("completed", "cancelled"):
            return {"ok": True, "skipped": "already_finished"}
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        job.progress = 5
        db.flush()
        job_type = job.job_type
        payload = dict(job.payload or {})
        workspace_id = job.workspace_id
        created_by = job.created_by

    try:
        if job_type in ("ingest_dataset", "reprocess_dataset"):
            from app.services.datasets import process_ingestion_job

            result = process_ingestion_job(job_id, payload, workspace_id, created_by)
        else:
            raise RuntimeError(f"Unsupported job type '{job_type}'")
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job and job.status != "cancelled":
                job.status = "completed"
                job.progress = 100
                job.result = result
                job.finished_at = datetime.now(timezone.utc)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("job_failed id=%s", job_id)
        with session_scope() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)[:2000]
                job.message = "Processing failed. See error details."
                job.finished_at = datetime.now(timezone.utc)
                dataset_id = (job.payload or {}).get("dataset_id")
                if dataset_id:
                    from app.models import Dataset

                    dataset = db.get(Dataset, dataset_id)
                    if dataset and dataset.status == "processing":
                        dataset.status = "failed"
        return {"ok": False, "error": str(exc)}
