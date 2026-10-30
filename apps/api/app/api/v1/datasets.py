"""Dataset upload, inspection, profiling and versioning endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.ingestion import list_excel_sheets, validate_upload
from app.analytics.retail import DATASET_CONTRACT, retail_csv_bytes
from app.core.deps import TenantContext, get_dataset as require_dataset, get_tenant_context, get_workspace, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Dashboard, Dataset, DatasetVersion, SemanticModel
from app.services import audit
from app.services import datasets as dataset_service
from app.services import semantic as semantic_service

router = APIRouter(prefix="/datasets", tags=["datasets"])
MAX_BYTES = 50 * 1024 * 1024


class CleanRequest(BaseModel):
    operations: list[str]
    sheet_name: str | None = None


class DemoRequest(BaseModel):
    workspace_id: str
    name: str | None = None


@router.post("/inspect")
async def inspect_file(file: UploadFile = File(...), ctx: TenantContext = Depends(get_tenant_context)):
    data = await file.read()
    validate_upload(file.filename or "upload.csv", data)
    ext = (file.filename or "").lower().rsplit(".", 1)[-1]
    sheets = list_excel_sheets(data) if ext in ("xlsx", "xlsm") else []
    return ok({
        "file_name": file.filename,
        "size_bytes": len(data),
        "kind": "excel" if sheets else "csv",
        "sheets": sheets,
        "suggested_name": (file.filename or "dataset").rsplit(".", 1)[0].replace("_", " ").strip(),
    })


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    sheet_name: str | None = Form(default=None),
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    workspace = get_workspace(workspace_id, ctx, db, minimum_role="analyst")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise AppError("FILE_TOO_LARGE", "Files must be smaller than 50 MB.", 413)
    dataset, job = dataset_service.create_dataset(
        db,
        workspace=workspace,
        user=ctx.user,
        filename=file.filename or "dataset.csv",
        data=data,
        sheet_name=sheet_name,
        name=name,
        description=description,
    )
    audit.record(db, action="dataset.uploaded", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=workspace.id, resource_type="dataset", resource_id=dataset.id,
                 metadata={"file_name": file.filename, "size_bytes": len(data)})
    db.commit()
    return ok({"dataset_id": dataset.id, "job_id": job.id, "status": "queued"})


@router.post("/demo")
def create_demo_dataset(
    payload: DemoRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    workspace = get_workspace(payload.workspace_id, ctx, db, minimum_role="analyst")
    data = retail_csv_bytes()
    dataset, job = dataset_service.create_dataset(
        db,
        workspace=workspace,
        user=ctx.user,
        filename="retail_sales_synthetic.csv",
        data=data,
        name=payload.name or "Retail Sales (synthetic demo)",
        description="Deterministic synthetic retail dataset generated for demonstration. Not real business results.",
        is_synthetic=True,
    )
    audit.record(db, action="dataset.demo_created", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=workspace.id, resource_type="dataset", resource_id=dataset.id,
                 metadata={"synthetic": True})
    db.commit()
    return ok({
        "dataset_id": dataset.id,
        "job_id": job.id,
        "status": "queued",
        "synthetic": True,
        "contract": DATASET_CONTRACT,
    })


@router.get("")
def list_datasets(
    workspace_id: str = Query(...),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    get_workspace(workspace_id, ctx, db)
    datasets = db.scalars(
        select(Dataset).where(Dataset.workspace_id == workspace_id).order_by(Dataset.created_at.desc())
    ).all()
    payload = []
    for dataset in datasets:
        latest = semantic_service.latest_model(db, dataset.id)
        payload.append(dataset_service.serialize_dataset(dataset, latest))
    return ok(payload)


@router.get("/{dataset_id}")
def dataset_detail(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db)
    latest = semantic_service.latest_model(db, dataset.id)
    dashboards = db.scalars(
        select(Dashboard).where(Dashboard.dataset_id == dataset.id).order_by(Dashboard.updated_at.desc())
    ).all()
    return ok({
        **dataset_service.serialize_dataset(dataset, latest, include_profile=True),
        "dashboards": [
            {"id": d.id, "title": d.title, "status": d.status, "version": len(d.versions)}
            for d in dashboards
        ],
    })


@router.get("/{dataset_id}/profile")
def dataset_profile(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db)
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version or not version.profile:
        raise AppError("PROFILE_NOT_READY", "The profile is not available yet.", 409)
    return ok({
        "dataset_id": dataset.id,
        "version": version.version_number,
        "profile": version.profile,
        "cleaning_plan": version.cleaning_plan,
        "applied_transformations": version.applied_transformations,
    })


@router.get("/{dataset_id}/schema")
def dataset_schema(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db)
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version:
        raise AppError("DATASET_NOT_READY", "Dataset has no active version.", 409)
    columns = version.profile.get("columns", []) if version.profile else []
    return ok({
        "dataset_id": dataset.id,
        "version": version.version_number,
        "table_name": version.table_name,
        "columns": [
            {"name": c["name"], "type": c["inferred_type"], "nullable": c["null_count"] > 0,
             "unique_count": c["unique_count"], "null_pct": c["null_pct"]}
            for c in columns
        ],
    })


@router.get("/{dataset_id}/preview")
def dataset_preview(
    dataset_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    version: int | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dataset = require_dataset(dataset_id, ctx, db)
    version_number = version or dataset.active_version
    target = next((v for v in dataset.versions if v.version_number == version_number), None)
    if not target:
        raise AppError("VERSION_NOT_FOUND", "Dataset version not found.", 404)
    return ok(dataset_service.preview_version(target, limit=limit))


@router.get("/{dataset_id}/values")
def dimension_values(
    dataset_id: str,
    field: str = Query(..., description="Semantic dimension or time-dimension name"),
    limit: int = Query(default=60, ge=1, le=300),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Distinct values for a filter control. Executed through the SQL policy layer."""
    from app.agents.tools import load_context
    from app.sql.builder import quote

    dataset = require_dataset(dataset_id, ctx, db)
    tool_ctx = load_context(
        db,
        organization_id=ctx.organization.id,
        workspace_id=dataset.workspace_id,
        user_id=ctx.user.id,
        dataset_id=dataset.id,
    )
    semantic = tool_ctx.semantic
    match = next((d for d in semantic.get("dimensions", []) if d["name"] == field), None)
    time_match = next((t for t in semantic.get("time_dimensions", []) if t["name"] == field), None)
    if not match and not time_match:
        raise AppError("UNKNOWN_DIMENSION", "That field is not part of the semantic model.", 422)
    column = quote((match or time_match)["source_column"])
    table = quote(tool_ctx.version.table_name)
    result = tool_ctx.engine.execute(
        f"SELECT DISTINCT {column} AS value FROM {table} WHERE {column} IS NOT NULL "
        f"ORDER BY {column} LIMIT {int(limit)}"
    )
    return ok({
        "field": field,
        "values": [row[0] for row in result["rows"]],
        "row_count": result["row_count"],
    })


