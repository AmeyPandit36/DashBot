"""Audit logging helper."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.logging import log_event, request_id_ctx
from app.models import AuditLog

logger = logging.getLogger("agentic_bi.audit")


def record(
    db: Session,
    *,
    action: str,
    user_id: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        user_id=user_id,
        organization_id=organization_id,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata or {},
        ip_address=ip_address,
        request_id=request_id_ctx.get(),
    )
    db.add(entry)
    db.flush()
    log_event(logger, "audit", action=action, user_id=user_id, workspace_id=workspace_id,
              resource_type=resource_type, resource_id=resource_id)
    return entry
