"""Job dispatch: Celery when configured, in-process worker thread otherwise.

Both paths call the same idempotent task function, so behaviour cannot diverge
between local development and production.
"""
from __future__ import annotations

import logging
import threading

from app.core.config import settings

logger = logging.getLogger("agentic_bi.jobs")


def dispatch(job_id: str, job_type: str) -> None:
    if settings.USE_CELERY and settings.CELERY_BROKER_URL:
        try:
            from app.workers.celery_app import process_job_task

            process_job_task.delay(job_id)
            logger.info("job_dispatched_celery id=%s type=%s", job_id, job_type)
            return
        except Exception as exc:  # noqa: BLE001 - fall back to local execution
            logger.warning("celery_dispatch_failed id=%s error=%s", job_id, exc)
    thread = threading.Thread(target=_run_local, args=(job_id,), daemon=True, name=f"job-{job_id[:8]}")
    thread.start()
    logger.info("job_dispatched_local id=%s type=%s", job_id, job_type)


def _run_local(job_id: str) -> None:
    from app.workers.tasks import run_job

    try:
        run_job(job_id)
    except Exception:  # noqa: BLE001 - job status already records the failure
        logger.exception("job_crashed id=%s", job_id)
