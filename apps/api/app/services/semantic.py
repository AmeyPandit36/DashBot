"""Semantic model lifecycle: proposal, edit, approval, glossary indexing."""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Dataset,
    DatasetVersion,
    DimensionDefinition,
    MetricDefinition,
    SemanticModel,
    Workspace,
)
from app.rag.store import replace_glossary
from app.semantic.inference import build_glossary, build_heuristic_proposal, refine_with_llm
from app.semantic.schemas import validate_semantic_definition

logger = logging.getLogger("agentic_bi.semantic")


def latest_model(db: Session, dataset_id: str) -> SemanticModel | None:
    return (
        db.query(SemanticModel)
        .filter(SemanticModel.dataset_id == dataset_id)
        .order_by(SemanticModel.version_number.desc())
        .first()
    )


def approved_model(db: Session, dataset_id: str) -> SemanticModel | None:
    return (
        db.query(SemanticModel)
        .filter(SemanticModel.dataset_id == dataset_id, SemanticModel.status == "approved")
        .order_by(SemanticModel.version_number.desc())
        .first()
    )


def propose(db: Session, dataset: Dataset, version: DatasetVersion, *, regenerate: bool = False) -> SemanticModel:
    profile = version.profile or {}
    columns = profile.get("columns", [])
    available = {c["name"] for c in columns}
    types = {c["name"]: c["inferred_type"] for c in columns}

    heuristic = build_heuristic_proposal(
        dataset.id, version.id, version.table_name, profile, grain=profile.get("grain", "one row per record")
    )
    refined, meta = refine_with_llm(heuristic, profile, available)
    validated, report = validate_semantic_definition(refined, available, types)
    if not validated:
        logger.warning("semantic_proposal_invalid dataset=%s errors=%s", dataset.id, report.errors)
        raise AppError(
            "SEMANTIC_PROPOSAL_FAILED",
            "A valid semantic model could not be inferred for this dataset.",
            422,
            {"errors": report.errors},
        )
    validated["version"] = 1

    previous = latest_model(db, dataset.id)
    if previous and previous.status == "proposed" and not regenerate:
        # Replace the pending draft rather than stacking versions.
        version_number = previous.version_number
        db.delete(previous)
        db.flush()
    elif previous:
        version_number = previous.version_number + 1
    else:
        version_number = 1

    model = SemanticModel(
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        version_number=version_number,
        status="proposed",
        generated_by=validated.get("generated_by", "heuristic"),
        definition={**validated, "version": version_number},
    )
    db.add(model)
    db.flush()
    _sync_children(db, model, validated)
    if dataset.status == "ready":
        dataset.status = "needs_review"
    logger.info("semantic_proposed dataset=%s version=%s provider=%s", dataset.id, version_number, meta.get("provider"))
    return model


def _sync_children(db: Session, model: SemanticModel, definition: dict) -> None:
    db.query(MetricDefinition).filter(MetricDefinition.semantic_model_id == model.id).delete()
    db.query(DimensionDefinition).filter(DimensionDefinition.semantic_model_id == model.id).delete()
    db.flush()
    for metric in definition.get("metrics", []):
        db.add(MetricDefinition(
            semantic_model_id=model.id,
            metric_name=metric["name"],
            label=metric.get("label", metric["name"]),
            aggregation=metric["aggregation"],
            source_column=metric.get("source_column", ""),
            format=metric.get("format", "number"),
            description=metric.get("description", ""),
            confirmed=bool(metric.get("confirmed", False)),
        ))
    for dim in definition.get("dimensions", []) + [
        {**t, "data_type": "time", "confirmed": True} for t in definition.get("time_dimensions", [])
    ]:
        db.add(DimensionDefinition(
            semantic_model_id=model.id,
            dimension_name=dim["name"],
            label=dim.get("label", dim["name"]),
            source_column=dim["source_column"],
            data_type=dim.get("data_type", "categorical"),
            default_grain=dim.get("default_grain"),
            description=dim.get("description", ""),
            confirmed=bool(dim.get("confirmed", False)),
        ))
    db.flush()


def update_definition(db: Session, model: SemanticModel, definition: dict, available_columns: set[str],
                      available_types: dict[str, str]) -> tuple[SemanticModel, dict]:
    if model.status == "approved":
        # Editing an approved model creates a new version in review.
        new_version = model.version_number + 1
        model.status = "superseded"
        db.flush()
        clone = SemanticModel(
            dataset_id=model.dataset_id,
            dataset_version_id=model.dataset_version_id,
            version_number=new_version,
            status="proposed",
            generated_by="user",
            definition={},
        )
        db.add(clone)
        db.flush()
        model = clone

    payload = {**definition}
    payload["dataset_id"] = model.dataset_id
    payload["table_name"] = definition.get("table_name") or (model.definition or {}).get("table_name")
    payload["version"] = model.version_number
    payload["dataset_version_id"] = model.dataset_version_id
    validated, report = validate_semantic_definition(payload, available_columns, available_types)
    if not validated:
        raise AppError("INVALID_SEMANTIC_MODEL", "The semantic model is invalid.", 422, {"errors": report.errors})
    validated["version"] = model.version_number
    model.definition = validated
    model.generated_by = "user"
    _sync_children(db, model, validated)
    db.flush()
    return model, report.model_dump()


def approve(db: Session, model: SemanticModel, user_id: str, organization_id: str) -> SemanticModel:
    if model.status == "approved":
        return model
    others = db.scalars(
        select(SemanticModel).where(
            SemanticModel.dataset_id == model.dataset_id,
            SemanticModel.status == "approved",
            SemanticModel.id != model.id,
        )
    ).all()
    for other in others:
        other.status = "superseded"

    model.status = "approved"
    model.approved_by = user_id
    model.approved_at = datetime.now(timezone.utc)
    # Deep copy so SQLAlchemy detects the JSON mutation (in-place edits to the
    # same nested objects would compare equal and never be persisted).
    definition = copy.deepcopy(model.definition or {})
    for metric in definition.get("metrics", []):
        metric["requires_approval"] = False
    model.definition = definition
    db.flush()

    dataset = db.get(Dataset, model.dataset_id)
    workspace = db.get(Workspace, dataset.workspace_id) if dataset else None
    if dataset and workspace:
        dataset.status = "ready"
        glossary = build_glossary(definition, dataset.name)
        try:
            replace_glossary(
                db,
                workspace_id=workspace.id,
                organization_id=organization_id,
                dataset_id=dataset.id,
                title=f"Business glossary — {dataset.name}",
                content=glossary,
            )
        except Exception:  # noqa: BLE001 - retrieval must not block approval
            logger.exception("glossary_indexing_failed dataset=%s", dataset.id)
    db.flush()
    return model


def serialize(model: SemanticModel) -> dict:
    return {
        "id": model.id,
        "dataset_id": model.dataset_id,
        "dataset_version_id": model.dataset_version_id,
        "version": model.version_number,
        "status": model.status,
        "generated_by": model.generated_by,
        "definition": model.definition,
        "approved_at": model.approved_at.isoformat() if model.approved_at else None,
        "created_at": model.created_at.isoformat(),
        "updated_at": model.updated_at.isoformat(),
    }
