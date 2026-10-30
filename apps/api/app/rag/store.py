"""Tenant-aware contextual retrieval.

Stores chunk embeddings (pgvector on PostgreSQL, JSON elsewhere) and retrieves
the most relevant approved business context. Retrieval is always scoped by
organisation + workspace, and optionally by dataset. Retrieved text is treated
as untrusted data, never as instructions.
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import llm
from app.core.config import settings
from app.core.logging import log_event
from app.models import Document, DocumentChunk
from app.rag.chunking import chunk_text

import logging

logger = logging.getLogger("agentic_bi.rag")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def index_document(
    db: Session,
    *,
    workspace_id: str,
    organization_id: str,
    title: str,
    content: str,
    document_type: str,
    dataset_id: str | None = None,
    metadata: dict | None = None,
) -> Document:
    """Create a document and its embedded chunks."""
    document = Document(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        title=title[:240],
        document_type=document_type,
        content=content,
        metadata_json=metadata or {},
        status="ready",
    )
    db.add(document)
    db.flush()

    pieces = chunk_text(content)
    vectors, _ = llm.embed_texts(pieces)
    for idx, (piece, vector) in enumerate(zip(pieces, vectors)):
        db.add(
            DocumentChunk(
                document_id=document.id,
                workspace_id=workspace_id,
                organization_id=organization_id,
                dataset_id=dataset_id,
                chunk_index=idx,
                content=piece,
                embedding=vector,
                embedding_model=settings.GEMINI_EMBEDDING_MODEL if llm.llm_available() else "deterministic-hash",
                embedding_version="v1",
                metadata_json={"title": title, "document_type": document_type, **(metadata or {})},
            )
        )
    document.chunk_count = len(pieces)
    db.flush()
    log_event(logger, "document_indexed", document_id=document.id, chunks=len(pieces), type=document_type)
    return document


def replace_glossary(
    db: Session,
    *,
    workspace_id: str,
    organization_id: str,
    dataset_id: str,
    title: str,
    content: str,
) -> Document:
    existing = db.scalars(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.dataset_id == dataset_id,
            Document.document_type == "glossary",
        )
    ).all()
    for doc in existing:
        db.delete(doc)
    db.flush()
    return index_document(
        db,
        workspace_id=workspace_id,
        organization_id=organization_id,
        title=title,
        content=content,
        document_type="glossary",
        dataset_id=dataset_id,
        metadata={"source": "semantic_model"},
    )


def retrieve_context(
    db: Session,
    *,
    query: str,
    organization_id: str,
    workspace_id: str,
    dataset_id: str | None = None,
    top_k: int = 5,
    min_score: float = 0.05,
) -> list[dict]:
    if not query.strip():
        return []
    vectors, _ = llm.embed_texts([query], trace_name="rag.query_embedding")
    query_vector = vectors[0]

    stmt = select(DocumentChunk).where(
        DocumentChunk.organization_id == organization_id,
        DocumentChunk.workspace_id == workspace_id,
    )
    if dataset_id:
        stmt = stmt.where((DocumentChunk.dataset_id == dataset_id) | (DocumentChunk.dataset_id.is_(None)))

    candidates = db.scalars(stmt.limit(800)).all()
    if not candidates:
        return []

    scored: list[tuple[float, DocumentChunk]] = []
    for chunk in candidates:
        try:
            vector = chunk.embedding if isinstance(chunk.embedding, list) else list(chunk.embedding)
        except TypeError:
            continue
        scored.append((_cosine(query_vector, vector), chunk))

    if not settings.is_sqlite:
        # pgvector path: use the database's vector index ordering for larger corpora.
        try:
            distance = DocumentChunk.embedding.cosine_distance(query_vector)
            rows = db.execute(
                stmt.add_columns(distance.label("distance")).order_by(distance).limit(top_k)
            ).all()
            if rows:
                scored = [(1 - float(row.distance), row[0]) for row in rows]
        except Exception:  # noqa: BLE001 - fall back to in-process scoring
            pass

    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[dict] = []
    for score, chunk in scored[:top_k]:
        if score < min_score:
            continue
        results.append({
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "title": chunk.metadata_json.get("title", "Business context"),
            "document_type": chunk.metadata_json.get("document_type", "note"),
            "content": chunk.content,
            "score": round(score, 4),
            "embedding_model": chunk.embedding_model,
        })
    return results
