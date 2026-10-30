"""Conversational analytics service: persistence + LangGraph invocation."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import build_question_graph
from app.agents.state import AgentState
from app.agents.tools import load_context
from app.core.deps import TenantContext
from app.core.errors import AppError
from app.models import (
    AgentRun,
    Conversation,
    Dataset,
    Message,
    QueryLog,
)
from app.services import audit

logger = logging.getLogger("agentic_bi.chat")


def _get_or_create_conversation(
    db: Session, ctx: TenantContext, workspace_id: str, dataset_id: str, conversation_id: str | None, question: str
) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if not conversation or conversation.workspace_id != workspace_id:
            raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found in this workspace.", 404)
        return conversation
    conversation = Conversation(
        workspace_id=workspace_id,
        user_id=ctx.user.id,
        dataset_id=dataset_id,
        title=question[:120] or "New analysis",
    )
    db.add(conversation)
    db.flush()
    return conversation


def run_question(
    db: Session,
    *,
    tenant: TenantContext,
    workspace_id: str,
    dataset_id: str,
    question: str,
    conversation_id: str | None = None,
    context: dict | None = None,
) -> dict:
    dataset = db.get(Dataset, dataset_id)
    if not dataset or dataset.workspace_id != workspace_id:
        raise AppError("DATASET_NOT_FOUND", "Dataset not found in this workspace.", 404)
    if dataset.status not in ("ready", "needs_review"):
        raise AppError("DATASET_NOT_READY", "This dataset is still processing.", 409)
    if not question.strip():
        raise AppError("EMPTY_QUESTION", "Enter a question to analyse.", 422)

    conversation = _get_or_create_conversation(
        db, tenant, workspace_id, dataset_id, conversation_id, question
    )
    history = [
        {"role": m.role, "text": m.text}
        for m in db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.desc()).limit(6)
        ).all()
    ][::-1]

    user_message = Message(conversation_id=conversation.id, role="user", text=question, content={"context": context or {}})
    db.add(user_message)
    db.flush()

    tool_ctx = load_context(
        db,
        organization_id=tenant.organization.id,
        workspace_id=workspace_id,
        user_id=tenant.user.id,
        dataset_id=dataset_id,
    )
    graph = build_question_graph(tool_ctx)
    started = time.perf_counter()
    initial: AgentState = {
        "organization_id": tenant.organization.id,
        "workspace_id": workspace_id,
        "user_id": tenant.user.id,
        "conversation_id": conversation.id,
        "dataset_id": dataset_id,
        "dataset_version_id": tool_ctx.version.id,
        "semantic_model_version": int(tool_ctx.semantic.get("version") or 1),
        "table_name": tool_ctx.version.table_name,
        "user_question": question,
        "history": history,
        "retry_count": 0,
        "errors": [],
        "trace": [],
        "steps": [],
        "extra": {},
    }
    try:
        final_state = graph.invoke(initial)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_graph_failed workspace=%s", workspace_id)
        raise AppError(
            "AGENT_FAILED",
            "The analytical agent could not complete this request. Please try rephrasing.",
            500,
            {"reason": str(exc)[:300]},
        ) from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response = final_state.get("response") or {}
    steps = final_state.get("steps") or []

    query_ids: list[str] = []
    for step in steps:
        result = step.get("result") or {}
        log = QueryLog(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            dataset_version_id=tool_ctx.version.id,
            conversation_id=conversation.id,
            user_id=tenant.user.id,
            question=question,
            sql_text=step.get("sql") or "",
            execution_status=step.get("status") or "unknown",
            error_message=step.get("error"),
            row_count=int(step.get("row_count") or 0),
            duration_ms=result.get("duration_ms"),
            result_preview={"columns": result.get("columns", []), "rows": (result.get("rows") or [])[:20]},
            verification=response.get("verification") or {},
            provenance={
                "dataset_version": tool_ctx.version.version_number,
                "semantic_model_version": tool_ctx.semantic.get("version"),
                "intent": response.get("intent"),
                "route": response.get("route"),
                "label": step.get("label"),
            },
        )
        db.add(log)
        db.flush()
        query_ids.append(log.id)
        if response.get("result") is None and step.get("role") == "primary":
            response["result"] = result

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        text=response.get("answer", ""),
        content={
            "intent": response.get("intent"),
            "route": response.get("route"),
            "verification": response.get("verification"),
            "result": response.get("result"),
            "visualization": response.get("visualization"),
            "insights": response.get("insights"),
            "follow_ups": response.get("follow_ups"),
            "evidence": [
                {k: v for k, v in step.items() if k != "result"} | {"result": step.get("result")}
                for step in steps
            ],
            "context": response.get("context"),
            "query_ids": query_ids,
            "trace": response.get("trace"),
            "plan": response.get("plan"),
            "llm_used": response.get("llm_used", False),
        },
        query_id=query_ids[0] if query_ids else None,
        verification_status=(response.get("verification") or {}).get("status"),
    )
    db.add(assistant_message)

    conversation.message_count = (conversation.message_count or 0) + 2
    if conversation.title in ("New analysis", ""):
        conversation.title = question[:120]

    agent_run = AgentRun(
        workspace_id=workspace_id,
        conversation_id=conversation.id,
        graph="question",
        status="completed" if response.get("answer") else "failed",
        intent=response.get("intent"),
        route=response.get("route"),
        steps=[{"node": t.get("node"), "detail": {k: v for k, v in t.items() if k != "node"}} for t in response.get("trace", [])],
        latency_ms=latency_ms,
        tokens=int(response.get("tokens") or 0),
    )
    db.add(agent_run)
    db.commit()

    response["conversation_id"] = conversation.id
    response["message_id"] = assistant_message.id
    response["query_ids"] = query_ids
    response["provenance"] = {
        "dataset_version": tool_ctx.version.version_number,
        "semantic_model_version": tool_ctx.semantic.get("version"),
        "dataset_id": dataset_id,
        "query_ids": query_ids,
        "agent_run_id": agent_run.id,
        "latency_ms": latency_ms,
        "tool_calls": tool_ctx.calls,
    }
    audit.record(
        db,
        action="chat.question_answered",
        user_id=tenant.user.id,
        organization_id=tenant.organization.id,
        workspace_id=workspace_id,
        resource_type="conversation",
        resource_id=conversation.id,
        metadata={"intent": response.get("intent"), "verification": (response.get("verification") or {}).get("status")},
    )
    db.commit()
    return response


def serialize_message(message: Message) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "text": message.text,
        "content": message.content,
        "verification_status": message.verification_status,
        "created_at": message.created_at.isoformat(),
        "feedback": message.feedback,
    }


def serialize_conversation(conversation: Conversation, include_messages: bool = False) -> dict:
    payload = {
        "id": conversation.id,
        "workspace_id": conversation.workspace_id,
        "dataset_id": conversation.dataset_id,
        "title": conversation.title,
        "message_count": conversation.message_count,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }
    if include_messages:
        payload["messages"] = [serialize_message(m) for m in conversation.messages]
    return payload
