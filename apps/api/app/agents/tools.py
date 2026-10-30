"""Controlled analytical tools.

Each tool re-checks tenant ownership before returning data or executing SQL.
The LLM never receives a database handle, connection string or file path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.analytics.ingestion import frame_preview
from app.core.errors import AppError
from app.models import Dataset, DatasetVersion, SemanticModel, Workspace
from app.rag.store import retrieve_context
from app.sql.engine import DatasetEngine
from app.sql.validator import validate_sql


@dataclass
class ToolContext:
    db: Session
    organization_id: str
    workspace_id: str
    user_id: str
    dataset: Dataset
    version: DatasetVersion
    semantic: dict
    engine: DatasetEngine
    profile: dict = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)

    def _audit(self, tool: str, **meta) -> None:
        self.calls.append({"tool": tool, **meta})


def load_context(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    user_id: str,
    dataset_id: str,
) -> ToolContext:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise AppError("DATASET_NOT_FOUND", "Dataset not found.", 404)
    workspace = db.get(Workspace, dataset.workspace_id)
    if not workspace or workspace.organization_id != organization_id or workspace.id != workspace_id:
        raise AppError("DATASET_NOT_FOUND", "Dataset not found in this workspace.", 404)
    if dataset.status not in ("ready", "needs_review"):
        raise AppError("DATASET_NOT_READY", "This dataset is still being processed.", 409)

    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version or not version.parquet_file_key:
        raise AppError("DATASET_NOT_READY", "No processed dataset version is available.", 409)

    semantic_row = (
        db.query(SemanticModel)
        .filter(SemanticModel.dataset_id == dataset.id, SemanticModel.status == "approved")
        .order_by(SemanticModel.version_number.desc())
        .first()
    )
    if semantic_row:
        semantic = dict(semantic_row.definition)
    else:
        semantic_row = (
            db.query(SemanticModel)
            .filter(SemanticModel.dataset_id == dataset.id)
            .order_by(SemanticModel.version_number.desc())
            .first()
        )
        semantic = dict(semantic_row.definition) if semantic_row else {}

    from app.core.storage import storage

    path = storage.local_path(version.parquet_file_key)
    if path is None:
        raise AppError("DATASET_FILE_MISSING", "Processed dataset artefact is unavailable.", 410)
    semantic.setdefault("table_name", version.table_name)
    semantic["table_name"] = version.table_name
    semantic.setdefault("version", semantic_row.version_number if semantic_row else 1)

    return ToolContext(
        db=db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset=dataset,
        version=version,
        semantic=semantic,
        engine=DatasetEngine(path, version.table_name),
        profile=version.profile or {},
    )


# --- individual tools -------------------------------------------------------
def get_dataset_schema(ctx: ToolContext) -> list[dict]:
    schema = ctx.engine.schema()
    ctx._audit("get_dataset_schema", columns=len(schema))
    return schema


def get_semantic_model(ctx: ToolContext) -> dict:
    ctx._audit("get_semantic_model", version=ctx.semantic.get("version"))
    return ctx.semantic


def profile_dataset(ctx: ToolContext) -> dict:
    ctx._audit("profile_dataset")
    return {
        "row_count": ctx.profile.get("row_count"),
        "column_count": ctx.profile.get("column_count"),
        "quality_score": ctx.profile.get("quality_score"),
        "missing_cells": ctx.profile.get("missing_cells"),
        "duplicate_rows": ctx.profile.get("duplicate_rows"),
        "date_columns": ctx.profile.get("date_columns", []),
    }


def dataset_preview(ctx: ToolContext, limit: int = 20) -> dict:
    import polars as pl

    frame = pl.read_parquet(str(ctx.engine.parquet_path), n_rows=limit)
    ctx._audit("dataset_preview", rows=limit)
    return frame_preview(frame, limit=limit)


def validate_generated_sql(ctx: ToolContext, sql: str) -> tuple[bool, list[str], str]:
    result = validate_sql(
        sql,
        allowed_tables={ctx.version.table_name},
        allowed_columns={c["name"] for c in ctx.profile.get("columns", [])},
    )
    ctx._audit("validate_sql", valid=result.valid, errors=result.errors)
    return result.valid, result.errors, result.sql


def execute_readonly_sql(ctx: ToolContext, sql: str, params: list | None = None, limit: int | None = None) -> dict:
    valid, errors, cleaned = validate_generated_sql(ctx, sql)
    if not valid:
        raise AppError("SQL_REJECTED", "; ".join(errors), 422)
    result = ctx.engine.execute(cleaned, params=params, limit=limit)
    ctx._audit("execute_readonly_sql", rows=result["row_count"], duration_ms=result["duration_ms"])
    return result


def retrieve_business_context(ctx: ToolContext, query: str, top_k: int = 5) -> list[dict]:
    chunks = retrieve_context(
        ctx.db,
        query=query,
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        dataset_id=ctx.dataset.id,
        top_k=top_k,
    )
    ctx._audit("retrieve_business_context", chunks=len(chunks), top_score=chunks[0]["score"] if chunks else None)
    return chunks
