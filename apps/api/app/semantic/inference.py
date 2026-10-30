"""Semantic inference: deterministic heuristics + optional Gemini refinement.

Column names alone are never trusted as business meaning. Every inferred metric
carries a confidence, a description and ``requires_approval``; the UI presents
the proposal as a draft until a human approves it.
"""
from __future__ import annotations

import re

from app.agents import llm
from app.semantic.schemas import SemanticProposal, validate_semantic_definition

REVENUE_TOKENS = ("revenue", "sales", "amount", "total", "gmv", "income", "turnover")
PRICE_TOKENS = ("price", "rate", "cost")
QUANTITY_TOKENS = ("quantity", "qty", "units", "volume")
DISCOUNT_TOKENS = ("discount", "markdown", "rebate")
PROFIT_TOKENS = ("profit", "margin")


def humanize(name: str) -> str:
    words = re.sub(r"[_\-]+", " ", name).strip().split()
    small = {"of", "and", "the", "per", "by", "to"}
    out = []
    for idx, word in enumerate(words):
        if idx > 0 and word.lower() in small:
            out.append(word.lower())
        elif word.isupper():
            out.append(word)
        else:
            out.append(word.capitalize())
    label = " ".join(out) or name
    return label.replace("Id", "ID")


def _is_identifier(name: str, column: dict) -> bool:
    if name.lower().endswith("_id") or name.lower() == "id":
        return True
    unique_pct = column.get("unique_pct", 0)
    stats = column.get("stats", {})
    return bool(stats.get("identifier_like")) and unique_pct > 95


def _currency_like(name: str) -> bool:
    return any(token in name.lower() for token in REVENUE_TOKENS + PRICE_TOKENS + PROFIT_TOKENS)


def build_heuristic_proposal(
    dataset_id: str,
    dataset_version_id: str | None,
    table_name: str,
    profile: dict,
    grain: str = "one row per record",
) -> dict:
    columns = profile.get("columns", [])
    metrics: list[dict] = []
    dimensions: list[dict] = []
    times: list[dict] = []
    identifiers: list[str] = []
    metric_names: set[str] = set()

    def add_metric(**kwargs: dict) -> None:
        name = kwargs["name"]
        if name in metric_names:
            return
        metric_names.add(name)
        metrics.append(kwargs)

    revenue_column: str | None = None
    order_column: str | None = None
    quantity_column: str | None = None

    numeric = [c for c in columns if c["inferred_type"] in ("integer", "decimal")]
    strings = [c for c in columns if c["inferred_type"] in ("string", "boolean")]
    dates = [c for c in columns if c["inferred_type"] in ("date", "datetime")]

    for column in numeric:
        name = column["name"]
        lower = name.lower()
        if _is_identifier(name, column):
            identifiers.append(name)
            continue
        label = humanize(name)
        if any(t in lower for t in DISCOUNT_TOKENS) and column["inferred_type"] == "decimal":
            add_metric(
                name=f"avg_{name}", label=f"Average {label}", source_column=name, aggregation="AVG",
                format="percent", confidence=0.6,
                description=f"Arithmetic mean of {name}. If values are stored as fractions (0-1), display as a percentage.",
            )
            continue
        if any(t in lower for t in PRICE_TOKENS):
            add_metric(
                name=f"avg_{name}", label=f"Average {label}", source_column=name, aggregation="AVG",
                format="currency" if _currency_like(name) else "decimal", confidence=0.5,
                description=f"Average {label} across the rows in scope.",
            )
            continue
        if any(t in lower for t in REVENUE_TOKENS) and revenue_column is None:
            revenue_column = name
            add_metric(
                name="total_revenue", label=(label if label.lower().startswith("total") else f"Total {label}"),
                source_column=name, aggregation="SUM",
                format="currency", confidence=0.55, requires_approval=True,
                description=(
                    f"SUM({name}). The business meaning of this column (net of discount, tax or refunds) "
                    "must be confirmed in the semantic model before it is treated as revenue."
                ),
            )
            continue
        if any(t in lower for t in QUANTITY_TOKENS):
            quantity_column = name
            add_metric(
                name=f"total_{name}", label=(label if label.lower().startswith("total") else f"Total {label}"),
                source_column=name, aggregation="SUM",
                format="integer", confidence=0.7,
                description=f"Sum of {name} across all rows in scope.",
            )
            continue
        add_metric(
            name=f"total_{name}", label=(label if label.lower().startswith("total") else f"Total {label}"),
            source_column=name, aggregation="SUM", format="decimal", confidence=0.45,
            description=f"Sum of {name}.",
        )

    for column in strings:
        name = column["name"]
        lower = name.lower()
        label = humanize(name)
        unique = column.get("unique_count", 0)
        if _is_identifier(name, column):
            identifiers.append(name)
            if "order" in lower:
                order_column = name
                add_metric(
                    name="total_orders", label="Total Orders", source_column=name, aggregation="COUNT_DISTINCT",
                    format="integer", confidence=0.8,
                    description=f"COUNT(DISTINCT {name}) — one row per order line, so orders are de-duplicated.",
                )
            elif "customer" in lower:
                add_metric(
                    name="unique_customers", label="Unique Customers", source_column=name,
                    aggregation="COUNT_DISTINCT", format="integer", confidence=0.8,
                    description=f"COUNT(DISTINCT {name}).",
                )
            elif "product" in lower:
                add_metric(
                    name="unique_products", label="Unique Products", source_column=name,
                    aggregation="COUNT_DISTINCT", format="integer", confidence=0.6,
                    description=f"COUNT(DISTINCT {name}).",
                )
            else:
                add_metric(
                    name=f"unique_{name}", label=f"Unique {label}", source_column=name,
                    aggregation="COUNT_DISTINCT", format="integer", confidence=0.5,
                    description=f"COUNT(DISTINCT {name}).",
                )
            continue
        if 0 < unique <= 100 and unique < max(2, profile.get("row_count", 1) * 0.6):
            dimensions.append({
                "name": name,
                "label": label,
                "source_column": name,
                "data_type": "categorical",
                "unique_count": unique,
                "description": f"Grouping dimension with {unique} distinct value(s).",
                "confirmed": False,
                "confidence": 0.75 if unique <= 20 else 0.55,
            })

    for column in dates:
        name = column["name"]
        stats = column.get("stats", {})
        times.append({
            "name": name,
            "label": humanize(name),
            "source_column": name,
            "default_grain": "month",
            "description": f"Date dimension. Observed range {stats.get('min', 'n/a')} to {stats.get('max', 'n/a')}.",
            "min_value": str(stats.get("min")) if stats.get("min") else None,
            "max_value": str(stats.get("max")) if stats.get("max") else None,
        })

    if revenue_column and order_column:
        add_metric(
            name="average_order_value", label="Average Order Value", source_column=revenue_column,
            aggregation="RATIO", format="currency", numerator="total_revenue", denominator="total_orders",
            confidence=0.7, requires_approval=True,
            description="Total revenue divided by distinct orders (AOV). Confirm the revenue definition first.",
        )
    if revenue_column and quantity_column:
        add_metric(
            name="average_selling_price", label="Average Selling Price", source_column=revenue_column,
            aggregation="RATIO", format="currency", numerator="total_revenue",
            denominator=f"total_{quantity_column}", confidence=0.45,
            description="Revenue divided by units sold — an implied realised price, not the list price.",
        )

    for ident in identifiers:
        dimensions.append({
            "name": ident,
            "label": humanize(ident),
            "source_column": ident,
            "data_type": "identifier",
            "unique_count": None,
            "description": "Identifier column: used for counting and joining, not for grouping by default.",
            "confirmed": False,
            "confidence": 0.9,
        })

    business_definitions = _business_definitions(revenue_column, order_column, quantity_column)

    return {
        "dataset_id": dataset_id,
        "dataset_version_id": dataset_version_id,
        "table_name": table_name,
        "version": 1,
        "grain": grain,
        "generated_by": "heuristic",
        "metrics": metrics,
        "dimensions": dimensions,
        "time_dimensions": times,
        "relationships": [],
        "business_definitions": business_definitions,
    }


