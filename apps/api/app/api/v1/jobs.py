"""Background job status endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import TenantContext, get_tenant_context, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Dataset, Job, Workspace
from app.services.jobs import dispatch

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job(db: Session, job_id: str, ctx: TenantContext) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
    workspace = db.get(Workspace, job.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("JOB_NOT_FOUND", "Job not found.", 404)
    return job


@router.get("/{job_id}")
def job_status(job_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    job = _job(db, job_id, ctx)
    return ok({
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result,
        "attempts": job.attempts,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    })


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    job = _job(db, job_id, ctx)
    ctx.require("analyst")
    if job.status not in ("queued", "running"):
        raise AppError("JOB_NOT_CANCELLABLE", "Only queued or running jobs can be cancelled.", 409)
    job.status = "cancelled"
    job.finished_at = datetime.now(timezone.utc)
    job.message = "Cancelled by user"
    db.commit()
    return ok({"id": job.id, "status": job.status})


@router.post("/{job_id}/retry")
def retry_job(job_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    """Re-dispatch a failed job.

    Retries are bounded by ``JOB_MAX_RETRIES`` so a deterministic failure cannot
    loop forever. The attempt counter is preserved for observability.
    """
    job = _job(db, job_id, ctx)
    ctx.require("analyst")
    if job.status not in ("failed",):
        raise AppError("JOB_NOT_RETRYABLE", "Only failed jobs can be retried.", 409)
    if job.attempts >= settings.JOB_MAX_RETRIES + 1:
        raise AppError(
            "JOB_RETRY_EXHAUSTED",
            f"This job has already been attempted {job.attempts} times.",
            409,
        )
    dataset_id = (job.payload or {}).get("dataset_id")
    if dataset_id:
        dataset = db.get(Dataset, dataset_id)
        if dataset and dataset.status == "failed":
            dataset.status = "processing"
    job.status = "queued"
    job.error = None
    job.message = "Requeued by user"
    job.progress = 0
    job.started_at = None
    job.finished_at = None
    db.commit()
    dispatch(job.id, job.job_type)
    return ok({"id": job.id, "status": job.status, "attempts": job.attempts})
