"""Question planning and SQL generation for the analytical agent.

Two paths, identical safety envelope:
1. **Gemini path** — the LLM writes a single SELECT against the dataset view.
   It is parsed, policy-checked, executed read-only and verified.
2. **Deterministic path** — a rule-based planner maps the question onto the
   approved semantic model and the declarative query builder. This path is used
   when no Gemini key is configured and as the recovery path when the LLM output
   fails validation.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.agents import llm
from app.core.errors import AppError
from app.semantic.inference import humanize
from app.sql.builder import QuerySpec, build_query, quote

DEFINITION_PATTERNS = (
    "what does", "what is the meaning", "meaning of", "define ", "definition of",
    "how is", "how are", "calculated", "stand for", "explain the metric",
)
META_PATTERNS = (
    "how many rows", "how many columns", "what columns", "which columns", "describe the dataset",
    "data quality", "quality score", "missing values", "null values", "dataset schema",
    "what data", "data profile",
)
DECOMPOSE_PATTERNS = (
    "why", "decline", "decrease", "decreased", "drop", "dropped", "increase", "increased",
    "growth", "grew", "driver", "root cause", "explain", "what happened", "behind",
)
UNSUPPORTED_PATTERNS = (
    "forecast", "predict", "prediction", "write a", "create table", "delete ", "drop table",
    "update the", "insert into", "weather", "stock price", "send email", "browse",
)
TREND_PATTERNS = ("trend", "over time", "by month", "monthly", "weekly", "daily", "quarterly",
                  "yearly", "over the last", "last 12", "time series", "seasonality")
GRAIN_HINTS = {"daily": "day", "day": "day", "weekly": "week", "week": "week", "monthly": "month",
               "month": "month", "quarterly": "quarter", "quarter": "quarter", "yearly": "year", "year": "year"}

METRIC_SYNONYMS = {
    "revenue": ["total_revenue", "revenue", "sales", "amount", "income", "turnover"],
    "sales": ["total_revenue", "revenue", "sales"],
    "orders": ["total_orders", "orders", "order count"],
    "order": ["total_orders"],
    "customers": ["unique_customers", "customers", "customer count"],
    "units": ["total_quantity", "quantity", "units", "volume"],
    "quantity": ["total_quantity"],
    "aov": ["average_order_value"],
    "basket": ["average_order_value"],
    "price": ["average_selling_price", "avg_unit_price"],
    "discount": ["avg_discount"],
    "products": ["unique_products"],
}


def _tokens(text: str) -> set[str]:
    return set(llm.tokenize(text))


CONTEXT_PATTERNS = (
    "policy", "policies", "contract", "contracts", "handbook", "playbook", "rule", "rules",
    "document", "documents", "note", "notes", "glossary", "refund", "refunds", "definition",
    "define", "meaning",
)


def classify_intent(question: str, semantic: dict) -> str:
    q = question.lower()
    if any(p in q for p in UNSUPPORTED_PATTERNS):
        return "unsupported"
    if any(p in q for p in META_PATTERNS):
        return "dataset_metadata"
    if any(p in q for p in DEFINITION_PATTERNS):
        # "what is total revenue" is numerical; definitions explicitly talk about meaning.
        if any(word in q for word in ("mean", "meaning", "definition", "define", "calculated", "stand for")):
            return "definition"
    if any(p in q for p in CONTEXT_PATTERNS):
        return "business_context"
    if any(p in q for p in DECOMPOSE_PATTERNS):
        return "decomposition"
    if any(p in q for p in TREND_PATTERNS):
        return "timeseries"
    return "analytical_query"


def _score_metric(metric: dict, question: str) -> float:
    tokens = _tokens(question)
    score = 0.0
    name_tokens = set(llm.tokenize(metric["name"].replace("_", " ")))
    label_tokens = set(llm.tokenize(metric.get("label", "")))
    if tokens & name_tokens:
        score += 3 * len(tokens & name_tokens)
    if tokens & label_tokens:
        score += 1.5 * len(tokens & label_tokens)
    for trigger, targets in METRIC_SYNONYMS.items():
        if trigger in tokens and metric["name"] in targets:
            score += 4 if metric["name"] == targets[0] else 2
    if metric["name"] == "total_revenue" and ({"revenue", "sales", "money"} & tokens):
        score += 3
    # Multi-word business phrases outrank loose token overlap.
    if metric["name"] == "average_order_value" and any(
        phrase in question.lower() for phrase in ("order value", "aov", "basket", "order size")
    ):
        score += 8
    if metric["name"] == "average_selling_price" and any(
        phrase in question.lower() for phrase in ("selling price", "price per unit", "revenue per unit")
    ):
        score += 6
    return score


def select_metrics(question: str, semantic: dict) -> list[dict]:
    tokens = _tokens(question)
    metrics = semantic.get("metrics", [])
    scored = sorted(
        ((m, _score_metric(m, question)) for m in metrics), key=lambda x: x[1], reverse=True
    )
    top = [(m, s) for m, s in scored if s > 0][:3]
    if not top:
        preferred = {"total_revenue", "total_orders"}
        fallback = [m for m in metrics if m["name"] in preferred][:2] or metrics[:1]
        return fallback
    # Never mix additive and ratio metrics in one result: the totals would be
    # mathematically meaningless. Keep the family that best matches the question.
    ratios = [m for m, _ in top if m["aggregation"] == "RATIO"]
    additive = [m for m, _ in top if m["aggregation"] != "RATIO"]
    best_ratio = max((s for m, s in top if m["aggregation"] == "RATIO"), default=0.0)
    best_additive = max((s for m, s in top if m["aggregation"] != "RATIO"), default=0.0)
    if ratios and best_ratio >= best_additive - 0.5:
        return ratios[:2]
    return (additive or ratios)[:3]


def select_dimension(question: str, semantic: dict) -> dict | None:
    tokens = _tokens(question)
    best: tuple[dict | None, float] = (None, 0.0)
    for dim in semantic.get("dimensions", []):
        if dim.get("data_type") == "identifier":
            continue
        name_tokens = set(llm.tokenize(dim["name"].replace("_", " ")))
        label_tokens = set(llm.tokenize(dim.get("label", "")))
        score = len(tokens & name_tokens) * 2 + len(tokens & label_tokens)
        if dim["name"].endswith("s") and dim["name"][:-1] in tokens:
            score += 2
        if score > best[1]:
            best = (dim, score)
    return best[0]


def select_time(question: str, semantic: dict) -> dict | None:
    times = semantic.get("time_dimensions", [])
    if not times:
        return None
    tokens = _tokens(question)
    for td in times:
        if td["name"].replace("_", " ") in question.lower() or set(llm.tokenize(td["name"])) & tokens:
            return td
    return times[0]


def detect_top_n(question: str) -> int | None:
    match = re.search(r"\b(?:top|first|best|worst|highest|lowest)\s+(\d{1,2})\b", question.lower())
    if match:
        return max(1, min(50, int(match.group(1))))
    if re.search(r"\btop\b|\bbest\b|\bhighest\b|\blowest\b|\bworst\b", question.lower()):
        return 10
    return None


def detect_grain(question: str, default: str = "month") -> str:
    q = question.lower()
    for word, grain in GRAIN_HINTS.items():
        if re.search(rf"\b{word}\b", q):
            return grain
    return default


def plan_question(question: str, semantic: dict) -> dict:
    intent = classify_intent(question, semantic)
    metrics = select_metrics(question, semantic)
    dimension = select_dimension(question, semantic)
    time_dim = select_time(question, semantic)
    top_n = detect_top_n(question)
    grain = detect_grain(question, (time_dim or {}).get("default_grain", "month"))

    plan = {
        "intent": intent,
        "metrics": [m["name"] for m in metrics],
        "metric_labels": [m.get("label", m["name"]) for m in metrics],
        "dimension": dimension["name"] if dimension else None,
        "dimension_label": dimension.get("label") if dimension else None,
        "time_dimension": time_dim["name"] if time_dim else None,
        "time_label": time_dim.get("label") if time_dim else None,
        "grain": grain,
        "top_n": top_n,
        "reasoning": "Rule-based plan from the approved semantic model.",
    }

    if intent == "decomposition" and time_dim is None and (dimension is None):
        plan["intent"] = "analytical_query"

    if intent in ("definition", "dataset_metadata", "unsupported"):
        return plan
    if intent == "decomposition":
        plan["type"] = "decomposition"
    elif any(p in question.lower() for p in TREND_PATTERNS) and time_dim:
        plan["type"] = "timeseries"
    elif dimension:
        plan["type"] = "group"
        plan["limit"] = top_n or 10
    else:
        plan["type"] = "aggregate"
    return plan


def build_plan_query(plan: dict, semantic: dict, table_name: str) -> dict:
    """Build the primary SQL for a deterministic plan."""
    metrics = [m for m in plan.get("metrics", []) if m]
    if not metrics:
        raise AppError("NO_METRIC", "No metric could be matched to the question.", 422)
    if plan["type"] == "group":
        spec = QuerySpec(
            metrics=metrics,
            group_by=[plan["dimension"]],
            order_by={"field": metrics[0], "direction": "desc"},
            limit=plan.get("limit") or 10,
        )
        label = f"{plan['metric_labels'][0]} by {plan['dimension_label']}"
    elif plan["type"] == "timeseries":
        spec = QuerySpec(
            metrics=metrics,
            group_by=[plan["time_dimension"]],
            grain=plan.get("grain") or "month",
            order_by={"field": plan["time_dimension"], "direction": "asc"},
            limit=120,
        )
        label = f"{plan['metric_labels'][0]} by {plan.get('grain')}"
    else:
        spec = QuerySpec(metrics=metrics, limit=1)
        label = ", ".join(plan["metric_labels"])
    sql, params, columns = build_query(spec, semantic, table_name)
    return {"label": label, "sql": sql, "params": params, "columns": columns, "spec": spec.model_dump()}


def period_bounds(engine, semantic: dict) -> dict | None:
    times = semantic.get("time_dimensions", [])
    if not times:
        return None
    column = quote(times[0]["source_column"])
    today = date.today()
    result = engine.execute(
        f'SELECT MIN({column}) AS min_date, MAX({column}) AS max_date FROM {quote(semantic["table_name"])}'
    ).get("rows") or []
    if not result or not result[0][0]:
        return None
    min_date = _as_date(result[0][0])
    max_date = _as_date(result[0][1])
    if max_date > today:
        max_date = today
    recent_end = max_date
    recent_start = _shift_months(max_date, -2)
    prev_end = recent_start - timedelta(days=1)
    prev_start = _shift_months(recent_start, -3)
    return {
        "min_date": min_date.isoformat(),
        "max_date": max_date.isoformat(),
        "recent_start": recent_start.isoformat(),
        "recent_end": recent_end.isoformat(),
        "prev_start": prev_start.isoformat(),
        "prev_end": prev_end.isoformat(),
        "column": times[0]["source_column"],
        "dimension": times[0]["name"],
    }


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def _shift_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def build_decomposition(plan: dict, semantic: dict, bounds: dict) -> list[dict]:
    """Build the multi-step 'why did this move?' investigation.

    Periods: the most recent quarter vs the preceding quarter, computed from the
    data itself (never hard-coded), then decomposed by categorical dimensions.
    """
    table = quote(semantic["table_name"])
    metrics = [m for m in semantic.get("metrics", []) if m["name"] in plan.get("metrics", [])] or \
              [m for m in semantic.get("metrics", []) if m["name"] == "total_revenue"]
    metric = metrics[0] if metrics else None
    if metric is None:
        raise AppError("NO_METRIC", "No metric available for decomposition.", 422)
    if metric["aggregation"] == "RATIO":
        metric = next((m for m in semantic["metrics"] if m["aggregation"] == "SUM"), metric)
    measure = f'SUM({quote(metric["source_column"])})'
    date_col = quote(bounds["column"])
    dimensions = [d for d in semantic.get("dimensions", []) if d.get("data_type") in ("categorical", "boolean")][:2]

    steps: list[dict] = []
    steps.append({
        "label": f"{metric['label']} by month",
        "sql": (
            f"SELECT DATE_TRUNC('month', {date_col}) AS month, {measure} AS {quote(metric['name'])} "
            f"FROM {table} GROUP BY 1 ORDER BY 1"
        ),
        "params": [],
        "columns": ["month", metric["name"]],
        "role": "trend",
    })
    steps.append({
        "label": "Recent vs previous quarter",
        "sql": (
            f"SELECT {measure} AS recent, "
            f"(SELECT {measure} FROM {table} WHERE {date_col} BETWEEN ? AND ?) AS previous "
            f"FROM {table} WHERE {date_col} BETWEEN ? AND ?"
        ),
        "params": [bounds["prev_start"], bounds["prev_end"], bounds["recent_start"], bounds["recent_end"]],
        "columns": ["recent", "previous"],
        "role": "totals",
    })
    for dim in dimensions:
        column = quote(dim["source_column"])
        steps.append({
            "label": f"{metric['label']} change by {dim['label']}",
            "sql": (
                f"SELECT {column} AS {quote(dim['name'])}, "
                f"SUM(CASE WHEN {date_col} BETWEEN ? AND ? THEN {quote(metric['source_column'])} ELSE 0 END) AS recent, "
                f"SUM(CASE WHEN {date_col} BETWEEN ? AND ? THEN {quote(metric['source_column'])} ELSE 0 END) AS previous "
                f"FROM {table} GROUP BY 1 ORDER BY recent DESC"
            ),
            "params": [bounds["recent_start"], bounds["recent_end"], bounds["prev_start"], bounds["prev_end"]],
            "columns": [dim["name"], "recent", "previous"],
            "role": "dimension",
            "dimension": dim["name"],
            "dimension_label": dim.get("label", humanize(dim["name"])),
        })
    return steps


LLM_SQL_SYSTEM = (
    "You are a senior analytics engineer. You translate business questions into a single, read-only "
    "DuckDB SELECT statement over the provided dataset view. Rules: use only the listed tables and columns; "
    "never write DDL or DML; never use multiple statements; do not use file functions; always alias "
    "aggregates with the semantic metric names; use DATE_TRUNC for time grouping; keep result sets under 500 rows. "
    "Return JSON: {\"sql\": str, \"explanation\": str, \"confidence\": number}. No markdown."
)


def llm_generate_sql(
    question: str, semantic: dict, columns: list[dict], history: list[dict] | None = None
) -> tuple[dict | None, llm.LLMResult]:
    if not llm.llm_available():
        return None, llm.LLMResult(error="llm_not_configured", model="deterministic")
    metric_lines = [
        f"- {m['name']}: {m['label']} = {m['aggregation']}({m.get('source_column')})"
        + (f" ratio {m['numerator']}/{m['denominator']}" if m["aggregation"] == "RATIO" else "")
        for m in semantic.get("metrics", [])
    ]
    dim_lines = [
        f"- {d['name']} = column {d['source_column']} ({d['data_type']})"
        for d in semantic.get("dimensions", [])
    ]
    time_lines = [
        f"- {t['name']} = column {t['source_column']} (time dimension)"
        for t in semantic.get("time_dimensions", [])
    ]
    column_lines = [f"- {c['name']} ({c['type']})" for c in columns]
    history_text = ""
    if history:
        history_text = "\nRecent conversation:\n" + "\n".join(
            f"{m['role']}: {m['text'][:300]}" for m in history[-4:]
        )
    prompt = (
        f"Dataset table: {semantic['table_name']}\n"
        f"Columns:\n{chr(10).join(column_lines)}\n"
        f"Semantic metrics:\n{chr(10).join(metric_lines)}\n"
        f"Dimensions:\n{chr(10).join(dim_lines)}\n"
        f"Time dimensions:\n{chr(10).join(time_lines)}\n"
        f"{history_text}\n\nQuestion: {question}\n"
        "Write the SQL for this question."
    )
    from pydantic import BaseModel

    class SQLPlan(BaseModel):
        sql: str
        explanation: str = ""
        confidence: float = 0.5

    parsed, result = llm.generate_structured(prompt, SQLPlan, system=LLM_SQL_SYSTEM, trace_name="sql.generation")
    if parsed is None:
        return None, result
    return {"sql": parsed.sql, "label": question[:80], "explanation": parsed.explanation,
            "confidence": parsed.confidence}, result
