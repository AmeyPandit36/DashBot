"""Organisation, workspace, member and settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import TenantContext, get_tenant_context, get_workspace as require_workspace, ok
from app.core.errors import AppError
from app.core.utils import slugify, unique_suffix
from app.db.session import get_db
from app.models import (
    AuditLog,
    Conversation,
    Dashboard,
    Dataset,
    Membership,
    Organization,
    OrganizationInvitation,
    User,
    Workspace,
)
from app.services import audit

router = APIRouter(tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=400)
    organization_id: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=400)


class MemberInvite(BaseModel):
    email: EmailStr
    role: str = Field(default="analyst", pattern="^(analyst|admin|viewer)$")


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern="^(owner|admin|analyst|viewer)$")


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    preferences: dict | None = None


@router.get("/organizations")
def list_organizations(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).where(Membership.user_id == ctx.user.id)).all()
    orgs = [db.get(Organization, m.organization_id) for m in memberships]
    return ok([
        {"id": o.id, "name": o.name, "slug": o.slug, "plan": o.plan, "role": m.role}
        for o, m in zip(orgs, memberships) if o
    ])


@router.get("/organizations/current")
def current_organization(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    member_count = db.scalar(
        select(func.count(Membership.id)).where(Membership.organization_id == ctx.organization.id)
    )
    workspace_count = db.scalar(
        select(func.count(Workspace.id)).where(Workspace.organization_id == ctx.organization.id)
    )
    return ok({
        "id": ctx.organization.id,
        "name": ctx.organization.name,
        "slug": ctx.organization.slug,
        "plan": ctx.organization.plan,
        "role": ctx.role,
        "member_count": member_count,
        "workspace_count": workspace_count,
        "created_at": ctx.organization.created_at.isoformat(),
    })


@router.post("/workspaces")
def create_workspace(payload: WorkspaceCreate, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    ctx.require("admin")
    workspace = Workspace(
        organization_id=ctx.organization.id,
        name=payload.name.strip(),
        slug=f"{slugify(payload.name)}-{unique_suffix()}",
        description=payload.description,
        created_by=ctx.user.id,
    )
    db.add(workspace)
    db.flush()
    audit.record(db, action="workspace.created", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 workspace_id=workspace.id, resource_type="workspace", resource_id=workspace.id)
    db.commit()
    return ok({"id": workspace.id, "name": workspace.name, "slug": workspace.slug, "description": workspace.description})


@router.get("/workspaces")
def list_workspaces(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    workspaces = db.scalars(
        select(Workspace).where(Workspace.organization_id == ctx.organization.id).order_by(Workspace.created_at)
    ).all()
    payload = []
    for workspace in workspaces:
        dataset_count = db.scalar(select(func.count(Dataset.id)).where(Dataset.workspace_id == workspace.id))
        dashboard_count = db.scalar(select(func.count(Dashboard.id)).where(Dashboard.workspace_id == workspace.id))
        payload.append({
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "description": workspace.description,
            "dataset_count": dataset_count,
            "dashboard_count": dashboard_count,
            "created_at": workspace.created_at.isoformat(),
        })
    return ok(payload)


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    workspace = require_workspace(workspace_id, ctx, db)
    datasets = db.scalars(
        select(Dataset).where(Dataset.workspace_id == workspace.id).order_by(Dataset.created_at.desc()).limit(5)
    ).all()
    dashboards = db.scalars(
        select(Dashboard).where(Dashboard.workspace_id == workspace.id).order_by(Dashboard.created_at.desc()).limit(5)
    ).all()
    conversations = db.scalars(
        select(Conversation).where(Conversation.workspace_id == workspace.id)
        .order_by(Conversation.updated_at.desc()).limit(5)
    ).all()
    return ok({
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "created_at": workspace.created_at.isoformat(),
        "recent_datasets": [
            {"id": d.id, "name": d.name, "status": d.status, "row_count": d.row_count,
             "quality_score": d.quality_score, "is_synthetic": d.is_synthetic, "created_at": d.created_at.isoformat()}
            for d in datasets
        ],
        "recent_dashboards": [
            {"id": d.id, "title": d.title, "status": d.status, "dataset_id": d.dataset_id,
             "updated_at": d.updated_at.isoformat()}
            for d in dashboards
        ],
        "recent_conversations": [
            {"id": c.id, "title": c.title, "message_count": c.message_count, "updated_at": c.updated_at.isoformat(),
             "dataset_id": c.dataset_id}
            for c in conversations
        ],
    })


@router.patch("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str, payload: WorkspaceUpdate, ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    workspace = require_workspace(workspace_id, ctx, db, minimum_role="admin")
    if payload.name:
        workspace.name = payload.name.strip()
    if payload.description is not None:
        workspace.description = payload.description
    db.commit()
    return ok({"id": workspace.id, "name": workspace.name, "description": workspace.description})


@router.get("/members")
def list_members(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    memberships = db.scalars(
        select(Membership).where(Membership.organization_id == ctx.organization.id).order_by(Membership.created_at)
    ).all()
    invitations = db.scalars(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == ctx.organization.id,
            OrganizationInvitation.status == "pending",
        )
    ).all()
    members = []
    for membership in memberships:
        user = db.get(User, membership.user_id)
        if not user:
            continue
        members.append({
            "id": membership.id,
            "user_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": membership.role,
            "status": membership.status,
            "joined_at": membership.created_at.isoformat(),
        })
    return ok({
        "members": members,
        "invitations": [
            {"id": i.id, "email": i.email, "role": i.role, "status": i.status, "created_at": i.created_at.isoformat()}
            for i in invitations
        ],
    })


@router.post("/members/invite")
def invite_member(payload: MemberInvite, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    ctx.require("admin")
    existing_user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing_user:
        already = db.scalar(
            select(Membership).where(
                Membership.user_id == existing_user.id,
                Membership.organization_id == ctx.organization.id,
            )
        )
        if already:
            raise AppError("ALREADY_MEMBER", "This person is already a member of the organisation.", 409)
        db.add(Membership(user_id=existing_user.id, organization_id=ctx.organization.id, role=payload.role))
        db.commit()
        return ok({"invited": True, "added_existing_user": True})
    invitation = OrganizationInvitation(
        organization_id=ctx.organization.id,
        email=payload.email.lower(),
        role=payload.role,
        token=unique_suffix() + unique_suffix(),
        status="pending",
        invited_by=ctx.user.id,
    )
    db.add(invitation)
    audit.record(db, action="member.invited", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 metadata={"email": payload.email, "role": payload.role})
    db.commit()
    return ok({
        "invited": True,
        "invitation_id": invitation.id,
        "note": "Email delivery is not configured in this environment. Share the invitation email and ask the user to register.",
    })


@router.patch("/members/{membership_id}")
def update_member_role(
    membership_id: str, payload: MemberRoleUpdate, ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    ctx.require("admin")
    membership = db.get(Membership, membership_id)
    if not membership or membership.organization_id != ctx.organization.id:
        raise AppError("MEMBER_NOT_FOUND", "Member not found.", 404)
    if membership.role == "owner" and payload.role != "owner":
        owners = db.scalar(
            select(func.count(Membership.id)).where(
                Membership.organization_id == ctx.organization.id, Membership.role == "owner"
            )
        )
        if owners <= 1:
            raise AppError("LAST_OWNER", "The organisation must keep at least one owner.", 409)
    membership.role = payload.role
    audit.record(db, action="member.role_changed", user_id=ctx.user.id, organization_id=ctx.organization.id,
                 metadata={"membership_id": membership.id, "role": payload.role})
    db.commit()
    return ok({"id": membership.id, "role": membership.role})


@router.get("/activity")
def activity(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db), limit: int = 20):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == ctx.organization.id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(max(limit, 1), 100))
    ).all()
    return ok([
        {
            "id": row.id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "metadata": row.metadata_json,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ])


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    user = db.get(User, ctx.user.id)
    if payload.full_name:
        user.full_name = payload.full_name.strip()
    if payload.job_title is not None:
        user.job_title = payload.job_title
    if payload.preferences is not None:
        user.preferences = {**(user.preferences or {}), **payload.preferences}
    db.commit()
    return ok({
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "job_title": user.job_title,
        "preferences": user.preferences,
    })


@router.get("/settings/security")
def security_overview(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    from app.core.config import settings as app_settings

    return ok({
        "sessions": {
            "login_at": ctx.user.last_login_at.isoformat() if ctx.user.last_login_at else None,
            "token_ttl_minutes": app_settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "http_only_cookie": True,
            "secure_cookie": app_settings.COOKIE_SECURE,
        },
        "ai": {
            "llm_enabled": app_settings.llm_configured,
            "provider": "Google Gemini" if app_settings.llm_configured else "Deterministic engine (no API key configured)",
            "model": app_settings.GEMINI_MODEL if app_settings.llm_configured else "rule-based planner",
            "tracing": bool(app_settings.LANGFUSE_PUBLIC_KEY),
        },
        "storage": {"backend": app_settings.STORAGE_BACKEND},
        "isolation": {"scope": "organisation", "workspace_scoped_queries": True, "audit_logging": True},
    })
