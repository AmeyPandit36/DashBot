"""LangGraph state contract for the analytical question workflow."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Tenancy (never model-visible secrets)
    organization_id: str
    workspace_id: str
    user_id: str
    conversation_id: str | None

    # Dataset context
    dataset_id: str
    dataset_version_id: str
    semantic_model_version: int
    table_name: str

    # Question
    user_question: str
    history: list[dict]
    intent: str
    route: str
    need_context: bool

    # Planning and execution
    plan: dict
    steps: list[dict]
    sql_validated: bool
    sql_errors: list[str]
    llm_used: bool
    tokens: int

    # Retrieval
    retrieved_context: list[dict]

    # Outcome
    narrative: str
    summary: str
    insights: list[dict]
    follow_ups: list[str]
    visualization: dict | None
    verification: dict
    force_deterministic: bool
    response: dict

    retry_count: int
    errors: list[str]
    trace: list[dict]
    extra: dict[str, Any]
