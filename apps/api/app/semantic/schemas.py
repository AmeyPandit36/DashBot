"""Pydantic contracts for the semantic model and its validation."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Aggregation = Literal["SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX", "MEDIAN", "RATIO"]
Format = Literal["currency", "integer", "decimal", "percent", "number"]
Grain = Literal["day", "week", "month", "quarter", "year"]

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,60}$")


class MetricSpec(BaseModel):
    name: str
    label: str
    source_column: str
    aggregation: Aggregation
    format: Format = "number"
    description: str = ""
    numerator: str | None = None
    denominator: str | None = None
    requires_approval: bool = True
    confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def _name_format(cls, value: str) -> str:
        if not NAME_RE.match(value):
            raise ValueError("Metric names must be snake_case identifiers.")
        return value

    @model_validator(mode="after")
    def _ratio_shape(self) -> "MetricSpec":
        if self.aggregation == "RATIO" and not (self.numerator and self.denominator):
            raise ValueError("RATIO metrics require numerator and denominator metric names.")
        return self


class DimensionSpec(BaseModel):
    name: str
    label: str
    source_column: str
    data_type: Literal["categorical", "identifier", "numeric", "boolean"] = "categorical"
    description: str = ""
    confirmed: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)


class TimeDimensionSpec(BaseModel):
    name: str
    label: str
    source_column: str
    default_grain: Grain = "month"
    description: str = ""
    min_value: str | None = None
    max_value: str | None = None


class RelationshipSpec(BaseModel):
    from_column: str
    to_column: str
    type: Literal["many_to_one", "one_to_many", "one_to_one"] = "many_to_one"
    confidence: float = 0.3
    note: str = ""


class SemanticProposal(BaseModel):
    """What the LLM is allowed to return. Never executable code."""

    metrics: list[MetricSpec] = Field(default_factory=list)
    dimensions: list[DimensionSpec] = Field(default_factory=list)
    time_dimensions: list[TimeDimensionSpec] = Field(default_factory=list)
    relationships: list[RelationshipSpec] = Field(default_factory=list)
    notes: str = ""


class SemanticDefinition(BaseModel):
    dataset_id: str
    dataset_version_id: str | None = None
    table_name: str
    version: int = 1
    grain: str = "one row per record"
    generated_by: str = "heuristic"
    metrics: list[MetricSpec] = Field(default_factory=list)
    dimensions: list[DimensionSpec] = Field(default_factory=list)
    time_dimensions: list[TimeDimensionSpec] = Field(default_factory=list)
    relationships: list[RelationshipSpec] = Field(default_factory=list)
    business_definitions: list[dict] = Field(default_factory=list)


class SemanticValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dropped_metrics: list[str] = Field(default_factory=list)
    dropped_dimensions: list[str] = Field(default_factory=list)


def validate_semantic_definition(
    definition: dict, available_columns: set[str], available_types: dict[str, str] | None = None
) -> tuple[dict, SemanticValidationReport]:
    """Validate a semantic model against the physical dataset schema.

    Invalid metrics/dimensions are dropped (with an explicit report) rather than
    persisted, so downstream SQL generation can trust the model.
    """
    errors: list[str] = []
    warnings: list[str] = []
    dropped_metrics: list[str] = []
    dropped_dimensions: list[str] = []
    columns_lower = {c.lower(): c for c in available_columns}

    try:
        model = SemanticDefinition.model_validate(definition)
    except Exception as exc:  # noqa: BLE001
        return {}, SemanticValidationReport(valid=False, errors=[f"Semantic model failed schema validation: {exc}"])

    metrics: list[MetricSpec] = []
    seen: set[str] = set()
    for metric in model.metrics:
        if metric.source_column.lower() not in columns_lower and metric.aggregation != "RATIO":
            dropped_metrics.append(f"{metric.name} (missing column '{metric.source_column}')")
            continue
        if metric.name in seen:
            dropped_metrics.append(f"{metric.name} (duplicate name)")
            continue
        if metric.aggregation == "COUNT_DISTINCT" and available_types:
            col_type = available_types.get(columns_lower.get(metric.source_column.lower(), ""), "")
            if col_type in ("decimal", "float", "double"):
                warnings.append(f"COUNT_DISTINCT on continuous column '{metric.source_column}' may be imprecise.")
        seen.add(metric.name)
        metrics.append(metric)

    # Resolve RATIO references after the first pass.
    metric_names = {m.name for m in metrics}
    metrics = [m for m in metrics if m.aggregation != "RATIO" or (m.numerator in metric_names and m.denominator in metric_names)]

    dimensions: list[DimensionSpec] = []
    dim_seen: set[str] = set()
    for dim in model.dimensions:
        if dim.source_column.lower() not in columns_lower:
            dropped_dimensions.append(f"{dim.name} (missing column '{dim.source_column}')")
            continue
        if dim.name in dim_seen:
            dropped_dimensions.append(f"{dim.name} (duplicate name)")
            continue
        dim_seen.add(dim.name)
        dimensions.append(dim)

    times: list[TimeDimensionSpec] = []
    for td in model.time_dimensions:
        if td.source_column.lower() not in columns_lower:
            errors.append(f"Time dimension '{td.name}' references unknown column '{td.source_column}'.")
            continue
        times.append(td)

    if not metrics:
        errors.append("The semantic model must define at least one valid metric.")
    if not dimensions and not times:
        errors.append("The semantic model must define at least one dimension or time dimension.")

    model.metrics = metrics
    model.dimensions = dimensions
    model.time_dimensions = times
    payload = model.model_dump()
    return payload, SemanticValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        dropped_metrics=dropped_metrics,
        dropped_dimensions=dropped_dimensions,
    )
