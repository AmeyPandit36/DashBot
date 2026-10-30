"""Deterministic narrative composition and number formatting.

Answers are composed from executed query results only. When Gemini is enabled
it may rewrite the narrative, but the verifier re-checks every number against
the result set and a deterministic narrative is used if grounding fails.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

CURRENCY = "₹"


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace(CURRENCY, "").replace("$", "").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def fmt_number(value: Any, fmt: str = "number") -> str:
    number = to_number(value)
    if number is None:
        return "—"
    if fmt == "percent":
        # Ratio columns (e.g. discount rates) are stored as fractions.
        return f"{number * 100:.1f}%"
    if fmt in ("currency", "decimal"):
        sign = "-" if number < 0 else ""
        magnitude = abs(number)
        if magnitude >= 1_000_000:
            body = f"{magnitude / 1_000_000:,.2f}M"
        elif magnitude >= 1_000:
            body = f"{magnitude:,.0f}"
        elif fmt == "currency" and magnitude >= 100:
            body = f"{magnitude:,.0f}"
        else:
            body = f"{magnitude:,.2f}"
        return f"{sign}{CURRENCY if fmt == 'currency' else ''}{body}"
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}"
    return f"{number:,.2f}"


def fmt_plain(value: Any) -> str:
    number = to_number(value)
    if number is None:
        return "—"
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}"
    return f"{number:,.2f}"


def fmt_date(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%b %Y") if isinstance(value, (date, datetime)) else str(value)
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text[:10])
        return parsed.strftime("%b %Y")
    except ValueError:
        return text


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "")[:10]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def fmt_period(value: Any, grain: str | None = None) -> str:
    """Format a period label according to the grain that produced it."""
    stamp = parse_date(value)
    if stamp is None:
        return fmt_date(value)
    if grain == "quarter":
        return f"Q{((stamp.month - 1) // 3) + 1} {stamp.year}"
    if grain == "year":
        return str(stamp.year)
    if grain == "week":
        return f"week of {stamp.strftime('%d %b %Y')}"
    if grain == "day":
        return stamp.strftime("%d %b %Y")
    return stamp.strftime("%b %Y")


def _metric_meta(plan: dict, semantic: dict) -> dict[str, dict]:
    return {m["name"]: m for m in semantic.get("metrics", [])}


def _pct_change(current: float, previous: float) -> float | None:
    if previous in (0, None):
        return None
    return (current - previous) / abs(previous) * 100


def compose_aggregate(result: dict, plan: dict, semantic: dict) -> dict:
    metrics = _metric_meta(plan, semantic)
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not rows:
        return {"answer": "No rows matched this analysis. The dataset may not contain data for that selection.",
                "summary": "No data returned.", "insights": []}
    row = rows[0]
    parts = []
    for idx, column in enumerate(columns):
        metric = metrics.get(column, {})
        parts.append(f"**{metric.get('label', column)}** is {fmt_number(row[idx], metric.get('format', 'number'))}")
    value_text = "; ".join(parts)
    answer = f"{value_text}."
    if metrics.get(columns[0], {}).get("requires_approval"):
        answer += " This metric's business definition is still marked for approval in the semantic model."
    return {
        "answer": answer,
        "summary": value_text,
        "insights": [{"title": metric_label(semantic, col), "detail": fmt_number(row[i], metrics.get(col, {}).get("format", "number"))}
                     for i, col in enumerate(columns)],
    }


def metric_label(semantic: dict, name: str) -> str:
    for metric in semantic.get("metrics", []):
        if metric["name"] == name:
            return metric.get("label", name)
    return name.replace("_", " ").title()


def compose_group(result: dict, plan: dict, semantic: dict) -> dict:
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not rows or not columns:
        return {"answer": "No rows were returned for this breakdown.", "summary": "No data.", "insights": []}
    dimension = columns[0]
    metric_name = columns[1] if len(columns) > 1 else columns[0]
    metric = next((m for m in semantic.get("metrics", []) if m["name"] == metric_name), {})
    label = metric.get("label", metric_name)
    dim_label = next((d.get("label", d["name"]) for d in semantic.get("dimensions", []) if d["name"] == dimension),
                     dimension.replace("_", " ").title())
    fmt = metric.get("format", "number")

    ordered = sorted(rows, key=lambda r: (to_number(r[1]) or 0), reverse=True)
    top = ordered[0]
    bottom = ordered[-1]
    total = sum((to_number(r[1]) or 0) for r in ordered)
    share = (to_number(top[1]) or 0) / total * 100 if total else None
    answer = (
        f"**{top[0]}** leads on {label.lower()} with {fmt_number(top[1], fmt)}"
        + (f", which is {share:.1f}% of the {fmt_number(total, fmt)} total" if share is not None else "")
        + f". {bottom[0]} is lowest at {fmt_number(bottom[1], fmt)} across {len(ordered)} {dim_label.lower()} values."
    )
    if len(ordered) >= 2:
        leader, runner_up = ordered[0], ordered[1]
        gap = (to_number(leader[1]) or 0) - (to_number(runner_up[1]) or 0)
        answer += f" The gap to {runner_up[0]} is {fmt_number(gap, fmt)}."
    insights = [
        {"title": f"Leader: {top[0]}", "detail": f"{fmt_number(top[1], fmt)} ({share:.1f}% share)" if share is not None else fmt_number(top[1], fmt), "severity": "info"},
        {"title": f"Lowest: {bottom[0]}", "detail": fmt_number(bottom[1], fmt), "severity": "info"},
    ]
    return {"answer": answer, "summary": f"{label} by {dim_label}", "insights": insights}


def compose_timeseries(result: dict, plan: dict, semantic: dict) -> dict:
    grain = plan.get("grain")
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if len(rows) < 1:
        return {"answer": "There are no data points in that time range.", "summary": "No data.", "insights": []}
    time_col = columns[0]
    metric_name = columns[1] if len(columns) > 1 else columns[0]
    metric = next((m for m in semantic.get("metrics", []) if m["name"] == metric_name), {})
    fmt = metric.get("format", "number")
    label = metric.get("label", metric_name)
    series = [(row[0], to_number(row[1]) or 0.0) for row in rows if row[1] is not None]
    if not series:
        return {"answer": "The selected metric has no values in that range.", "summary": "No data.", "insights": []}
    peak = max(series, key=lambda p: p[1])
    trough = min(series, key=lambda p: p[1])
    first, last = series[0], series[-1]
    change = _pct_change(last[1], first[1])
    direction = "increased" if change and change > 0 else "decreased" if change and change < 0 else "remained flat"
    answer = (
        f"{label} {direction}"
        + (f" by {abs(change):.1f}% " if change is not None else " ")
        + f"between {fmt_period(first[0], grain)} and {fmt_period(last[0], grain)}: from {fmt_number(first[1], fmt)} to {fmt_number(last[1], fmt)}. "
        f"The peak was {fmt_period(peak[0], grain)} at {fmt_number(peak[1], fmt)}; the low point was "
        f"{fmt_period(trough[0], grain)} at {fmt_number(trough[1], fmt)}."
    )
    insights = [
        {"title": f"Peak in {fmt_period(peak[0], grain)}", "detail": fmt_number(peak[1], fmt), "severity": "info"},
        {"title": f"Lowest in {fmt_period(trough[0], grain)}", "detail": fmt_number(trough[1], fmt), "severity": "warning"},
    ]
    if len(series) >= 2:
        recent = series[-1]
        prior = series[-2]
        recent_change = _pct_change(recent[1], prior[1])
        if recent_change is not None and recent_change <= -5:
            insights.append({
                "title": f"Latest period down {abs(recent_change):.1f}%",
                "detail": f"{fmt_period(recent[0], grain)} vs {fmt_period(prior[0], grain)}",
                "severity": "warning",
            })
    return {"answer": answer, "summary": f"{label} trend, {len(series)} periods", "insights": insights}


def compose_decomposition(results: list[dict], plan: dict, semantic: dict) -> dict:
    """Explain a change using the period comparison and dimension decompositions."""
    trend = next((r for r in results if r.get("role") == "trend"), None)
    totals = next((r for r in results if r.get("role") == "totals"), None)
    dims = [r for r in results if r.get("role") == "dimension"]
    metric_name = (plan.get("metrics") or ["total_revenue"])[0]
    metric = next((m for m in semantic.get("metrics", []) if m["name"] == metric_name), {})
    fmt = metric.get("format", "number")
    label = metric.get("label", metric_name)
    insights = []
    answer_parts: list[str] = []

    change_text = ""
    if totals and (totals.get("result") or {}).get("rows"):
        totals_rows = totals["result"]["rows"]
        recent = to_number(totals_rows[0][0])
        previous = to_number(totals_rows[0][1])
        if recent is not None and previous is not None:
            delta = recent - previous
            pct = _pct_change(recent, previous)
            direction = "decreased" if delta < 0 else "increased" if delta > 0 else "was flat"
            change_text = (
                f"{label} {direction} to {fmt_number(recent, fmt)} in the latest quarter"
                + (f" ({pct:+.1f}% vs {fmt_number(previous, fmt)})" if pct is not None else "")
                + f", a change of {fmt_number(delta, fmt)}."
            )
            answer_parts.append(change_text)
            insights.append({
                "title": f"Latest quarter: {fmt_number(recent, fmt)}",
                "detail": f"Change of {fmt_number(delta, fmt)} vs previous quarter",
                "severity": "warning" if delta < 0 else "positive",
            })

    contributions: list[dict] = []
    for dim_result in dims:
        rows = (dim_result.get("result") or {}).get("rows", [])
        if not rows:
            continue
        for row in rows:
            name, recent, previous = row[0], to_number(row[1]) or 0.0, to_number(row[2]) or 0.0
            contributions.append({
                "dimension": dim_result.get("dimension_label") or dim_result.get("dimension", "segment"),
                "value": name,
                "delta": recent - previous,
                "recent": recent,
                "previous": previous,
            })

    if contributions:
        negative = sorted([c for c in contributions if c["delta"] < 0], key=lambda c: c["delta"])
        positive = sorted([c for c in contributions if c["delta"] > 0], key=lambda c: c["delta"], reverse=True)
        if negative:
            worst = negative[:3]
            detail = ", ".join(
                f"{c['value']} ({fmt_number(c['delta'], fmt)})" for c in worst
            )
            answer_parts.append(
                f"The largest declines came from {worst[0]['dimension'].lower()}: {detail}."
            )
            insights.append({
                "title": f"Biggest drag: {worst[0]['value']}",
                "detail": f"{fmt_number(worst[0]['delta'], fmt)} change in {worst[0]['dimension'].lower()}",
                "severity": "critical",
            })
        if positive:
            best = positive[0]
            answer_parts.append(
                f"{best['value']} partly offset this with {fmt_number(best['delta'], fmt)} of growth."
            )
            insights.append({
                "title": f"Offsetting growth: {best['value']}",
                "detail": f"{fmt_number(best['delta'], fmt)} change",
                "severity": "positive",
            })

    if trend and (trend.get("result") or {}).get("rows"):
        series = [(r[0], to_number(r[1]) or 0.0) for r in trend["result"]["rows"]]
        if len(series) >= 2:
            last, prior = series[-1], series[-2]
            pct = _pct_change(last[1], prior[1])
            answer_parts.append(
                f"The monthly series shows {fmt_date(last[0])} at {fmt_number(last[1], fmt)}"
                + (f", {pct:+.1f}% month on month." if pct is not None else ".")
            )
            insights.append({
                "title": f"Monthly movement in {fmt_date(last[0])}",
                "detail": f"{pct:+.1f}% vs previous month" if pct is not None else "no prior month",
                "severity": "info",
            })

    if not answer_parts:
        answer_parts.append("The analysis ran successfully but the movement could not be decomposed from the available rows.")

    answer = " ".join(answer_parts)
    answer += " Causes shown are statistical contributions from the data, not proven business causality."
    return {"answer": answer, "summary": change_text or "Change decomposition", "insights": insights}


def follow_ups(semantic: dict, plan: dict) -> list[str]:
    suggestions: list[str] = []
    dims = [d for d in semantic.get("dimensions", []) if d.get("data_type") != "identifier"]
    times = semantic.get("time_dimensions", [])
    metrics = [m for m in semantic.get("metrics", []) if m["aggregation"] != "RATIO"][:3]
    if dims and metrics:
        suggestions.append(f"{metrics[0]['label']} by {dims[0]['label'].lower()}")
    if times:
        suggestions.append(f"Show the monthly trend of {metrics[0]['label'].lower() if metrics else 'revenue'}")
    if len(dims) > 1 and metrics:
        suggestions.append(f"Break down {metrics[0]['label'].lower()} by {dims[1]['label'].lower()}")
    if metrics:
        suggestions.append(f"Why did {metrics[0]['label'].lower()} change recently?")
    suggestions.append("What are the major business insights?")
    return suggestions[:4]


def _add_scaled(pool: set[float], number: float) -> None:
    """Register a value and the forms it can legitimately take after formatting."""
    for scaled in (number, number / 1e3, number / 1e6, number / 1e9, number * 100):
        pool.add(round(scaled, 6))
        pool.add(round(scaled, 2))
        pool.add(round(scaled, 1))
        pool.add(round(scaled, 4))


def numeric_pool(results: list[dict]) -> set[float]:
    """All numbers a verified answer is allowed to cite, including derived values.

    Derived values recomputed here from the evidence: totals, shares, deltas,
    adjacent-period percentage changes and endpoint changes of a series.
    """
    pool: set[float] = {0.0, 100.0}
    for result in results:
        rows = result.get("rows") or []
        numeric_by_col: dict[int, list[float]] = {}
        for row in rows:
            for idx, value in enumerate(row):
                number = to_number(value)
                if number is not None:
                    _add_scaled(pool, number)
                    _add_scaled(pool, abs(number))
                    numeric_by_col.setdefault(idx, []).append(number)
        for idx, values in numeric_by_col.items():
            total = sum(values)
            _add_scaled(pool, total)
            _add_scaled(pool, abs(total))
            for value in values:
                if total:
                    _add_scaled(pool, value / total * 100)
                if abs(value) < 1:
                    _add_scaled(pool, value * 100)
            # Deltas and percentage changes across the series (bounded work).
            if len(values) <= 400:
                for previous, current in zip(values, values[1:]):
                    _add_scaled(pool, current - previous)
                    if previous:
                        _add_scaled(pool, (current - previous) / abs(previous) * 100)
                if len(values) >= 2 and values[0]:
                    _add_scaled(pool, values[-1] - values[0])
                    _add_scaled(pool, (values[-1] - values[0]) / abs(values[0]) * 100)
            # Cross-column deltas (recent vs previous, revenue vs target, ...).
            for other_idx, other_values in numeric_by_col.items():
                if other_idx <= idx or len(other_values) != len(values):
                    continue
                for a, b in zip(values, other_values):
                    _add_scaled(pool, a - b)
                    if b:
                        _add_scaled(pool, (a - b) / abs(b) * 100)
                break
    return pool


def compose_metadata(profile: dict, semantic: dict, dataset_name: str) -> dict:
    score = profile.get("quality_score")
    columns = profile.get("column_count", 0)
    rows = profile.get("row_count", 0)
    nulls = profile.get("missing_cells", 0)
    dates = profile.get("date_columns") or []
    answer = (
        f"**{dataset_name}** contains {rows:,} rows and {columns} columns"
        + (f", with a data quality score of {score}/100" if score is not None else "")
        + f". {nulls:,} cells are missing and {profile.get('duplicate_rows', 0):,} rows are exact duplicates."
    )
    if dates:
        answer += f" The primary time dimension is `{dates[0]}`."
    return {
        "answer": answer,
        "summary": "Dataset profile",
        "insights": [
            {"title": "Quality score", "detail": f"{score}/100", "severity": "info" if (score or 0) >= 80 else "warning"},
            {"title": "Rows", "detail": f"{rows:,}", "severity": "info"},
        ],
    }
