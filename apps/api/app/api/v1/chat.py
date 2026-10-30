"""Conversational analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, get_tenant_context, ok
from app.core.errors import AppError
from app.db.session import get_db
from app.models import Conversation, Message, Workspace
from app.services import chat as chat_service

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    workspace_id: str
    dataset_id: str
    conversation_id: str | None = None
    question: str = Field(min_length=2, max_length=1000)
    context: dict | None = None


class FeedbackRequest(BaseModel):
    feedback: str = Field(pattern="^(helpful|not_helpful)$")
    message_id: str | None = None


def _conversation(db: Session, conversation_id: str, ctx: TenantContext) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
    workspace = db.get(Workspace, conversation.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found.", 404)
    return conversation


@router.post("/chat")
def chat(payload: ChatRequest, ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    workspace = db.get(Workspace, payload.workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found.", 404)
    ctx.require("viewer")
    response = chat_service.run_question(
        db,
        tenant=ctx,
        workspace_id=payload.workspace_id,
        dataset_id=payload.dataset_id,
        question=payload.question.strip(),
        conversation_id=payload.conversation_id,
        context=payload.context,
    )
    return ok(response)


@router.get("/conversations")
def list_conversations(
    workspace_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.organization_id != ctx.organization.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found.", 404)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id, Conversation.user_id == ctx.user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    ).all()
    return ok([chat_service.serialize_conversation(c) for c in conversations])


@router.get("/conversations/{conversation_id}")
def conversation_detail(
    conversation_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    conversation = _conversation(db, conversation_id, ctx)
    return ok(chat_service.serialize_conversation(conversation, include_messages=True))


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    _conversation(db, conversation_id, ctx)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at).limit(limit)
    ).all()
    return ok([chat_service.serialize_message(m) for m in messages])


@router.post("/chat/{conversation_id}/feedback")
def submit_feedback(
    conversation_id: str,
    payload: FeedbackRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    conversation = _conversation(db, conversation_id, ctx)
    query = select(Message).where(Message.conversation_id == conversation.id, Message.role == "assistant")
    if payload.message_id:
        query = query.where(Message.id == payload.message_id)
    message = db.scalars(query.order_by(Message.created_at.desc()).limit(1)).first()
    if not message:
        raise AppError("MESSAGE_NOT_FOUND", "No assistant message to rate.", 404)
    message.feedback = payload.feedback
    db.commit()
    return ok({"message_id": message.id, "feedback": message.feedback})


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    conversation = _conversation(db, conversation_id, ctx)
    db.delete(conversation)
    db.commit()
    return ok({"deleted": True})
