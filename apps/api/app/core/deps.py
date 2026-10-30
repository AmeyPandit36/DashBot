"""Request dependencies: authentication, tenant context and role checks.

Tenant context always derives from the authenticated session — never from a
client-supplied organisation id alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Dataset, Membership, Organization, User, Workspace

ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3, "owner": 4}


@dataclass
class TenantContext:
    user: User
    organization: Organization
    membership: Membership

    @property
    def role(self) -> str:
        return self.membership.role

    def require(self, minimum: str) -> None:
        if ROLE_RANK.get(self.role, 0) < ROLE_RANK.get(minimum, 99):
            raise AppError(
                "INSUFFICIENT_ROLE",
                f"This action requires the '{minimum}' role. Your role is '{self.role}'.",
                403,
            )


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return request.cookies.get(settings.AUTH_COOKIE_NAME)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise AppError("NOT_AUTHENTICATED", "Authentication required.", 401)
    payload = decode_access_token(token)
    user = db.get(User, payload.get("sub"))
    if not user or user.status != "active":
        raise AppError("NOT_AUTHENTICATED", "Account is not active.", 401)
    return user


def get_tenant_context(request: Request, db: Session = Depends(get_db)) -> TenantContext:
    user = get_current_user(request, db)
    token = _token_from_request(request)
    org_id = None
    if token:
        try:
            org_id = decode_access_token(token).get("org")
        except AppError:
            org_id = None

    membership: Membership | None = None
    if org_id:
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        )
    if membership is None:
        membership = db.scalar(
            select(Membership)
            .where(Membership.user_id == user.id, Membership.status == "active")
            .order_by(Membership.created_at)
        )
    if membership is None:
        raise AppError("NO_ORGANIZATION", "Your account is not attached to an organisation.", 403)

    organization = db.get(Organization, membership.organization_id)
    if organization is None:
        raise AppError("NO_ORGANIZATION", "Organisation not found.", 403)
    return TenantContext(user=user, organization=organization, membership=membership)


def get_workspace(
    workspace_id: str, ctx: TenantContext, db: Session, minimum_role: str = "viewer"
) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found in your organisation.", 404)
    ctx.require(minimum_role)
    return workspace


def get_dataset(dataset_id: str, ctx: TenantContext, db: Session, minimum_role: str = "viewer") -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise AppError("DATASET_NOT_FOUND", "Dataset not found.", 404)
    workspace = db.get(Workspace, dataset.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("DATASET_NOT_FOUND", "Dataset not found.", 404)
    ctx.require(minimum_role)
    return dataset


def ok(data=None, meta: dict | None = None) -> dict:
    body: dict = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return body
