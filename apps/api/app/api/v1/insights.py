"""Insight list and generation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, get_dataset as require_dataset, get_tenant_context, get_workspace, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Insight
from app.services import audit
from app.services.insights import refresh_dataset_insights, serialize_insight

router = APIRouter(prefix="/insights", tags=["insights"])


class GenerateRequest(BaseModel):
    dataset_id: str


@router.get("")
def list_insights(
    workspace_id: str,
    dataset_id: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    get_workspace(workspace_id, ctx, db)
    query = select(Insight).where(Insight.workspace_id == workspace_id)
    if dataset_id:
        query = query.where(Insight.dataset_id == dataset_id)
    insights = db.scalars(query.order_by(Insight.created_at.desc()).limit(60)).all()
    return ok([serialize_insight(i) for i in insights])


@router.post("/generate")
def generate_insights(
    payload: GenerateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dataset = require_dataset(payload.dataset_id, ctx, db, minimum_role="analyst")
    if not dataset.versions:
        raise AppError("DATASET_NOT_READY", "Dataset has no processed version.", 409)
    insights = refresh_dataset_insights(
        db,
        organization_id=ctx.organization.id,
        workspace_id=dataset.workspace_id,
        user_id=ctx.user.id,
        dataset_id=dataset.id,
    )
    audit.record(db, action="insights.generated", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="dataset", resource_id=dataset.id,
                 metadata={"count": len(insights)})
    return ok([serialize_insight(i) for i in insights])
