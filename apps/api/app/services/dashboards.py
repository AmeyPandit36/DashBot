"""Dashboard persistence, generation and trusted data resolution."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.agents.tools import load_context
from app.core.errors import AppError
from app.dashboards.planner import generate_dashboard_spec
from app.dashboards.schema import validate_dashboard_spec
from app.models import Dashboard, DashboardVersion, Dataset, SemanticModel, User
from app.sql.builder import QueryFilter, QuerySpec, build_query

logger = logging.getLogger("agentic_bi.dashboards")


def generate(
    db: Session,
    *,
    dataset: Dataset,
    model: SemanticModel,
    user: User,
    mode: str = "review",
    title: str | None = None,
) -> tuple[Dashboard, DashboardVersion, dict]:
    if model.status != "approved":
        raise AppError(
            "SEMANTIC_NOT_APPROVED",
            "Approve the semantic model before generating a dashboard.",
            409,
        )
    definition = dict(model.definition or {})
    definition["version"] = model.version_number

    spec, report = generate_dashboard_spec(dataset.id, definition, mode=mode)
    if spec is None:
        raise AppError("DASHBOARD_GENERATION_FAILED", "The dashboard specification could not be validated.", 422,
                       {"report": report})
    if title:
        spec["title"] = title[:140]
    spec["semantic_model_version"] = model.version_number
    spec["generation_mode"] = mode
    spec["metadata"].update({"semantic_model_id": model.id, "dataset_version": dataset.active_version})

    existing = db.query(Dashboard).filter(Dashboard.dataset_id == dataset.id).order_by(
        Dashboard.created_at.desc()
    ).first()
    status = "published" if mode == "automatic" else "draft"
    if existing and existing.status in ("draft", "published"):
        dashboard = existing
        version_number = max((v.version_number for v in dashboard.versions), default=0) + 1
        dashboard.title = spec["title"]
        dashboard.description = spec.get("description")
        dashboard.generation_mode = mode
        dashboard.status = status
    else:
        dashboard = Dashboard(
            workspace_id=dataset.workspace_id,
            dataset_id=dataset.id,
            title=spec["title"],
            description=spec.get("description"),
            status=status,
            generation_mode=mode,
            created_by=user.id,
        )
        db.add(dashboard)
        db.flush()
        version_number = 1

    spec["dashboard_id"] = dashboard.id
    spec["metadata"]["version"] = version_number
    validated, validation = validate_dashboard_spec(spec, definition)
    if validated is None:
        raise AppError("DASHBOARD_INVALID", "Dashboard validation failed.", 422,
                       {"errors": validation.errors})

    version = DashboardVersion(
        dashboard_id=dashboard.id,
        version_number=version_number,
        specification=validated,
        generated_by=report.get("provider", "dashboard_planner"),
        validation_report=report.get("validation", {}),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    if status == "published":
        dashboard.active_version_id = version.id
    dashboard.title = validated["title"]
    dashboard.description = validated.get("description", "")
    db.commit()
    return dashboard, version, report


def active_version(db: Session, dashboard: Dashboard) -> DashboardVersion | None:
    if dashboard.active_version_id:
        version = db.get(DashboardVersion, dashboard.active_version_id)
        if version:
            return version
    return max(dashboard.versions, key=lambda v: v.version_number) if dashboard.versions else None


def update_spec(db: Session, dashboard: Dashboard, spec: dict, user: User, semantic: dict) -> DashboardVersion:
    spec = dict(spec)
    spec["dashboard_id"] = dashboard.id
    current = active_version(db, dashboard)
    validated, report = validate_dashboard_spec(spec, semantic)
    if validated is None:
        raise AppError("DASHBOARD_INVALID", "Dashboard validation failed.", 422, {"errors": report.errors})
    if dashboard.status == "draft" and current and current.version_number == 1:
        current.specification = validated
        current.validation_report = report.model_dump()
        current.created_by = user.id
        db.commit()
        return current

    version_number = max((v.version_number for v in dashboard.versions), default=0) + 1
    validated["metadata"]["version"] = version_number
    version = DashboardVersion(
        dashboard_id=dashboard.id,
        version_number=version_number,
        specification=validated,
        generated_by="user_edit",
        validation_report=report.model_dump(),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    dashboard.title = validated["title"]
    dashboard.description = validated.get("description", "")
    if dashboard.status == "published":
        dashboard.active_version_id = version.id
    db.commit()
    return version


def publish(db: Session, dashboard: Dashboard) -> DashboardVersion:
    version = max(dashboard.versions, key=lambda v: v.version_number) if dashboard.versions else None
    if version is None:
        raise AppError("DASHBOARD_EMPTY", "This dashboard has no version to publish.", 409)
    dashboard.status = "published"
    dashboard.active_version_id = version.id
    db.commit()
    return version


def widget_data(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    user_id: str,
    dashboard: Dashboard,
    widget_id: str,
    runtime_filters: list[dict] | None = None,
) -> dict:
    version = active_version(db, dashboard)
    if version is None:
        raise AppError("DASHBOARD_NOT_FOUND", "This dashboard has no published version.", 404)
    spec = version.specification or {}
    widget = next((w for w in spec.get("widgets", []) if w["id"] == widget_id), None)
    if widget is None:
        raise AppError("WIDGET_NOT_FOUND", f"Widget '{widget_id}' does not exist in this dashboard.", 404)
    query_spec_dict = spec.get("queries", {}).get(widget["query_ref"])
    if query_spec_dict is None:
        raise AppError("QUERY_NOT_FOUND", "The widget's query reference is missing.", 422)

    ctx = load_context(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dashboard.dataset_id,
    )
    if dashboard.dataset_id != ctx.dataset.id:
        raise AppError("TENANT_MISMATCH", "Dashboard dataset is not accessible.", 403)

    try:
        query = QuerySpec.model_validate(query_spec_dict)
    except Exception as exc:  # noqa: BLE001
        raise AppError("INVALID_QUERY", f"Stored query specification is invalid: {exc}", 422) from exc

    allowed_filter_fields = {f["field"] for f in spec.get("filters", [])}
    for item in runtime_filters or []:
        field = item.get("field")
        if field not in allowed_filter_fields:
            raise AppError("INVALID_FILTER", f"Filter field '{field}' is not enabled on this dashboard.", 422)
        if field not in {d["name"] for d in ctx.semantic.get("dimensions", [])} | {
            t["name"] for t in ctx.semantic.get("time_dimensions", [])
        }:
            raise AppError("INVALID_FILTER", f"Filter field '{field}' is not in the semantic model.", 422)
        try:
            query.filters = [*query.filters, QueryFilter.model_validate(item)]
        except Exception as exc:  # noqa: BLE001
            raise AppError("INVALID_FILTER", f"Invalid filter value: {exc}", 422) from exc

    sql, params, columns = build_query(query, ctx.semantic, ctx.version.table_name)
    result = ctx.engine.execute(sql, params=params, limit=query.limit)

    comparison = None
    if widget.get("type") == "kpi" and (widget.get("options") or {}).get("compare") == "previous_period":
        comparison = _previous_period_comparison(query, ctx, spec)

    return {
        "widget_id": widget_id,
        "type": widget["type"],
        "title": widget["title"],
        "encoding": widget["encoding"],
        "options": widget.get("options", {}),
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": result["row_count"],
        "truncated": result["truncated"],
        "duration_ms": result["duration_ms"],
        "sql": sql,
        "query_spec": query.model_dump(),
        "comparison": comparison,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _previous_period_comparison(query: QuerySpec, ctx, spec: dict) -> dict | None:
    """Compare a KPI with the equal-length window immediately before the active date filter.

    Only runs when the dashboard has an explicit date range applied, so the
    comparison is always a real aggregate over real rows — never an estimate.
    """
    time_fields = {
        f["field"] for f in spec.get("filters", []) if f.get("type") == "date_range"
    } & {t["name"] for t in ctx.semantic.get("time_dimensions", [])}
    if not time_fields:
        return None
    field = next(iter(time_fields))
    start = end = None
    for item in query.filters:
        if item.field != field:
            continue
        if item.operator in ("gte", "gt"):
            start = item.value
        elif item.operator in ("lte", "lt"):
            end = item.value
    if not start or not end:
        return None
    try:
        start_date = date.fromisoformat(str(start)[:10])
        end_date = date.fromisoformat(str(end)[:10])
    except ValueError:
        return None
    span = (end_date - start_date).days + 1
    if span <= 0:
        return None
    previous_start = start_date - timedelta(days=span)
    previous_end = start_date - timedelta(days=1)

    shifted = QuerySpec.model_validate(query.model_dump())
    shifted.filters = [item for item in shifted.filters if item.field != field]
    shifted.filters.append(QueryFilter(field=field, operator="gte", value=previous_start.isoformat()))
    shifted.filters.append(QueryFilter(field=field, operator="lte", value=previous_end.isoformat()))
    try:
        previous_sql, previous_params, _ = build_query(shifted, ctx.semantic, ctx.version.table_name)
        previous_result = ctx.engine.execute(previous_sql, params=previous_params, limit=1)
    except Exception:  # noqa: BLE001 - comparison is optional enrichment
        logger.warning("kpi_comparison_failed field=%s", field, exc_info=True)
        return None
    if not previous_result["rows"] or not previous_result["rows"][0]:
        return None
    previous_value = previous_result["rows"][0][0]
    if previous_value in (None, 0):
        return None
    return {
        "previous_value": previous_value,
        "previous_start": previous_start.isoformat(),
        "previous_end": previous_end.isoformat(),
        "period_days": span,
        "sql": previous_sql,
        "row_count": previous_result["row_count"],
    }


def serialize_dashboard(db: Session, dashboard: Dashboard, include_spec: bool = True) -> dict:
    version = active_version(db, dashboard)
    spec = version.specification if version else {}
    return {
        "id": dashboard.id,
        "workspace_id": dashboard.workspace_id,
        "dataset_id": dashboard.dataset_id,
        "title": dashboard.title,
        "description": dashboard.description,
        "status": dashboard.status,
        "generation_mode": dashboard.generation_mode,
        "created_at": dashboard.created_at.isoformat(),
        "updated_at": dashboard.updated_at.isoformat(),
        "version": version.version_number if version else None,
        "version_id": version.id if version else None,
        "version_count": len(dashboard.versions),
        "widget_count": len(spec.get("widgets", [])),
        "specification": spec if include_spec else None,
    }
