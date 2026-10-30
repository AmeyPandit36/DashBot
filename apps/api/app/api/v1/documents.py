"""Business context documents (glossary notes) feeding tenant-scoped RAG."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, get_tenant_context, get_workspace, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Document, Workspace
from app.rag.store import index_document
from app.services import audit

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=40000)
    document_type: str = Field(default="business_note", pattern="^(business_note|glossary|policy)$")
    dataset_id: str | None = None


@router.get("")
def list_documents(workspace_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    get_workspace(workspace_id, ctx, db)
    documents = db.scalars(
        select(Document).where(Document.workspace_id == workspace_id).order_by(Document.created_at.desc()).limit(100)
    ).all()
    return ok([
        {
            "id": d.id,
            "title": d.title,
            "document_type": d.document_type,
            "chunk_count": d.chunk_count,
            "dataset_id": d.dataset_id,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
        }
        for d in documents
    ])


@router.post("")
def create_document(
    payload: DocumentCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    get_workspace(payload.workspace_id, ctx, db, minimum_role="analyst")
    document = index_document(
        db,
        workspace_id=payload.workspace_id,
        organization_id=ctx.organization.id,
        title=payload.title,
        content=payload.content,
        document_type=payload.document_type,
        dataset_id=payload.dataset_id,
        metadata={"source": "user_upload", "author": ctx.user.email},
    )
    audit.record(db, action="document.created", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=payload.workspace_id, resource_type="document", resource_id=document.id)
    db.commit()
    return ok({
        "id": document.id,
        "title": document.title,
        "chunk_count": document.chunk_count,
        "document_type": document.document_type,
    })


@router.delete("/{document_id}")
def delete_document(document_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise AppError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    workspace = db.get(Workspace, document.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    ctx.require("analyst")
    db.delete(document)
    db.commit()
    return ok({"deleted": True})