def _business_definitions(revenue: str | None, order: str | None, quantity: str | None) -> list[dict]:
    definitions = [
        {
            "term": "Row grain",
            "definition": "Each row represents one record of the uploaded dataset. Metrics aggregate rows within the active filters.",
        },
    ]
    if revenue:
        definitions.append({
            "term": humanize(revenue),
            "definition": (
                f"{revenue} is aggregated with SUM. Its business meaning (net vs gross, tax, refunds) is proposed by the "
                "semantic layer and requires human approval before it is used as the revenue definition."
            ),
        })
    if order:
        definitions.append({
            "term": "Orders",
            "definition": f"Number of distinct {order} values. Multiple rows can belong to the same order.",
        })
    if quantity:
        definitions.append({
            "term": "Units sold",
            "definition": f"SUM of {quantity} across the selected rows.",
        })
    return definitions


# ---------------------------------------------------------------------------
# LLM refinement
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You are a careful data analyst building a semantic model for a business intelligence platform. "
    "You never invent columns. You only use the column names and statistics supplied. "
    "Return JSON only, matching the requested shape. Do not include commentary or code."
)


def build_llm_prompt(heuristic: dict, profile: dict) -> str:
    columns_summary = [
        {
            "name": c["name"],
            "type": c["inferred_type"],
            "null_pct": c["null_pct"],
            "unique_count": c["unique_count"],
            "samples": c["sample_values"][:3],
            "stats": {k: c["stats"].get(k) for k in ("min", "max", "mean", "median") if c["stats"].get(k) is not None},
        }
        for c in profile.get("columns", [])
    ]
    return (
        "Propose a semantic model for this dataset.\n"
        f"Rows: {profile.get('row_count')}, Columns: {profile.get('column_count')}\n"
        f"Grain hint: {heuristic.get('grain')}\n"
        f"Columns: {columns_summary}\n\n"
        "Return JSON with keys: metrics, dimensions, time_dimensions, relationships, notes.\n"
        "metric: {name (snake_case), label, source_column, aggregation in [SUM, AVG, COUNT, COUNT_DISTINCT, MIN, MAX, MEDIAN, RATIO], "
        "format in [currency, integer, decimal, percent, number], description, confidence 0-1, numerator/denominator only for RATIO}.\n"
        "dimension: {name, label, source_column, data_type in [categorical, identifier, numeric, boolean], description, confidence}.\n"
        "time_dimension: {name, label, source_column, default_grain in [day, week, month, quarter, year], description}.\n"
        "Use at most 9 metrics and at most 8 dimensions. Prefer business-relevant metrics. "
        "Do not assume a column means revenue purely from its name: explain the assumption in the description."
    )


