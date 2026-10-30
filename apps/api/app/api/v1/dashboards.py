"""Dashboard generation, versioning, publishing and trusted widget data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, get_dataset as require_dataset, get_tenant_context, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Dashboard, SemanticModel, Workspace
from app.services import audit
from app.services import dashboards as dashboard_service
from app.services import semantic as semantic_service

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


class GenerateRequest(BaseModel):
    dataset_id: str
    semantic_model_id: str | None = None
    mode: str = Field(default="review", pattern="^(automatic|review)$")


class SpecUpdate(BaseModel):
    specification: dict


class WidgetDataRequest(BaseModel):
    filters: list[dict] = Field(default_factory=list, max_length=8)


def _dashboard_for_user(db: Session, dashboard_id: str, ctx: TenantContext) -> Dashboard:
    dashboard = db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise AppError("DASHBOARD_NOT_FOUND", "Dashboard not found.", 404)
    workspace = db.get(Workspace, dashboard.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("DASHBOARD_NOT_FOUND", "Dashboard not found.", 404)
    return dashboard


def _semantic_for_dataset(db: Session, dataset_id: str) -> tuple[SemanticModel | None, dict]:
    model = semantic_service.approved_model(db, dataset_id) or semantic_service.latest_model(db, dataset_id)
    return model, dict(model.definition) if model else {}


@router.post("/generate")
def generate_dashboard(
    payload: GenerateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dataset = require_dataset(payload.dataset_id, ctx, db, minimum_role="analyst")
    model = db.get(SemanticModel, payload.semantic_model_id) if payload.semantic_model_id else None
    if model is None:
        model = semantic_service.approved_model(db, dataset.id)
    if model is None or model.dataset_id != dataset.id:
        raise AppError("SEMANTIC_NOT_APPROVED", "Approve a semantic model for this dataset first.", 409)
    dashboard, version, report = dashboard_service.generate(
        db, dataset=dataset, model=model, user=ctx.user, mode=payload.mode
    )
    audit.record(db, action="dashboard.generated", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="dashboard", resource_id=dashboard.id,
                 metadata={"mode": payload.mode, "provider": report.get("provider"), "version": version.version_number})
    return ok({**dashboard_service.serialize_dashboard(db, dashboard), "generation_report": report})


@router.get("")
def list_dashboards(
    workspace_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found.", 404)
    dashboards = db.scalars(
        select(Dashboard).where(Dashboard.workspace_id == workspace_id).order_by(Dashboard.updated_at.desc())
    ).all()
    return ok([dashboard_service.serialize_dashboard(db, d, include_spec=False) for d in dashboards])


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dashboard = _dashboard_for_user(db, dashboard_id, ctx)
    _, semantic = _semantic_for_dataset(db, dashboard.dataset_id)
    return ok({**dashboard_service.serialize_dashboard(db, dashboard), "semantic": semantic})


@router.put("/{dashboard_id}")
def update_dashboard(
    dashboard_id: str,
    payload: SpecUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dashboard = _dashboard_for_user(db, dashboard_id, ctx)
    ctx.require("analyst")
    _, semantic = _semantic_for_dataset(db, dashboard.dataset_id)
    if not semantic:
        raise AppError("SEMANTIC_NOT_FOUND", "No semantic model for this dashboard's dataset.", 409)
    version = dashboard_service.update_spec(db, dashboard, payload.specification, ctx.user, semantic)
    audit.record(db, action="dashboard.updated", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dashboard.workspace_id, resource_type="dashboard", resource_id=dashboard.id,
                 metadata={"version": version.version_number})
    return ok(dashboard_service.serialize_dashboard(db, dashboard))


@router.post("/{dashboard_id}/publish")
def publish_dashboard(dashboard_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dashboard = _dashboard_for_user(db, dashboard_id, ctx)
    ctx.require("analyst")
    version = dashboard_service.publish(db, dashboard)
    audit.record(db, action="dashboard.published", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dashboard.workspace_id, resource_type="dashboard", resource_id=dashboard.id,
                 metadata={"version": version.version_number})
    return ok({"id": dashboard.id, "status": dashboard.status, "version": version.version_number})


@router.get("/{dashboard_id}/versions")
def dashboard_versions(dashboard_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dashboard = _dashboard_for_user(db, dashboard_id, ctx)
    return ok([
        {
            "id": v.id,
            "version_number": v.version_number,
            "generated_by": v.generated_by,
            "created_at": v.created_at.isoformat(),
            "widget_count": len((v.specification or {}).get("widgets", [])),
            "is_active": v.id == dashboard.active_version_id,
            "validation": v.validation_report,
        }
        for v in sorted(dashboard.versions, key=lambda v: v.version_number, reverse=True)
    ])


@router.post("/{dashboard_id}/widgets/{widget_id}/data")
def widget_data(
    dashboard_id: str,
    widget_id: str,
    payload: WidgetDataRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dashboard = _dashboard_for_user(db, dashboard_id, ctx)
    return ok(dashboard_service.widget_data(
        db,
        organization_id=ctx.organization.id,
        workspace_id=dashboard.workspace_id,
        user_id=ctx.user.id,
        dashboard=dashboard,
        widget_id=widget_id,
        runtime_filters=payload.filters,
    ))
