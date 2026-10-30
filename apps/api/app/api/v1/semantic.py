"""Semantic model endpoints: generate, read, edit, approve."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, get_dataset as require_dataset, get_tenant_context, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import SemanticModel
from app.services import audit
from app.services import semantic as semantic_service

router = APIRouter(prefix="/semantic-models", tags=["semantic"])


class GenerateRequest(BaseModel):
    dataset_id: str
    regenerate: bool = False


class ApprovalRequest(BaseModel):
    approved: bool = True
    version: int | None = None


class DefinitionUpdate(BaseModel):
    definition: dict


@router.post("/generate")
def generate(
    payload: GenerateRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dataset = require_dataset(payload.dataset_id, ctx, db, minimum_role="analyst")
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version or not version.profile:
        raise AppError("DATASET_NOT_READY", "Profile the dataset before generating a semantic model.", 409)
    model = semantic_service.propose(db, dataset, version, regenerate=payload.regenerate)
    audit.record(db, action="semantic.generated", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="semantic_model", resource_id=model.id,
                 metadata={"version": model.version_number, "provider": model.generated_by})
    db.commit()
    return ok(semantic_service.serialize(model))


@router.get("/dataset/{dataset_id}")
def get_for_dataset(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    require_dataset(dataset_id, ctx, db)
    model = semantic_service.latest_model(db, dataset_id)
    if not model:
        raise AppError("SEMANTIC_NOT_FOUND", "No semantic model has been generated for this dataset.", 404)
    return ok(semantic_service.serialize(model))


@router.get("/{model_id}")
def get_model(model_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    model = db.get(SemanticModel, model_id)
    if not model:
        raise AppError("SEMANTIC_NOT_FOUND", "Semantic model not found.", 404)
    require_dataset(model.dataset_id, ctx, db)
    return ok(semantic_service.serialize(model))


@router.put("/{model_id}")
def update_model(
    model_id: str,
    payload: DefinitionUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    model = db.get(SemanticModel, model_id)
    if not model:
        raise AppError("SEMANTIC_NOT_FOUND", "Semantic model not found.", 404)
    dataset = require_dataset(model.dataset_id, ctx, db, minimum_role="analyst")
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    profile = (version.profile if version else {}) or {}
    columns = profile.get("columns", [])
    model, report = semantic_service.update_definition(
        db,
        model,
        payload.definition,
        available_columns={c["name"] for c in columns},
        available_types={c["name"]: c["inferred_type"] for c in columns},
    )
    audit.record(db, action="semantic.edited", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="semantic_model", resource_id=model.id,
                 metadata={"version": model.version_number})
    db.commit()
    return ok({**semantic_service.serialize(model), "validation": report})


@router.post("/{model_id}/approve")
def approve(
    model_id: str,
    payload: ApprovalRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    model = db.get(SemanticModel, model_id)
    if not model:
        raise AppError("SEMANTIC_NOT_FOUND", "Semantic model not found.", 404)
    dataset = require_dataset(model.dataset_id, ctx, db, minimum_role="analyst")
    if not payload.approved:
        model.status = "rejected"
        db.commit()
        return ok(semantic_service.serialize(model))
    if payload.version is not None and payload.version != model.version_number:
        raise AppError("VERSION_CONFLICT", "This model was updated elsewhere. Reload and review the latest version.", 409)
    model = semantic_service.approve(db, model, ctx.user.id, ctx.organization.id)
    from app.services.dashboards import generate as generate_dashboard

    dashboard = None
    try:
        dashboard_obj, _, _ = generate_dashboard(db, dataset=dataset, model=model, user=ctx.user, mode="review")
        dashboard = {"id": dashboard_obj.id, "title": dashboard_obj.title, "status": dashboard_obj.status}
    except AppError:
        dashboard = None
    audit.record(db, action="semantic.approved", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="semantic_model", resource_id=model.id,
                 metadata={"version": model.version_number})
    db.commit()
    return ok({**semantic_service.serialize(model), "dashboard_draft": dashboard})
