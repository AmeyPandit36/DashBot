"""Authentication endpoints: register, login, logout, me, password reset."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import TenantContext, get_current_user, get_tenant_context, ok
from app.core.errors import AppError
from app.core.ratelimit import client_key, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.core.utils import slugify, unique_suffix
from app.db.session import get_db
from app.models import Membership, Organization, User, Workspace
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    organization_name: str | None = Field(default=None, max_length=160)
    workspace_name: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if value.isdigit() or value.lower() in ("password", "password123"):
            raise ValueError("Choose a stronger password.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


def _user_payload(user: User, organization: Organization, membership: Membership, workspaces: list[Workspace]) -> dict:
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "job_title": user.job_title,
            "preferences": user.preferences or {},
            "created_at": user.created_at.isoformat(),
        },
        "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug, "plan": organization.plan},
        "role": membership.role,
        "workspaces": [
            {"id": w.id, "name": w.name, "slug": w.slug, "description": w.description} for w in workspaces
        ],
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )


@router.post("/register")
def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.check(client_key(request), settings.LOGIN_RATE_LIMIT_PER_MINUTE)
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise AppError("EMAIL_IN_USE", "An account with this email already exists.", 409)

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        status="active",
        preferences={"theme": "system", "number_format": "compact"},
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    org_name = (payload.organization_name or f"{payload.full_name.split()[0]}'s organisation").strip()
    organization = Organization(name=org_name[:160], slug=f"{slugify(org_name)}-{unique_suffix()}", created_by=user.id)
    db.add(organization)
    db.flush()

    membership = Membership(user_id=user.id, organization_id=organization.id, role="owner", status="active")
    db.add(membership)
    workspace = Workspace(
        organization_id=organization.id,
        name=(payload.workspace_name or "Retail analytics")[:160],
        slug=f"{slugify(payload.workspace_name or 'retail-analytics')}-{unique_suffix()}",
        description="Your first analytical workspace",
        created_by=user.id,
    )
    db.add(workspace)
    db.flush()

    token = create_access_token(user.id, organization.id)
    _set_session_cookie(response, token)
    audit.record(
        db,
        action="auth.register",
        user_id=user.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        resource_type="user",
        resource_id=user.id,
    )
    db.commit()
    return ok({**_user_payload(user, organization, membership, [workspace]), "token": token})


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.check(client_key(request), settings.LOGIN_RATE_LIMIT_PER_MINUTE)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Incorrect email or password.", 401)
    if user.status != "active":
        raise AppError("ACCOUNT_DISABLED", "This account is not active.", 403)

    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.status == "active")
    )
    if not membership:
        raise AppError("NO_ORGANIZATION", "This account has no active organisation.", 403)
    organization = db.get(Organization, membership.organization_id)
    workspaces = db.scalars(select(Workspace).where(Workspace.organization_id == organization.id)).all()
    user.last_login_at = datetime.now(timezone.utc)

    token = create_access_token(user.id, organization.id)
    _set_session_cookie(response, token)
    audit.record(
        db,
        action="auth.login",
        user_id=user.id,
        organization_id=organization.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return ok({**_user_payload(user, organization, membership, list(workspaces)), "token": token})


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    return ok({"signed_out": True})


@router.get("/me")
def me(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    workspaces = db.scalars(
        select(Workspace).where(Workspace.organization_id == ctx.organization.id).order_by(Workspace.created_at)
    ).all()
    return ok(_user_payload(ctx.user, ctx.organization, ctx.membership, list(workspaces)))


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    result: dict = {"sent": True, "message": "If that email exists, reset instructions have been sent."}
    if user:
        token = jwt.encode(
            {
                "sub": user.id,
                "purpose": "password_reset",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        if not settings.is_production:
            # Email delivery is not configured locally: surface the token for development only.
            result["development_reset_token"] = token
    return ok(result)


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(payload.token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_RESET_TOKEN", "This reset link is invalid or has expired.", 400) from exc
    if claims.get("purpose") != "password_reset":
        raise AppError("INVALID_RESET_TOKEN", "This reset link is invalid.", 400)
    user = db.get(User, claims.get("sub"))
    if not user:
        raise AppError("INVALID_RESET_TOKEN", "This reset link is invalid.", 400)
    user.password_hash = hash_password(payload.password)
    audit.record(db, action="auth.password_reset", user_id=user.id, resource_type="user", resource_id=user.id)
    db.commit()
    return ok({"reset": True})
