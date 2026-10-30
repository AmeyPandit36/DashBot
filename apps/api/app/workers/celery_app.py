"""Celery application for background processing (production path)."""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "agentic_bi",
    broker=settings.CELERY_BROKER_URL or settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL or "redis://localhost:6379/1",
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=900,
    task_soft_time_limit=840,
)


@celery_app.task(bind=True, max_retries=settings.JOB_MAX_RETRIES, name="agentic_bi.process_job")
def process_job_task(self, job_id: str) -> dict:
    from app.workers.tasks import run_job

    try:
        return run_job(job_id)
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=10) from exc
