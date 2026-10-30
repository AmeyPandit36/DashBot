"""Strict declarative dashboard schema.

The renderer is a trusted component registry: the specification can only select
from an allowlist of widget types and encodings. Unknown widget types, unknown
encoding keys and dangling query references are rejected here, before the
browser ever receives the specification.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.sql.builder import QuerySpec

WidgetType = Literal[
    "kpi", "line_chart", "bar_chart", "area_chart", "pie_chart", "donut_chart",
    "scatter_chart", "data_table", "heatmap",
]
WIDGET_TYPES = {
    "kpi", "line_chart", "bar_chart", "area_chart", "pie_chart", "donut_chart",
    "scatter_chart", "data_table", "heatmap",
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,64}$")
ALLOWED_ENCODINGS = {
    "kpi": {"value", "secondary"},
    "line_chart": {"x", "y", "series"},
    "area_chart": {"x", "y", "series"},
    "bar_chart": {"x", "y", "series"},
    "pie_chart": {"label", "value"},
    "donut_chart": {"label", "value"},
    "scatter_chart": {"x", "y", "series", "label"},
    "data_table": {"columns"},
    "heatmap": {"x", "y", "value"},
}


class WidgetLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(default=0, ge=0, le=11)
    y: int = Field(default=0, ge=0, le=200)
    w: int = Field(default=6, ge=1, le=12)
    h: int = Field(default=4, ge=1, le=12)

    @model_validator(mode="after")
    def _bounds(self) -> "WidgetLayout":
        if self.x + self.w > 12:
            raise ValueError("Widget exceeds the 12-column grid.")
        return self


class WidgetInteractions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cross_filter: bool = False
    click_to_ask: bool = True


class WidgetOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_format: Literal["currency", "integer", "decimal", "percent", "number"] = "number"
    compare: Literal["none", "previous_period"] = "none"
    sort: Literal["none", "asc", "desc"] = "desc"
    show_legend: bool = True
    stacked: bool = False
    palette: Literal["brand", "sequential", "diverging", "categorical"] = "brand"
    delta_label: str | None = None


class WidgetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: WidgetType
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=400)
    query_ref: str
    encoding: dict[str, Any]
    layout: WidgetLayout
    interactions: WidgetInteractions = Field(default_factory=WidgetInteractions)
    options: WidgetOptions = Field(default_factory=WidgetOptions)

    @field_validator("id", "query_ref")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("Widget and query identifiers must be snake_case slugs.")
        return value

    @model_validator(mode="after")
    def _encoding_keys(self) -> "WidgetSpec":
        allowed = ALLOWED_ENCODINGS[self.type]
        unknown = set(self.encoding) - allowed
        if unknown:
            raise ValueError(f"Unsupported encoding keys for {self.type}: {sorted(unknown)}")
        if not self.encoding:
            raise ValueError("Every widget needs an encoding.")
        return self


class DashboardFilterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    field: str
    type: Literal["categorical", "date_range"] = "categorical"
    default_value: Any = None


class DashboardLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: Literal[12] = 12
    gap: int = Field(default=16, ge=8, le=32)
    density: Literal["comfortable", "compact"] = "comfortable"


class DashboardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    dashboard_id: str | None = None
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(default="", max_length=400)
    dataset_id: str
    semantic_model_version: int = 1
    generation_mode: Literal["automatic", "review"] = "review"
    layout: DashboardLayout = Field(default_factory=DashboardLayout)
    filters: list[DashboardFilterSpec] = Field(default_factory=list, max_length=8)
    queries: dict[str, QuerySpec] = Field(default_factory=dict)
    widgets: list[WidgetSpec] = Field(default_factory=list, min_length=1, max_length=24)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _integrity(self) -> "DashboardSpec":
        ids = [w.id for w in self.widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("Widget identifiers must be unique.")
        for widget in self.widgets:
            if widget.query_ref not in self.queries:
                raise ValueError(f"Widget '{widget.id}' references unknown query '{widget.query_ref}'.")
            spec = self.queries[widget.query_ref]
            available = set(spec.group_by) | set(spec.metrics)
            fields: list[str] = []
            for key, value in widget.encoding.items():
                if isinstance(value, list):
                    fields.extend(str(v) for v in value)
                elif isinstance(value, str):
                    fields.append(value)
            missing = [f for f in fields if f not in available]
            if missing:
                raise ValueError(
                    f"Widget '{widget.id}' encodes fields that its query does not return: {missing}."
                )
        return self


class DashboardValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    widget_count: int = 0
    query_count: int = 0


def validate_dashboard_spec(spec: dict, semantic: dict) -> tuple[dict | None, DashboardValidationReport]:
    """Validate structure *and* semantic references."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        parsed = DashboardSpec.model_validate(spec)
    except Exception as exc:  # noqa: BLE001
        return None, DashboardValidationReport(valid=False, errors=[str(exc)])

    dimension_names = {d["name"] for d in semantic.get("dimensions", [])} | {
        t["name"] for t in semantic.get("time_dimensions", [])
    }
    metric_names = {m["name"] for m in semantic.get("metrics", [])}

    for query_id, query in parsed.queries.items():
        for metric in query.metrics:
            if metric not in metric_names:
                errors.append(f"Query '{query_id}' uses metric '{metric}' that is not in the semantic model.")
        for field in query.group_by:
            if field not in dimension_names:
                errors.append(f"Query '{query_id}' groups by unknown dimension '{field}'.")
        for item in query.filters:
            if item.field not in dimension_names:
                errors.append(f"Query '{query_id}' filters on unknown field '{item.field}'.")

    for flt in parsed.filters:
        if flt.field not in dimension_names:
            errors.append(f"Global filter '{flt.id}' references unknown field '{flt.field}'.")
        if flt.type == "date_range":
            time_names = {t["name"] for t in semantic.get("time_dimensions", [])}
            if flt.field not in time_names:
                errors.append(f"Date filter '{flt.id}' must reference a time dimension.")

    seen_slots: dict[tuple[int, int], str] = {}
    for widget in parsed.widgets:
        key = (widget.layout.y, widget.layout.x)
        if key in seen_slots:
            warnings.append(f"Widgets '{seen_slots[key]}' and '{widget.id}' share a grid slot.")
        seen_slots[key] = widget.id

    if not any(w.type == "kpi" for w in parsed.widgets):
        warnings.append("The dashboard has no KPI cards.")

    return (
        parsed.model_dump(),
        DashboardValidationReport(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            widget_count=len(parsed.widgets),
            query_count=len(parsed.queries),
        ),
    )