@router.get("/{dataset_id}/versions")
def dataset_versions(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db)
    return ok([
        dataset_service.serialize_version(v) for v in sorted(dataset.versions, key=lambda v: v.version_number, reverse=True)
    ])


@router.post("/{dataset_id}/clean")
def clean_dataset(
    dataset_id: str,
    payload: CleanRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    dataset = require_dataset(dataset_id, ctx, db, minimum_role="analyst")
    version, job = dataset_service.reprocess_with_cleaning(
        db, dataset=dataset, user=ctx.user, operations=payload.operations, sheet_name=payload.sheet_name
    )
    audit.record(db, action="dataset.cleaned", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="dataset", resource_id=dataset.id,
                 metadata={"operations": payload.operations, "new_version": version.version_number})
    return ok({
        "dataset_id": dataset.id,
        "version": dataset_service.serialize_version(version, include_profile=True),
        "job_id": job.id,
    })


@router.post("/{dataset_id}/reprocess")
def reprocess_dataset(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db, minimum_role="analyst")
    latest_semantic = semantic_service.latest_model(db, dataset.id)
    if not latest_semantic:
        raise AppError("SEMANTIC_NOT_FOUND", "No semantic model exists for this dataset.", 409)
    version = next((v for v in dataset.versions if v.version_number == dataset.active_version), None)
    if not version:
        raise AppError("DATASET_NOT_READY", "Dataset has no active version.", 409)
    model = semantic_service.propose(db, dataset, version, regenerate=True)
    audit.record(db, action="dataset.reprocessed", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="dataset", resource_id=dataset.id)
    db.commit()
    return ok({"semantic_model": semantic_service.serialize(model)})


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    dataset = require_dataset(dataset_id, ctx, db, minimum_role="admin")
    audit.record(db, action="dataset.deleted", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=dataset.workspace_id, resource_type="dataset", resource_id=dataset.id,
                 metadata={"name": dataset.name})
    db.delete(dataset)
    db.commit()
    return ok({"deleted": True})
