"""Dashboard planner agent.

Produces a declarative dashboard specification from an approved semantic model.
Gemini may *choose* which trusted widget templates to use, but it never emits
component names, SQL or executable code: its plan is translated through the
same deterministic builders used in offline mode and then schema-validated.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.agents import llm
from app.dashboards.schema import validate_dashboard_spec
from app.sql.builder import QuerySpec

PREFERRED_KPIS = ("total_revenue", "total_orders", "average_order_value", "unique_customers", "total_quantity")
TREND_METRICS = ("total_revenue", "total_orders", "total_quantity")


class PlannerWidget(BaseModel):
    type: str
    title: str | None = None
    metric: str | None = None
    metrics: list[str] = Field(default_factory=list)
    dimension: str | None = None
    dimension2: str | None = None
    grain: str | None = None
    limit: int | None = None


class PlannerPlan(BaseModel):
    title: str | None = None
    description: str | None = None
    widgets: list[PlannerWidget] = Field(default_factory=list)


def _dimensions_of(semantic: dict) -> list[dict]:
    return [d for d in semantic.get("dimensions", []) if d.get("data_type") in ("categorical", "boolean")]


PREFERRED_DIM_TOKENS = (
    ("region", 100), ("country", 96), ("market", 94), ("territory", 92),
    ("category", 88), ("segment", 86), ("channel", 84), ("department", 82),
    ("product", 78), ("customer", 70), ("brand", 66), ("status", 60),
)


def _rank_dimensions(dimensions: list[dict]) -> list[dict]:
    """Order dimensions by analytical usefulness for an executive dashboard.

    Cardinality matters as much as the name: a 40-value dimension produces an
    unreadable chart, and a 1-value dimension explains nothing. Identifiers never
    reach this function (filtered by `_dimensions_of`).
    """
    def score(dimension: dict) -> float:
        name = dimension["name"].lower()
        value = 0.0
        for token, weight in PREFERRED_DIM_TOKENS:
            if token in name:
                value = max(value, weight)
                break
        unique = dimension.get("unique_count")
        if unique:
            if 2 <= unique <= 8:
                value += 14
            elif unique <= 15:
                value += 8
            elif unique <= 30:
                value += 2
            else:
                value -= 18
        return value

    return sorted(dimensions, key=score, reverse=True)


def _pick_kpis(semantic: dict, count: int = 4) -> list[dict]:
    metrics = {m["name"]: m for m in semantic.get("metrics", [])}
    ordered = [metrics[name] for name in PREFERRED_KPIS if name in metrics]
    for metric in semantic.get("metrics", []):
        if metric not in ordered and metric["aggregation"] in ("SUM", "COUNT_DISTINCT", "AVG"):
            ordered.append(metric)
    return ordered[:count]


def _primary_metric(semantic: dict) -> dict | None:
    metrics = {m["name"]: m for m in semantic.get("metrics", [])}
    for name in TREND_METRICS:
        if name in metrics:
            return metrics[name]
    return semantic["metrics"][0] if semantic.get("metrics") else None


def _default_window(time_dimension: dict) -> dict | None:
    """Default to the trailing 12 months so period-over-period KPIs compare real windows."""
    from datetime import date, timedelta

    try:
        end = date.fromisoformat(str(time_dimension.get("max_value"))[:10])
    except (TypeError, ValueError):
        return None
    return {"start": (end - timedelta(days=365)).isoformat(), "end": end.isoformat()}


def deterministic_plan(semantic: dict) -> dict:
    dimensions = _rank_dimensions(_dimensions_of(semantic))
    dim_a = dimensions[0] if dimensions else None
    dim_b = next((d for d in dimensions[1:] if 2 <= (d.get("unique_count") or 0) <= 8), None) or (
        dimensions[1] if len(dimensions) > 1 else None
    )
    dim_c = next((d for d in dimensions if d is not dim_a and d is not dim_b), None) or dim_a
    times = semantic.get("time_dimensions", [])
    kpis = _pick_kpis(semantic)
    primary = _primary_metric(semantic)
    queries: dict[str, dict] = {}
    widgets: list[dict] = []
    row = 0

    def add_widget(widget: dict) -> None:
        widgets.append(widget)

    # --- KPI row ---------------------------------------------------------
    for idx, metric in enumerate(kpis):
        query_id = f"kpi_{metric['name']}"
        queries[query_id] = QuerySpec(metrics=[metric["name"]], limit=1).model_dump()
        add_widget({
            "id": f"kpi_{metric['name']}",
            "type": "kpi",
            "title": metric["label"],
            "description": metric.get("description", "")[:200],
            "query_ref": query_id,
            "encoding": {"value": metric["name"]},
            "layout": {"x": (idx % 4) * 3, "y": row, "w": 3, "h": 2},
            "interactions": {"cross_filter": False, "click_to_ask": True},
            "options": {"value_format": metric.get("format", "number"), "compare": "previous_period"},
        })
    row += 2

    if primary and times:
        time_dim = times[0]
        query_id = "trend_primary"
        queries[query_id] = QuerySpec(
            metrics=[m for m in ("total_revenue", "total_orders") if m in {x["name"] for x in semantic["metrics"]}]
            or [primary["name"]],
            group_by=[time_dim["name"]],
            grain=time_dim.get("default_grain", "month"),
            order_by={"field": time_dim["name"], "direction": "asc"},
            limit=60,
        ).model_dump()
        add_widget({
            "id": "trend_primary",
            "type": "line_chart",
            "title": f"{primary['label']} over time",
            "description": f"Trend by {time_dim['label'].lower()} across the selected period.",
            "query_ref": query_id,
            "encoding": {"x": time_dim["name"], "y": queries[query_id]["metrics"]},
            "layout": {"x": 0, "y": row, "w": 8, "h": 4},
            "interactions": {"cross_filter": True, "click_to_ask": True},
            "options": {"palette": "brand", "show_legend": True},
        })

    if dim_a and primary:
        dim = dim_a
        query_id = "primary_by_dimension"
        queries[query_id] = QuerySpec(
            metrics=[primary["name"]],
            group_by=[dim["name"]],
            order_by={"field": primary["name"], "direction": "desc"},
            limit=12,
        ).model_dump()
        add_widget({
            "id": "primary_by_dimension",
            "type": "bar_chart",
            "title": f"{primary['label']} by {dim['label']}",
            "description": f"Comparison of {primary['label'].lower()} across {dim['label'].lower()}.",
            "query_ref": query_id,
            "encoding": {"x": dim["name"], "y": [primary["name"]]},
            "layout": {"x": 8 if (primary and times) else 0, "y": row, "w": 4 if (primary and times) else 6, "h": 4},
            "interactions": {"cross_filter": True, "click_to_ask": True},
            "options": {"palette": "brand", "sort": "desc"},
        })
    row += 4

    if dim_b and primary:
        dim = dim_b
        query_id = "mix_by_dimension"
        queries[query_id] = QuerySpec(
            metrics=[primary["name"]],
            group_by=[dim["name"]],
            order_by={"field": primary["name"], "direction": "desc"},
            limit=8,
        ).model_dump()
        add_widget({
            "id": "mix_by_dimension",
            "type": "donut_chart",
            "title": f"{primary['label']} mix by {dim['label']}",
            "description": f"Composition of {primary['label'].lower()} across {dim['label'].lower()}.",
            "query_ref": query_id,
            "encoding": {"label": dim["name"], "value": primary["name"]},
            "layout": {"x": 0, "y": row, "w": 4, "h": 4},
            "interactions": {"cross_filter": False, "click_to_ask": True},
            "options": {"palette": "categorical", "show_legend": True},
        })

    high_card = [
        d for d in dimensions
        if d not in (dim_a, dim_b) and 8 <= (d.get("unique_count") or 0) <= 40
    ]
    detail_dim = high_card[0] if high_card else dim_c
    if detail_dim and primary:
        query_id = "top_movers"
        queries[query_id] = QuerySpec(
            metrics=[primary["name"]],
            group_by=[detail_dim["name"]],
            order_by={"field": primary["name"], "direction": "desc"},
            limit=8,
        ).model_dump()
        add_widget({
            "id": "top_movers",
            "type": "bar_chart",
            "title": f"Top {detail_dim['label']} by {primary['label']}",
            "description": f"Highest contributing {detail_dim['label'].lower()} values.",
            "query_ref": query_id,
            "encoding": {"x": primary["name"], "y": [detail_dim["name"]]},
            "layout": {"x": 4, "y": row, "w": 8, "h": 4},
            "interactions": {"cross_filter": True, "click_to_ask": True},
            "options": {"palette": "sequential", "sort": "desc"},
        })
    row += 4

    if dim_a and dim_b and primary:
        query_id = "heatmap_dimensions"
        queries[query_id] = QuerySpec(
            metrics=[primary["name"]],
            group_by=[dim_a["name"], dim_b["name"]],
            order_by={"field": primary["name"], "direction": "desc"},
            limit=60,
        ).model_dump()
        add_widget({
            "id": "heatmap_dimensions",
            "type": "heatmap",
            "title": f"{primary['label']}: {dim_a['label']} × {dim_b['label']}",
            "description": "Density across the two leading dimensions.",
            "query_ref": query_id,
            "encoding": {"x": dim_b["name"], "y": dim_a["name"], "value": primary["name"]},
            "layout": {"x": 0, "y": row, "w": 6, "h": 4},
            "interactions": {"cross_filter": False, "click_to_ask": True},
            "options": {"palette": "sequential"},
        })

    table_metrics = [m["name"] for m in _pick_kpis(semantic, count=5) if m["aggregation"] != "RATIO"][:4]
    if dim_a and table_metrics:
        query_id = "detail_table"
        group = dim_a["name"]
        queries[query_id] = QuerySpec(
            metrics=table_metrics,
            group_by=[group],
            order_by={"field": table_metrics[0], "direction": "desc"},
            limit=25,
        ).model_dump()
        add_widget({
            "id": "detail_table",
            "type": "data_table",
            "title": f"Performance detail by {dim_a['label']}",
            "description": "Full metric breakdown with exportable rows.",
            "query_ref": query_id,
            "encoding": {"columns": [group, *table_metrics]},
            "layout": {"x": 6, "y": row, "w": 6, "h": 4} if dim_b else {"x": 0, "y": row, "w": 12, "h": 4},
            "interactions": {"cross_filter": False, "click_to_ask": False},
            "options": {"sort": "desc"},
        })
    row += 4

    filters: list[dict] = []
    categorical = dimensions
    if categorical:
        filters.append({
            "id": f"{categorical[0]['name']}_filter",
            "label": categorical[0]["label"],
            "field": categorical[0]["name"],
            "type": "categorical",
        })
    if len(categorical) > 1:
        filters.append({
            "id": f"{categorical[1]['name']}_filter",
            "label": categorical[1]["label"],
            "field": categorical[1]["name"],
            "type": "categorical",
        })
    if times:
        filters.append({
            "id": "date_range",
            "label": times[0]["label"],
            "field": times[0]["name"],
            "type": "date_range",
            "default_value": _default_window(times[0]),
        })

    return {
        "title": "Business performance overview",
        "description": "Automatically generated from the approved semantic model.",
        "queries": queries,
        "widgets": widgets,
        "filters": filters,
    }


def _llm_plan(semantic: dict) -> tuple[dict, dict]:
    if not llm.llm_available():
        return {}, {"provider": "deterministic", "reason": "GEMINI_API_KEY not configured"}
    metric_lines = [
        f"- {m['name']} ({m['label']}, {m['aggregation']}, {m.get('format', 'number')})"
        for m in semantic.get("metrics", [])
    ]
    dim_lines = [
        f"- {d['name']} ({d['label']}, {d['data_type']}, {d.get('unique_count', 'unknown')} values)"
        for d in semantic.get("dimensions", [])
    ]
    time_lines = [f"- {t['name']} ({t['label']}, default grain {t.get('default_grain')})"
                  for t in semantic.get("time_dimensions", [])]
    prompt = (
        "Design an executive dashboard for this dataset. Choose trusted widget templates only.\n"
        f"Metrics:\n{chr(10).join(metric_lines)}\nDimensions:\n{chr(10).join(dim_lines)}\n"
        f"Time dimensions:\n{chr(10).join(time_lines) or '- none'}\n\n"
        "Return JSON: {\"title\": str, \"description\": str, \"widgets\": [{\"type\": one of "
        "[kpi,line_chart,bar_chart,area_chart,pie_chart,donut_chart,scatter_chart,data_table,heatmap], "
        "\"title\": str, \"metric\": str, \"metrics\": [str], \"dimension\": str, \"dimension2\": str, "
        "\"grain\": str, \"limit\": int}]}. "
        "Use 3-5 KPI widgets, one trend line chart, one bar chart by a categorical dimension, "
        "one donut for composition, one data table, and optionally a heatmap using two dimensions. "
        "Only use metric and dimension names exactly as provided."
    )
    plan, result = llm.generate_structured(prompt, PlannerPlan, trace_name="dashboard.planner")
    if plan is None:
        return {}, {"provider": "deterministic", "reason": result.error or "llm_unavailable"}
    return plan.model_dump(), {"provider": "gemini", "model": result.model, "tokens": result.tokens}


def _translate_llm_plan(plan: dict, semantic: dict) -> dict:
    """Map an LLM plan onto trusted templates. Invalid picks are skipped."""
    metrics = {m["name"]: m for m in semantic.get("metrics", [])}
    dims = {d["name"]: d for d in semantic.get("dimensions", [])}
    times = {t["name"]: t for t in semantic.get("time_dimensions", [])}
    queries: dict[str, dict] = {}
    widgets: list[dict] = []
    row = 0
    kpi_index = 0

    for idx, item in enumerate(plan.get("widgets", [])[:10]):
        wtype = item.get("type")
        metric_name = item.get("metric") if item.get("metric") in metrics else None
        metric_set = [m for m in item.get("metrics", []) if m in metrics]
        if not metric_name and not metric_set:
            continue
        chosen = metric_set or [metric_name]
        dim_name = item.get("dimension") if item.get("dimension") in dims else None
        time_name = item.get("dimension") if item.get("dimension") in times else None
        dim2 = item.get("dimension2") if item.get("dimension2") in dims else None
        slug = re.sub(r"[^a-z0-9_]", "_", f"{wtype}_{idx}")[:60]
        title = (item.get("title") or f"{metrics[chosen[0]]['label']}")[:120]

        try:
            if wtype == "kpi":
                metric = metrics[chosen[0]]
                qid = f"kpi_{slug}"
                queries[qid] = QuerySpec(metrics=[metric["name"]], limit=1).model_dump()
                widgets.append({
                    "id": slug, "type": "kpi", "title": title,
                    "description": metric.get("description", "")[:200], "query_ref": qid,
                    "encoding": {"value": metric["name"]},
                    "layout": {"x": (kpi_index % 4) * 3, "y": row, "w": 3, "h": 2},
                    "interactions": {"cross_filter": False, "click_to_ask": True},
                    "options": {"value_format": metric.get("format", "number"), "compare": "previous_period"},
                })
                kpi_index += 1
                continue
            if wtype in ("line_chart", "area_chart") and time_name:
                td = times[time_name]
                qid = f"trend_{slug}"
                queries[qid] = QuerySpec(
                    metrics=chosen, group_by=[time_name], grain=item.get("grain") or td.get("default_grain", "month"),
                    order_by={"field": time_name, "direction": "asc"}, limit=60,
                ).model_dump()
                widgets.append({
                    "id": slug, "type": wtype, "title": title, "description": "",
                    "query_ref": qid, "encoding": {"x": time_name, "y": chosen},
                    "layout": {"x": 0, "y": max(row, 2), "w": 8, "h": 4},
                    "interactions": {"cross_filter": True, "click_to_ask": True},
                    "options": {"palette": "brand"},
                })
                row = max(row, 2) + 4
                continue
            if wtype in ("bar_chart", "pie_chart", "donut_chart") and dim_name:
                qid = f"dim_{slug}"
                queries[qid] = QuerySpec(
                    metrics=chosen, group_by=[dim_name],
                    order_by={"field": chosen[0], "direction": "desc"}, limit=item.get("limit") or 10,
                ).model_dump()
                encoding = (
                    {"x": dim_name, "y": chosen}
                    if wtype == "bar_chart"
                    else {"label": dim_name, "value": chosen[0]}
                )
                widgets.append({
                    "id": slug, "type": wtype, "title": title, "description": "",
                    "query_ref": qid, "encoding": encoding,
                    "layout": {"x": 0, "y": row, "w": 6, "h": 4},
                    "interactions": {"cross_filter": True, "click_to_ask": True},
                    "options": {"palette": "categorical"},
                })
                row += 4
                continue
            if wtype == "heatmap" and dim_name and dim2:
                qid = f"heat_{slug}"
                queries[qid] = QuerySpec(
                    metrics=chosen, group_by=[dim_name, dim2],
                    order_by={"field": chosen[0], "direction": "desc"}, limit=80,
                ).model_dump()
                widgets.append({
                    "id": slug, "type": "heatmap", "title": title, "description": "",
                    "query_ref": qid, "encoding": {"x": dim2, "y": dim_name, "value": chosen[0]},
                    "layout": {"x": 0, "y": row, "w": 6, "h": 4},
                    "interactions": {"cross_filter": False, "click_to_ask": True},
                    "options": {"palette": "sequential"},
                })
                row += 4
                continue
            if wtype == "data_table" and dim_name:
                qid = f"table_{slug}"
                queries[qid] = QuerySpec(
                    metrics=chosen, group_by=[dim_name],
                    order_by={"field": chosen[0], "direction": "desc"}, limit=25,
                ).model_dump()
                widgets.append({
                    "id": slug, "type": "data_table", "title": title, "description": "",
                    "query_ref": qid, "encoding": {"columns": [dim_name, *chosen]},
                    "layout": {"x": 6, "y": max(row - 4, 0), "w": 6, "h": 4},
                    "interactions": {"cross_filter": False, "click_to_ask": False},
                    "options": {"sort": "desc"},
                })
                continue
        except Exception:  # noqa: BLE001 - skip malformed widget, keep the rest
            continue

    if len(widgets) < 3:
        return {}
    return {"title": plan.get("title") or "Business performance overview",
            "description": plan.get("description") or "Generated from the approved semantic model.",
            "queries": queries, "widgets": widgets, "filters": []}


def generate_dashboard_spec(
    dataset_id: str,
    semantic: dict,
    mode: str = "review",
    dashboard_id: str | None = None,
) -> tuple[dict | None, dict]:
    """Return (validated_spec, report). Falls back to the deterministic plan."""
    base = deterministic_plan(semantic)
    report: dict = {"mode": mode, "provider": "deterministic"}
    plan_override, llm_meta = _llm_plan(semantic)
    report["llm"] = llm_meta
    if plan_override:
        translated = _translate_llm_plan(plan_override, semantic)
        if translated:
            base = translated
            report["provider"] = "gemini"
            report["llm_plan"] = {
                "title": plan_override.get("title"),
                "widgets": [w.get("type") for w in plan_override.get("widgets", [])],
            }

    spec = {
        "schema_version": "1.0",
        "dashboard_id": dashboard_id,
        "title": base.get("title") or "Business performance overview",
        "description": base.get("description") or "",
        "dataset_id": dataset_id,
        "semantic_model_version": semantic.get("version", 1),
        "generation_mode": mode,
        "layout": {"columns": 12, "gap": 16, "density": "comfortable"},
        "filters": base.get("filters", []),
        "queries": {k: v for k, v in base.get("queries", {}).items()},
        "widgets": base.get("widgets", []),
        "metadata": {
            "created_by": "dashboard_planner",
            "provider": report["provider"],
            "version": 1,
        },
    }
    validated, validation = validate_dashboard_spec(spec, semantic)
    report["validation"] = validation.model_dump()
    if validated is None:
        # Last-resort deterministic rebuild without LLM involvement.
        spec["widgets"] = deterministic_plan(semantic)["widgets"]
        spec["queries"] = deterministic_plan(semantic)["queries"]
        spec["metadata"]["provider"] = "deterministic_fallback"
        validated, validation = validate_dashboard_spec(spec, semantic)
        report["validation"] = validation.model_dump()
        report["provider"] = "deterministic_fallback"
    return validated, report