def refine_with_llm(heuristic: dict, profile: dict, available_columns: set[str]) -> tuple[dict, dict]:
    """Merge an LLM proposal into the heuristic model. Falls back safely."""
    if not llm.llm_available():
        return heuristic, {"provider": "deterministic", "reason": "GEMINI_API_KEY not configured"}

    proposal, result = llm.generate_structured(
        build_llm_prompt(heuristic, profile),
        SemanticProposal,
        system=_SYSTEM,
        trace_name="semantic.inference",
    )
    if proposal is None:
        return heuristic, {
            "provider": "deterministic",
            "reason": result.error or "llm_unavailable",
            "latency_ms": result.latency_ms,
        }

    heuristic_metric_names = {m["name"] for m in heuristic.get("metrics", [])}
    merged_metrics: list[dict] = []
    for metric in proposal.metrics:
        payload = metric.model_dump()
        payload["requires_approval"] = True
        payload["proposed_by"] = "gemini"
        merged_metrics.append(payload)

    # Keep heuristic ratio metrics the LLM cannot derive (they reference other metrics).
    for metric in heuristic.get("metrics", []):
        if metric["aggregation"] == "RATIO" and metric["name"] not in {m["name"] for m in merged_metrics}:
            merged_metrics.append(metric)

    if not merged_metrics:
        merged_metrics = heuristic.get("metrics", [])

    merged = {
        **heuristic,
        "generated_by": "gemini",
        "metrics": merged_metrics,
        "dimensions": [d.model_dump() for d in proposal.dimensions] or heuristic.get("dimensions", []),
        "time_dimensions": [t.model_dump() for t in proposal.time_dimensions] or heuristic.get("time_dimensions", []),
        "relationships": [r.model_dump() for r in proposal.relationships] or heuristic.get("relationships", []),
        "notes": proposal.notes,
    }
    merged["dataset_id"] = heuristic["dataset_id"]
    merged["table_name"] = heuristic["table_name"]
    merged["dataset_version_id"] = heuristic.get("dataset_version_id")
    merged["version"] = heuristic.get("version", 1)
    merged["grain"] = heuristic.get("grain", "one row per record")

    validated, report = validate_semantic_definition(merged, available_columns)
    if not validated:
        heuristic["_llm_merge_report"] = report.model_dump()
        return heuristic, {
            "provider": "deterministic",
            "reason": "llm_proposal_invalid",
            "report": report.model_dump(),
        }
    validated["generated_by"] = "gemini"
    return validated, {
        "provider": "gemini",
        "model": result.model,
        "tokens": result.tokens,
        "latency_ms": result.latency_ms,
        "kept_heuristic_metrics": sorted(heuristic_metric_names),
    }


def build_glossary(definition: dict, dataset_name: str) -> str:
    """Render the approved semantic model into a retrieval document."""
    lines = [f"# Business glossary — {dataset_name}", ""]
    if definition.get("grain"):
        lines.append(f"**Grain:** {definition['grain']}")
    lines.append("\n## Metrics")
    for metric in definition.get("metrics", []):
        agg = metric.get("aggregation", "SUM")
        extra = ""
        if agg == "RATIO":
            extra = f" = {metric.get('numerator')} / {metric.get('denominator')}"
        lines.append(
            f"- **{metric.get('label')}** (`{metric.get('name')}`): {agg} of "
            f"`{metric.get('source_column')}`{extra}. {metric.get('description', '')}".strip()
        )
    lines.append("\n## Dimensions")
    for dim in definition.get("dimensions", []):
        lines.append(
            f"- **{dim.get('label')}** (`{dim.get('source_column')}`): {dim.get('data_type')}. "
            f"{dim.get('description', '')}".strip()
        )
    if definition.get("time_dimensions"):
        lines.append("\n## Time dimensions")
        for td in definition["time_dimensions"]:
            lines.append(f"- **{td.get('label')}** (`{td.get('source_column')}`), default grain {td.get('default_grain')}.")
    if definition.get("business_definitions"):
        lines.append("\n## Business definitions")
        for item in definition["business_definitions"]:
            lines.append(f"- **{item.get('term')}**: {item.get('definition')}")
    return "\n".join(lines)
