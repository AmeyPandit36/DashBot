"""Platform metadata and health."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.retail import DATASET_CONTRACT
from app.core.config import settings
from app.core.deps import ok
from app.core.storage import storage
from app.db.session import get_db

router = APIRouter(tags=["meta"])
VERSION = "1.0.0"


@router.get("/meta/config")
def config():
    return ok({
        "app_name": settings.APP_NAME,
        "version": VERSION,
        "environment": settings.ENVIRONMENT,
        "currency_symbol": "₹",
        "llm": {
            "enabled": settings.llm_configured,
            "provider": "gemini" if settings.llm_configured else "deterministic",
            "model": settings.GEMINI_MODEL if settings.llm_configured else "rule-based planner",
            "note": (
                "Gemini is configured; semantic inference, SQL generation and narrative rewriting use the LLM."
                if settings.llm_configured
                else "No Gemini API key is configured. Semantic inference, SQL planning and narrative composition run "
                     "deterministically against real query results."
            ),
        },
        "uploads": {
            "supported": [".csv", ".xlsx"],
            "max_mb": settings.MAX_UPLOAD_BYTES // (1024 * 1024),
            "excel_sheets_limit": settings.MAX_EXCEL_SHEETS,
        },
        "query_limits": {
            "row_limit": settings.QUERY_ROW_LIMIT,
            "timeout_seconds": settings.QUERY_TIMEOUT_SECONDS,
            "memory_limit": settings.DUCKDB_MEMORY_LIMIT,
        },
        "storage_backend": settings.STORAGE_BACKEND,
        "demo_dataset": DATASET_CONTRACT,
        "features": {
            "automatic_dashboards": True,
            "review_mode": True,
            "cross_filtering": True,
            "rag": True,
            "sql_provenance": True,
            "insight_generation": True,
            "forecasting": False,
        },
    })


@router.get("/health")
def health(db: Session = Depends(get_db)):
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database_status = f"error: {type(exc).__name__}"
    storage_status = "ok"
    try:
        storage.put_bytes("_healthcheck/ping.txt", b"ok")
    except Exception as exc:  # noqa: BLE001
        storage_status = f"error: {type(exc).__name__}"
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "version": VERSION,
        "environment": settings.ENVIRONMENT,
        "database": database_status,
        "storage": storage_status,
        "llm": {
            "configured": settings.llm_configured,
            "provider": "gemini" if settings.llm_configured else "deterministic",
        },
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
