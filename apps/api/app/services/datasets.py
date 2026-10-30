"""Dataset ingestion orchestration and serialisation."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.analytics.ingestion import (
    apply_cleaning,
    checksum,
    frame_preview,
    parse_upload,
    profile_frame,
    validate_upload,
    write_parquet,
)
from app.core.config import settings
from app.core.errors import AppError
from app.core.storage import storage
from app.db.session import session_scope
from app.models import Dataset, DatasetColumn, DatasetVersion, Job, User, Workspace
from app.services import semantic as semantic_service
from app.services.jobs import dispatch

logger = logging.getLogger("agentic_bi.datasets")


def _new_table_name() -> str:
    return f"ds_{uuid.uuid4().hex[:10]}"


def _key(workspace_id: str, dataset_id: str, version: int, name: str) -> str:
    return f"workspaces/{workspace_id}/datasets/{dataset_id}/v{version}/{name}"


def create_dataset(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    filename: str,
    data: bytes,
    sheet_name: str | None = None,
    name: str | None = None,
    description: str | None = None,
    is_synthetic: bool = False,
) -> tuple[Dataset, Job]:
    validate_upload(filename, data)
    digest = checksum(data)
    dataset = Dataset(
        workspace_id=workspace.id,
        name=(name or filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip() or "Dataset")[:200],
        description=description,
        file_name=filename[:255],
        status="processing",
        is_synthetic=is_synthetic,
        created_by=user.id,
    )
    db.add(dataset)
    db.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        table_name=_new_table_name(),
        status="pending",
        sheet_name=sheet_name,
        source_checksum=digest,
    )
    db.add(version)
    db.flush()

    ext = filename.lower().rsplit(".", 1)[-1]
    original_key = _key(workspace.id, dataset.id, 1, f"original.{ext}")
    storage.put_bytes(original_key, data, content_type="text/csv" if ext == "csv" else
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    version.original_file_key = original_key

    job = Job(
        workspace_id=workspace.id,
        job_type="ingest_dataset",
        status="queued",
        payload={
            "dataset_id": dataset.id,
            "version_id": version.id,
            "sheet_name": sheet_name,
            "filename": filename,
            "is_synthetic": is_synthetic,
        },
        created_by=user.id,
        idempotency_key=f"ingest:{dataset.id}:{digest[:16]}",
        message="Queued for processing",
    )
    db.add(job)
    db.commit()

    dispatch(job.id, "ingest_dataset")
    return dataset, job


def process_ingestion_job(job_id: str, payload: dict, workspace_id: str, created_by: str | None) -> dict:
    """Run inside a worker. Idempotent per dataset version."""
    dataset_id = payload["dataset_id"]
    version_id = payload["version_id"]

    with session_scope() as db:
        dataset = db.get(Dataset, dataset_id)
        version = db.get(DatasetVersion, version_id)
        job = db.get(Job, job_id)
        if not dataset or not version:
            raise AppError("DATASET_NOT_FOUND", "Dataset disappeared before processing.", 404)
        if version.status == "ready":
            return {"dataset_id": dataset.id, "skipped": True}
        if job:
            job.progress = 20
            job.message = "Parsing file"

    original = storage.get_bytes(version.original_file_key) if version.original_file_key else None
    if original is None:
        raise AppError("FILE_MISSING", "Original upload is no longer available.", 410)

    parsed = parse_upload(payload.get("filename", "dataset.csv"), original, payload.get("sheet_name"))
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job:
            job.progress = 45
            job.message = "Profiling columns"

    profile = profile_frame(parsed.frame, parsed.coercion_issues)

    with session_scope() as db:
        job = db.get(Job, job_id)
        if job:
            job.progress = 65
            job.message = "Writing analytical artefact"

    dataset = db.get(Dataset, dataset_id)
    version = db.get(DatasetVersion, version_id)
    parquet_key = _key(dataset.workspace_id, dataset.id, version.version_number, "data.parquet")
    path = storage.local_path(parquet_key)
    if path is None:
        raise AppError("STORAGE_ERROR", "This storage backend cannot serve analytical files.", 500)
    write_parquet(parsed.frame, path)
    if settings.STORAGE_BACKEND == "s3":
        storage.put_bytes(parquet_key, path.read_bytes(), content_type="application/octet-stream")

    with session_scope() as db:
        dataset = db.get(Dataset, dataset_id)
        version = db.get(DatasetVersion, version_id)
        job = db.get(Job, job_id)

        version.status = "ready"
        version.parquet_file_key = parquet_key
        version.processed_file_key = parquet_key
        version.profile = profile
        version.cleaning_plan = profile.get("cleaning_plan", {})
        version.row_count = profile.get("row_count", 0)
        version.column_count = profile.get("column_count", 0)
        version.encoding = parsed.encoding
        version.delimiter = parsed.delimiter
        version.sheet_name = parsed.sheet_name
        version.applied_transformations = []
        db.query(DatasetColumn).filter(DatasetColumn.dataset_version_id == version.id).delete()
        for column in profile.get("columns", []):
            db.add(DatasetColumn(
                dataset_version_id=version.id,
                column_name=column["name"],
                inferred_type=column["inferred_type"],
                ordinal_position=column.get("ordinal_position", 0),
                nullable=column.get("null_count", 0) > 0,
                unique_count=column.get("unique_count", 0),
                null_count=column.get("null_count", 0),
                sample_values=column.get("sample_values", []),
                metadata_json={"stats": column.get("stats", {}), "issues": column.get("issues", [])},
            ))

        dataset.row_count = profile.get("row_count", 0)
        dataset.column_count = profile.get("column_count", 0)
        dataset.quality_score = profile.get("quality_score")
        dataset.status = "needs_review"
        db.flush()

        # Semantic inference runs immediately after profiling.
        semantic_service.propose(db, dataset, version)

        if job:
            job.progress = 90
            job.message = "Semantic model proposed"
            job.result = {
                "dataset_id": dataset.id,
                "quality_score": profile.get("quality_score"),
                "row_count": profile.get("row_count"),
                "column_count": profile.get("column_count"),
            }
    logger.info("dataset_ingested dataset=%s rows=%s", dataset_id, profile.get("row_count"))
    return {
        "dataset_id": dataset_id,
        "quality_score": profile.get("quality_score"),
        "row_count": profile.get("row_count"),
        "column_count": profile.get("column_count"),
    }


def reprocess_with_cleaning(
    db: Session, *, dataset: Dataset, user: User, operations: list[str], sheet_name: str | None = None
) -> tuple[DatasetVersion, Job]:
    """Create a new dataset version with explicitly approved cleaning operations."""
    current = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not current or not current.original_file_key:
        raise AppError("DATASET_NOT_READY", "This dataset has no processed version to clean.", 409)

    allowed = {"drop_duplicates", "trim_whitespace", "drop_all_null_rows"}
    chosen = [op for op in operations if op in allowed]
    if not chosen:
        raise AppError("NO_CLEANING_OPERATIONS", "Select at least one supported cleaning operation.", 422)

    original = storage.get_bytes(current.original_file_key)
    parsed = parse_upload(current.original_file_key, original, sheet_name or current.sheet_name)
    cleaned, applied = apply_cleaning(parsed.frame, chosen)
    profile = profile_frame(cleaned, parsed.coercion_issues)

    version_number = max(v.version_number for v in dataset.versions) + 1
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=version_number,
        table_name=_new_table_name(),
        source_checksum=current.source_checksum,
        sheet_name=parsed.sheet_name,
        status="ready",
        profile=profile,
        cleaning_plan=profile.get("cleaning_plan", {}),
        applied_transformations=applied,
        row_count=profile["row_count"],
        column_count=profile["column_count"],
        original_file_key=current.original_file_key,
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
    )
    db.add(version)
    db.flush()

    parquet_key = _key(dataset.workspace_id, dataset.id, version_number, "data.parquet")
    path = storage.local_path(parquet_key)
    write_parquet(cleaned, path)
    version.parquet_file_key = parquet_key
    version.processed_file_key = parquet_key

    for column in profile["columns"]:
        db.add(DatasetColumn(
            dataset_version_id=version.id,
            column_name=column["name"],
            inferred_type=column["inferred_type"],
            ordinal_position=column.get("ordinal_position", 0),
            nullable=column.get("null_count", 0) > 0,
            unique_count=column.get("unique_count", 0),
            null_count=column.get("null_count", 0),
            sample_values=column.get("sample_values", []),
            metadata_json={"stats": column.get("stats", {}), "issues": column.get("issues", [])},
        ))

    dataset.active_version = version_number
    dataset.row_count = profile["row_count"]
    dataset.column_count = profile["column_count"]
    dataset.quality_score = profile["quality_score"]
    dataset.status = "needs_review"

    job = Job(
        workspace_id=dataset.workspace_id,
        job_type="reprocess_dataset",
        status="completed",
        progress=100,
        message="Cleaning applied and new version created",
        payload={"dataset_id": dataset.id, "version_id": version.id, "operations": chosen},
        result={"version": version_number, "applied": applied},
        created_by=user.id,
    )
    db.add(job)
    semantic_service.propose(db, dataset, version, regenerate=True)
    db.commit()
    return version, job


def preview_version(version: DatasetVersion, limit: int = 50) -> dict:
    import polars as pl

    if not version.parquet_file_key:
        raise AppError("DATASET_NOT_READY", "The dataset has not been processed yet.", 409)
    path = storage.local_path(version.parquet_file_key)
    frame = pl.read_parquet(str(path), n_rows=max(1, min(limit, 500)))
    return frame_preview(frame, limit=limit)


def serialize_dataset(dataset: Dataset, latest_semantic=None, include_profile: bool = False) -> dict:
    active = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    return {
        "id": dataset.id,
        "workspace_id": dataset.workspace_id,
        "name": dataset.name,
        "description": dataset.description,
        "file_name": dataset.file_name,
        "source_type": dataset.source_type,
        "status": dataset.status,
        "is_synthetic": dataset.is_synthetic,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "quality_score": dataset.quality_score,
        "active_version": dataset.active_version,
        "version_count": len(dataset.versions),
        "created_at": dataset.created_at.isoformat(),
        "updated_at": dataset.updated_at.isoformat(),
        "semantic_status": latest_semantic.status if latest_semantic else None,
        "semantic_model_id": latest_semantic.id if latest_semantic else None,
        "semantic_version": latest_semantic.version_number if latest_semantic else None,
        "active_version_detail": serialize_version(active, include_profile=include_profile) if active else None,
    }


def serialize_version(version: DatasetVersion | None, include_profile: bool = False) -> dict | None:
    if version is None:
        return None
    payload = {
        "id": version.id,
        "version_number": version.version_number,
        "status": version.status,
        "row_count": version.row_count,
        "column_count": version.column_count,
        "table_name": version.table_name,
        "sheet_name": version.sheet_name,
        "encoding": version.encoding,
        "delimiter": version.delimiter,
        "applied_transformations": version.applied_transformations,
        "created_at": version.created_at.isoformat(),
        "quality_score": (version.profile or {}).get("quality_score"),
    }
    if include_profile:
        payload["profile"] = version.profile
        payload["cleaning_plan"] = version.cleaning_plan
    return payload
