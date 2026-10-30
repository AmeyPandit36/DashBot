"""Declarative query builder.

Dashboard widgets and the deterministic analyst describe *what* to compute
(metrics, dimensions, filters). This module turns that declaration into
parameterised DuckDB SQL. Users and LLMs never supply SQL for dashboard
rendering, which removes an entire class of injection and correctness risk.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.errors import AppError

OPERATORS = {"eq", "neq", "in", "not_in", "gte", "lte", "between", "contains"}
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,80}$")
GRAINS = {"day", "week", "month", "quarter", "year"}


class QueryFilter(BaseModel):
    field: str
    operator: Literal["eq", "neq", "in", "not_in", "gte", "lte", "between", "contains"] = "eq"
    value: Any = None

    @field_validator("field")
    @classmethod
    def _field_format(cls, value: str) -> str:
        if not IDENT_RE.match(value):
            raise ValueError("Filter fields must be semantic field names.")
        return value


class OrderSpec(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"


class QuerySpec(BaseModel):
    """A declarative analytical query, safe to store and validate."""

    metrics: list[str] = Field(default_factory=list, max_length=8)
    group_by: list[str] = Field(default_factory=list, max_length=3)
    grain: str | None = None
    filters: list[QueryFilter] = Field(default_factory=list, max_length=8)
    order_by: OrderSpec | None = None
    limit: int = Field(default=100, ge=1, le=2000)

    @field_validator("metrics", "group_by")
    @classmethod
    def _identifiers(cls, values: list[str]) -> list[str]:
        for value in values:
            if not IDENT_RE.match(value):
                raise ValueError(f"Invalid field name '{value}'.")
        return values

    @field_validator("grain")
    @classmethod
    def _grain(cls, value: str | None) -> str | None:
        if value is not None and value not in GRAINS:
            raise ValueError(f"Unsupported time grain '{value}'.")
        return value

    @model_validator(mode="after")
    def _shape(self) -> "QuerySpec":
        if not self.metrics and not self.group_by:
            raise ValueError("A query needs at least one metric or dimension.")
        return self


def quote(identifier: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", identifier):
        raise AppError("INVALID_IDENTIFIER", f"Unsafe identifier: {identifier}")
    return f'"{identifier}"'


def metric_expression(metric: dict) -> str:
    agg = metric["aggregation"]
    column = quote(metric["source_column"])
    if agg == "SUM":
        return f"SUM({column})"
    if agg == "AVG":
        return f"AVG({column})"
    if agg == "COUNT":
        return f"COUNT({column})"
    if agg == "COUNT_DISTINCT":
        return f"COUNT(DISTINCT {column})"
    if agg in ("MIN", "MAX", "MEDIAN"):
        return f"{agg}({column})"
    raise AppError("UNSUPPORTED_AGGREGATION", f"Aggregation '{agg}' cannot be rendered directly.")


def resolve_metrics(spec: QuerySpec, semantic: dict) -> list[dict]:
    by_name = {m["name"]: m for m in semantic.get("metrics", [])}
    resolved = []
    for name in spec.metrics:
        metric = by_name.get(name)
        if metric is None:
            raise AppError("UNKNOWN_METRIC", f"Metric '{name}' is not defined in the approved semantic model.", 422)
        resolved.append(metric)
    return resolved


def metric_sql(metric: dict, by_name: dict[str, dict], stack: tuple[str, ...] = ()) -> str:
    if metric["aggregation"] != "RATIO":
        return metric_expression(metric)
    if metric["name"] in stack:
        raise AppError("CYCLIC_METRIC", f"Metric '{metric['name']}' references itself.")
    numerator = by_name.get(metric.get("numerator", ""))
    denominator = by_name.get(metric.get("denominator", ""))
    if not numerator or not denominator:
        raise AppError("INVALID_METRIC", f"Ratio metric '{metric['name']}' has unresolved components.")
    num_sql = metric_sql(numerator, by_name, stack + (metric["name"],))
    den_sql = metric_sql(denominator, by_name, stack + (metric["name"],))
    return f"({num_sql}) / NULLIF(({den_sql}), 0)"


def _dimension_sql(field: str, semantic: dict, grain: str | None) -> tuple[str, str]:
    """Return (select_expression, output_alias)."""
    for td in semantic.get("time_dimensions", []):
        if td["name"] == field:
            use_grain = grain or td.get("default_grain") or "month"
            if use_grain not in GRAINS:
                raise AppError("UNSUPPORTED_GRAIN", f"Unsupported time grain '{use_grain}'.")
            return f"DATE_TRUNC('{use_grain}', {quote(td['source_column'])})", field
    for dim in semantic.get("dimensions", []):
        if dim["name"] == field:
            return quote(dim["source_column"]), field
    raise AppError("UNKNOWN_DIMENSION", f"Dimension '{field}' is not defined in the approved semantic model.", 422)


def _filter_sql(item: QueryFilter, semantic: dict) -> tuple[str, list[Any]]:
    column_sql, _ = _dimension_sql(item.field, semantic, None)
    op = item.operator
    if op == "eq":
        return f"{column_sql} = ?", [item.value]
    if op == "neq":
        return f"{column_sql} <> ?", [item.value]
    if op in ("in", "not_in"):
        values = item.value if isinstance(item.value, list) else [item.value]
        values = values[:50]
        if not values:
            raise AppError("INVALID_FILTER", f"Filter on '{item.field}' has no values.", 422)
        placeholders = ", ".join("?" for _ in values)
        keyword = "IN" if op == "in" else "NOT IN"
        return f"{column_sql} {keyword} ({placeholders})", list(values)
    if op == "gte":
        return f"{column_sql} >= ?", [item.value]
    if op == "lte":
        return f"{column_sql} <= ?", [item.value]
    if op == "between":
        values = item.value if isinstance(item.value, list) else []
        if len(values) != 2:
            raise AppError("INVALID_FILTER", "Between filters require exactly two values.", 422)
        return f"{column_sql} BETWEEN ? AND ?", [values[0], values[1]]
    if op == "contains":
        return f"CAST({column_sql} AS VARCHAR) ILIKE ?", [f"%{item.value}%"]
    raise AppError("INVALID_FILTER", f"Unsupported filter operator '{op}'.", 422)


def build_query(spec: QuerySpec, semantic: dict, table_name: str) -> tuple[str, list[Any], list[str]]:
    """Build a parameterised SELECT. Returns (sql, params, output_columns)."""
    table = quote(table_name)
    select_parts: list[str] = []
    group_parts: list[str] = []
    aliases: list[str] = []
    by_name = {m["name"]: m for m in semantic.get("metrics", [])}

    for field in spec.group_by:
        expr, alias = _dimension_sql(field, semantic, spec.grain)
        select_parts.append(f"{expr} AS {quote(alias)}")
        group_parts.append(expr)
        aliases.append(alias)

    for metric in resolve_metrics(spec, semantic):
        expr = metric_sql(metric, by_name)
        select_parts.append(f"{expr} AS {quote(metric['name'])}")
        aliases.append(metric["name"])

    if not select_parts:
        raise AppError("EMPTY_QUERY", "No selectable fields were provided.", 422)

    where_sql: list[str] = []
    params: list[Any] = []
    for item in spec.filters:
        clause, values = _filter_sql(item, semantic)
        where_sql.append(clause)
        params.extend(values)

    sql = f"SELECT {', '.join(select_parts)} FROM {table}"
    if where_sql:
        sql += " WHERE " + " AND ".join(where_sql)
    if group_parts:
        sql += " GROUP BY " + ", ".join(f"{i + 1}" for i in range(len(group_parts)))
    if spec.order_by:
        if spec.order_by.field not in aliases:
            raise AppError(
                "UNKNOWN_ORDER_FIELD",
                f"Cannot order by '{spec.order_by.field}' — it is not part of the query output.",
                422,
            )
        sql += f" ORDER BY {quote(spec.order_by.field)} {spec.order_by.direction.upper()}"
    elif group_parts:
        sql += f" ORDER BY {quote(aliases[0])}"
    sql += f" LIMIT {int(spec.limit)}"
    return sql, params, aliases


def output_columns(spec: QuerySpec, semantic: dict) -> list[str]:
    return list(spec.group_by) + list(spec.metrics)
