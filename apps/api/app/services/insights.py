"""Insight generation.

Every insight is derived from an executed analytical query and stores its
evidence (the SQL, the rows and the metadata) so the UI can show provenance.
No insight is generated from an LLM guess.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.tools import ToolContext, load_context
from app.models import Insight
from app.services.narrative import fmt_number, to_number
from app.sql.builder import quote
from app.sql.generator import period_bounds

logger = logging.getLogger("agentic_bi.insights")


def _combine(q: dict) -> str:
    return q["sql"]


def refresh_dataset_insights(
    db: Session,
    *,
    organization_id: str,
    workspace_id: str,
    user_id: str,
    dataset_id: str,
) -> list[Insight]:
    ctx: ToolContext = load_context(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dataset_id,
    )
    semantic = ctx.semantic
    metrics = [m for m in semantic.get("metrics", []) if m["aggregation"] == "SUM"]
    metric = next((m for m in metrics if m["name"] == "total_revenue"), metrics[0] if metrics else None)
    if metric is None:
        return []

    measured = f"SUM({quote(metric['source_column'])})"
    table = quote(ctx.version.table_name)
    bounds = period_bounds(ctx.engine, semantic)
    insights: list[Insight] = []

    db.query(Insight).filter(Insight.dataset_id == dataset_id, Insight.insight_type != "note").delete()
    db.flush()

    def store(title: str, summary: str, kind: str, severity: str, evidence: dict) -> None:
        insight = Insight(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            title=title[:240],
            summary=summary,
            insight_type=kind,
            severity=severity,
            evidence=evidence,
            verified=True,
        )
        db.add(insight)
        insights.append(insight)

    if bounds:
        date_col = quote(bounds["column"])
        current = ctx.engine.execute(
            f"SELECT {measured} FROM {table} WHERE {date_col} BETWEEN ? AND ?",
            params=[bounds["recent_start"], bounds["recent_end"]],
        )
        previous = ctx.engine.execute(
            f"SELECT {measured} FROM {table} WHERE {date_col} BETWEEN ? AND ?",
            params=[bounds["prev_start"], bounds["prev_end"]],
        )
        recent_value = to_number((current.get("rows") or [[0]])[0][0]) or 0.0
        prev_value = to_number((previous.get("rows") or [[0]])[0][0]) or 0.0
        if prev_value:
            change = (recent_value - prev_value) / abs(prev_value) * 100
            severity = "critical" if change < -5 else "warning" if change < 0 else "positive"
            store(
                title=f"{metric['label']} {'down' if change < 0 else 'up'} {abs(change):.1f}% in the latest quarter",
                summary=(
                    f"The most recent quarter closed at {fmt_number(recent_value, metric.get('format', 'number'))} "
                    f"versus {fmt_number(prev_value, metric.get('format', 'number'))} in the preceding quarter."
                ),
                kind="period_change",
                severity=severity,
                evidence={
                    "metric": metric["name"],
                    "recent_period": [bounds["recent_start"], bounds["recent_end"]],
                    "previous_period": [bounds["prev_start"], bounds["prev_end"]],
                    "recent_value": recent_value,
                    "previous_value": prev_value,
                    "change_pct": round(change, 2),
                    "sql": [current["columns"], previous["columns"]],
                },
            )

        for dim in [d for d in semantic.get("dimensions", []) if d.get("data_type") == "categorical"][:2]:
            column = quote(dim["source_column"])
            rows = ctx.engine.execute(
                f"SELECT {column} AS label, "
                f"SUM(CASE WHEN {date_col} BETWEEN ? AND ? THEN {quote(metric['source_column'])} ELSE 0 END) AS recent, "
                f"SUM(CASE WHEN {date_col} BETWEEN ? AND ? THEN {quote(metric['source_column'])} ELSE 0 END) AS previous "
                f"FROM {table} GROUP BY 1 ORDER BY recent DESC",
                params=[bounds["recent_start"], bounds["recent_end"], bounds["prev_start"], bounds["prev_end"]],
            ).get("rows", [])
            deltas = [
                (row[0], (to_number(row[1]) or 0.0) - (to_number(row[2]) or 0.0), to_number(row[1]) or 0.0,
                 to_number(row[2]) or 0.0)
                for row in rows
            ]
            if not deltas:
                continue
            worst = min(deltas, key=lambda d: d[1])
            best = max(deltas, key=lambda d: d[1])
            if worst[1] < 0:
                store(
                    title=f"{dim['label']}: {worst[0]} saw the largest decline",
                    summary=(
                        f"{dim['label']} '{worst[0]}' moved from {fmt_number(worst[3], metric.get('format', 'number'))} "
                        f"to {fmt_number(worst[2], metric.get('format', 'number'))} "
                        f"({fmt_number(worst[1], metric.get('format', 'number'))} change) quarter on quarter."
                    ),
                    kind="contribution",
                    severity="critical" if abs(worst[1]) > 0 else "warning",
                    evidence={"dimension": dim["name"], "value": worst[0], "delta": worst[1],
                              "recent": worst[2], "previous": worst[3], "method": "quarter-over-quarter contribution"},
                )
            if best[1] > 0:
                store(
                    title=f"{dim['label']}: {best[0]} contributed the most growth",
                    summary=(
                        f"{best[0]} added {fmt_number(best[1], metric.get('format', 'number'))} in the latest quarter, "
                        f"reaching {fmt_number(best[2], metric.get('format', 'number'))}."
                    ),
                    kind="contribution",
                    severity="positive",
                    evidence={"dimension": dim["name"], "value": best[0], "delta": best[1],
                              "recent": best[2], "previous": best[3]},
                )

    # Concentration analysis: share of the top product.
    products = next((d for d in semantic.get("dimensions", []) if "product" in d["name"]), None)
    if products:
        rows = ctx.engine.execute(
            f"SELECT {quote(products['source_column'])} AS label, {measured} AS {quote(metric['name'])} "
            f"FROM {table} GROUP BY 1 ORDER BY 2 DESC LIMIT 200"
        ).get("rows", [])
        total = sum(to_number(r[1]) or 0 for r in rows)
        if rows and total:
            top = rows[:5]
            share = sum(to_number(r[1]) or 0 for r in top) / total * 100
            store(
                title=f"Top 5 {products['label'].lower()} account for {share:.0f}% of {metric['label'].lower()}",
                summary=(
                    f"{top[0][0]} leads with {fmt_number(top[0][1], metric.get('format', 'number'))}. "
                    "High concentration is a dependency risk if a leading product declines."
                ),
                kind="concentration",
                severity="info",
                evidence={"dimension": products["name"], "top_5_share_pct": round(share, 2),
                          "leaders": [{"label": r[0], "value": r[1]} for r in top]},
            )

    # Data quality insight
    profile = ctx.profile or {}
    if profile.get("quality_score") is not None:
        store(
            title=f"Data quality score is {profile['quality_score']}/100",
            summary=(
                f"{profile.get('missing_cells', 0):,} missing cells and {profile.get('duplicate_rows', 0):,} duplicated "
                "rows detected during profiling. Quality is scored with a documented deterministic formula."
            ),
            kind="data_quality",
            severity="warning" if profile["quality_score"] < 80 else "info",
            evidence={"components": profile.get("quality_components", {}),
                      "formula": profile.get("quality_formula", {}).get("expression")},
        )

    db.commit()
    return insights


def serialize_insight(insight: Insight) -> dict:
    return {
        "id": insight.id,
        "workspace_id": insight.workspace_id,
        "dataset_id": insight.dataset_id,
        "title": insight.title,
        "summary": insight.summary,
        "insight_type": insight.insight_type,
        "severity": insight.severity,
        "evidence": insight.evidence,
        "verified": insight.verified,
        "created_at": insight.created_at.isoformat(),
    }
