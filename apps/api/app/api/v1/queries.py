"""SQL validation and execution (restricted, authenticated, logged)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.tools import load_context
from app.core.deps import TenantContext, get_dataset as require_dataset, get_tenant_context, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Dataset, QueryLog, Workspace
from app.services import audit
from app.sql.validator import validate_sql

router = APIRouter(prefix="/queries", tags=["queries"])


class ValidateRequest(BaseModel):
    dataset_id: str
    sql: str = Field(min_length=1, max_length=20000)


class ExecuteRequest(BaseModel):
    dataset_id: str
    sql: str = Field(min_length=1, max_length=20000)
    limit: int = Field(default=200, ge=1, le=2000)


@router.post("/validate")
def validate(payload: ValidateRequest, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(payload.dataset_id, ctx, db)
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version:
        raise AppError("DATASET_NOT_READY", "Dataset has no active version.", 409)
    profile = version.profile or {}
    result = validate_sql(
        payload.sql,
        allowed_tables={version.table_name},
        allowed_columns={c["name"] for c in profile.get("columns", [])},
    )
    return ok({
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "tables": result.tables,
        "normalised_sql": result.sql,
    })


@router.post("/execute")
def execute(payload: ExecuteRequest, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(payload.dataset_id, ctx, db, minimum_role="analyst")
    tool_ctx = load_context(
        db,
        organization_id=ctx.organization.id,
        workspace_id=dataset.workspace_id,
        user_id=ctx.user.id,
        dataset_id=payload.dataset_id,
    )
    result = validate_sql(
        payload.sql,
        allowed_tables={tool_ctx.version.table_name},
        allowed_columns={c["name"] for c in tool_ctx.profile.get("columns", [])},
    )
    if not result.valid:
        raise AppError("SQL_REJECTED", "Query failed read-only policy validation.", 422, {"errors": result.errors})
    execution = tool_ctx.engine.execute(result.sql, limit=payload.limit)
    log = QueryLog(
        workspace_id=tool_ctx.dataset.workspace_id,
        dataset_id=payload.dataset_id,
        dataset_version_id=tool_ctx.version.id,
        user_id=ctx.user.id,
        sql_text=result.sql,
        execution_status="success",
        row_count=execution["row_count"],
        duration_ms=execution["duration_ms"],
        result_preview={"columns": execution["columns"], "rows": execution["rows"][:20]},
        provenance={"dataset_version": tool_ctx.version.version_number, "source": "manual_query"},
    )
    db.add(log)
    db.flush()
    audit.record(db, action="query.executed", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=tool_ctx.dataset.workspace_id, resource_type="query", resource_id=log.id,
                 metadata={"row_count": execution["row_count"]})
    db.commit()
    return ok({**execution, "query_id": log.id, "sql": result.sql})


@router.get("/{query_id}")
def query_detail(query_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    log = db.get(QueryLog, query_id)
    if not log:
        raise AppError("QUERY_NOT_FOUND", "Query not found.", 404)
    workspace = db.get(Workspace, log.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("QUERY_NOT_FOUND", "Query not found.", 404)
    return ok({
        "id": log.id,
        "question": log.question,
        "sql": log.sql_text,
        "status": log.execution_status,
        "row_count": log.row_count,
        "duration_ms": log.duration_ms,
        "verification": log.verification,
        "provenance": log.provenance,
        "result_preview": log.result_preview,
        "created_at": log.created_at.isoformat(),
    })


@router.get("/{query_id}/sql")
def query_sql(query_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    detail = query_detail(query_id, ctx, db)
    return ok({"query_id": query_id, "sql": detail["data"]["sql"], "provenance": detail["data"]["provenance"]})
