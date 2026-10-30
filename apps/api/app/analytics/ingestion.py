"""File ingestion, type inference and deterministic data profiling.

Pipeline: VALIDATE -> PARSE -> NORMALISE -> PROFILE -> PARQUET.
The original uploaded bytes are always preserved by the caller before this
module runs; nothing here mutates source data. Cleaning is proposed, never
silently applied.
"""
from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import polars as pl
from charset_normalizer import from_bytes

from app.core.config import settings
from app.core.errors import AppError

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xlsm"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S")
CURRENCY_STRIP = re.compile(r"[₹$€£,\s]")
IDENTIFIER_HINTS = ("id", "code", "sku", "key", "number", "no")
MEASURE_HINTS = ("amount", "revenue", "sales", "total", "price", "cost", "profit", "margin",
                 "quantity", "qty", "units", "discount", "spend", "value")
TIME_HINTS = ("date", "day", "month", "year", "week", "quarter", "timestamp", "time", "period")


@dataclass
class ParsedDataset:
    frame: pl.DataFrame
    file_kind: str
    encoding: str | None
    delimiter: str | None
    sheet_name: str | None
    sheet_names: list[str] = field(default_factory=list)
    coercion_issues: list[dict] = field(default_factory=list)
    original_columns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_extension(filename: str) -> str:
    lowered = (filename or "").lower().strip()
    for ext in sorted(SUPPORTED_EXTENSIONS, key=len, reverse=True):
        if lowered.endswith(ext):
            return ext
    return ""


def validate_upload(filename: str, data: bytes) -> str:
    ext = file_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise AppError(
            "UNSUPPORTED_FILE_TYPE",
            "Only CSV and Excel (.xlsx) files are supported.",
            415,
            {"allowed": sorted(SUPPORTED_EXTENSIONS)},
        )
    if not data:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.", 400)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise AppError(
            "FILE_TOO_LARGE",
            f"Files must be smaller than {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            413,
        )
    if ext == ".csv":
        head = data[:8192]
        if b"\x00" in head:
            raise AppError("INVALID_FILE_CONTENT", "The file does not look like a CSV text file.", 415)
        sample = head.decode("utf-8", errors="ignore")
        if not sample.strip():
            raise AppError("EMPTY_FILE", "The CSV file has no readable content.", 400)
    else:
        if not data.startswith(b"PK"):
            raise AppError(
                "INVALID_FILE_CONTENT",
                "The file does not look like a valid Excel workbook (.xlsx).",
                415,
            )
    return ext


def detect_encoding(data: bytes) -> str:
    best = from_bytes(data[:200_000]).best()
    if best and best.encoding:
        encoding = best.encoding.lower()
        return "utf-8" if encoding in ("ascii", "utf_8", "utf-8") else encoding
    return "utf-8"


def detect_delimiter(text: str) -> str:
    header = text.split("\n", 1)[0]
    counts = {d: header.count(d) for d in [",", ";", "\t", "|"]}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def list_excel_sheets(data: bytes) -> list[str]:
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            sheets = [ws.title for ws in workbook.worksheets][: settings.MAX_EXCEL_SHEETS]
        finally:
            workbook.close()
        return sheets
    except Exception as exc:  # pragma: no cover - corrupt workbook path
        raise AppError("INVALID_EXCEL", "The Excel workbook could not be opened.", 422) from exc


# ---------------------------------------------------------------------------
# Column normalisation
# ---------------------------------------------------------------------------
def normalise_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for idx, raw in enumerate(columns):
        name = re.sub(r"[^0-9a-zA-Z]+", "_", str(raw or "").strip()).strip("_").lower()
        if not name:
            name = f"column_{idx + 1}"
        if name[0].isdigit():
            name = f"col_{name}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        result.append(name[:120])
    return result


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_upload(filename: str, data: bytes, sheet_name: str | None = None) -> ParsedDataset:
    ext = validate_upload(filename, data)
    if ext == ".csv":
        return _parse_csv(data)
    return _parse_excel(data, sheet_name)


def _parse_csv(data: bytes) -> ParsedDataset:
    encoding = detect_encoding(data)
    try:
        text = data.decode(encoding, errors="replace")
    except LookupError:
        encoding = "utf-8"
        text = data.decode("utf-8", errors="replace")
    delimiter = detect_delimiter(text)
    frame: pl.DataFrame | None = None
    last_error: Exception | None = None
    for separator in dict.fromkeys([delimiter, ",", ";", "\t"]):
        for infer in (10_000, 1_000):
            try:
                frame = pl.read_csv(
                    io.BytesIO(text.encode("utf-8")),
                    separator=separator,
                    infer_schema_length=infer,
                    try_parse_dates=True,
                    ignore_errors=True,
                    truncate_ragged_lines=True,
                    encoding="utf8",
                )
                delimiter = separator
                break
            except Exception as exc:  # noqa: BLE001 - retried with alternate separators
                last_error = exc
                frame = None
        if frame is not None and frame.height > 0:
            break
    if frame is None or frame.height == 0:
        raise AppError(
            "PARSE_FAILED",
            "The file could not be parsed as tabular data. Check the delimiter and header row.",
            422,
            {"reason": str(last_error) if last_error else "no rows"},
        )
    original = list(frame.columns)
    frame = _normalise_frame(frame)
    issues = _coerce_types(frame)
    frame = issues.pop("frame")
    return ParsedDataset(
        frame=frame,
        file_kind="csv",
        encoding=encoding,
        delimiter="\\t" if delimiter == "\t" else delimiter,
        sheet_name=None,
        coercion_issues=issues["issues"],
        original_columns=original,
    )


def _parse_excel(data: bytes, sheet_name: str | None) -> ParsedDataset:
    """Read a worksheet directly with openpyxl.

    Pandas is deliberately avoided here: it would pull in pyarrow just to build
    the frame, and every conversion layer is another place where spreadsheet
    values (dates, numbers, formula strings) can be silently mistyped.
    """
    from openpyxl import load_workbook

    sheets = list_excel_sheets(data)
    target = sheet_name if sheet_name in sheets else sheets[0]
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise AppError("INVALID_EXCEL", "The Excel workbook could not be opened.", 422) from exc
    try:
        if target not in workbook.sheetnames:
            raise AppError("SHEET_NOT_FOUND", f"Sheet '{target}' does not exist.", 422)
        worksheet = workbook[target]
        rows = worksheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if header_row is None:
            raise AppError("EMPTY_SHEET", f"Sheet '{target}' contains no data rows.", 422)
        original = [str(value) if value is not None else f"column_{i + 1}" for i, value in enumerate(header_row)]
        # Skip leading fully-empty columns.
        values: list[list] = []
        for row in rows:
            row_values = list(row[: len(original)])
            if all(value is None or str(value).strip() == "" for value in row_values):
                continue
            values.append(row_values)
    finally:
        workbook.close()

    if not values:
        raise AppError("EMPTY_SHEET", f"Sheet '{target}' contains no data rows.", 422)

    names = normalise_columns(original)
    columns: dict[str, list] = {name: [] for name in names}
    for row_values in values:
        for name, value in zip(names, row_values):
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    value = None
            columns[name].append(value)

    frame = pl.DataFrame(columns, strict=False)
    # Drop columns that are entirely empty after trimming.
    empty = [name for name in frame.columns if frame[name].null_count() == frame.height]
    if empty:
        frame = frame.drop(empty)
        names = [name for name in names if name not in empty]
    if frame.width == 0:
        raise AppError("EMPTY_SHEET", f"Sheet '{target}' contains no usable columns.", 422)
    issues = _coerce_types(frame)
    frame = issues.pop("frame")
    return ParsedDataset(
        frame=frame,
        file_kind="excel",
        encoding=None,
        delimiter=None,
        sheet_name=target,
        sheet_names=sheets,
        coercion_issues=issues["issues"],
        original_columns=original[: frame.width],
    )


def _normalise_frame(frame: pl.DataFrame) -> pl.DataFrame:
    new_names = normalise_columns(list(frame.columns))
    frame = frame.rename(dict(zip(frame.columns, new_names)))
    # Drop rows that are entirely null (trailing blank spreadsheet rows).
    if frame.height:
        frame = frame.filter(~pl.all_horizontal(pl.all().is_null()))
    return frame


def _coerce_types(frame: pl.DataFrame) -> dict:
    """Convert obviously-typed string columns and record coercion losses."""
    issues: list[dict] = []
    casts: dict[str, pl.Series] = {}
    for name in frame.columns:
        series = frame.get_column(name)
        if series.dtype not in (pl.String, pl.Utf8):
            continue
        non_null = series.drop_nulls()
        if non_null.len() == 0:
            continue
        sample = non_null.head(500).cast(pl.String)

        # Numeric?
        numeric_like = 0
        numeric_sample: list[float] = []
        for value in sample.to_list():
            cleaned = CURRENCY_STRIP.sub("", str(value))
            try:
                numeric_sample.append(float(cleaned))
                numeric_like += 1
            except ValueError:
                pass
        if numeric_like >= max(1, int(len(sample) * 0.95)):
            try:
                cleaned_series = (
                    series.cast(pl.String, strict=False).str.replace_all(r"[₹$€£,\s]", "").cast(pl.Float64, strict=False)
                )
                failures = cleaned_series.is_null().sum() - series.is_null().sum()
                if failures > 0:
                    issues.append({
                        "column": name,
                        "issue": "type_mismatch",
                        "count": int(failures),
                        "detail": f"{int(failures)} value(s) could not be parsed as numbers and were nulled during profiling.",
                    })
                all_int = all(float(v).is_integer() for v in numeric_sample)
                if all_int and numeric_like == len(sample):
                    casts[name] = cleaned_series.cast(pl.Int64, strict=False)
                else:
                    casts[name] = cleaned_series
                continue
            except Exception:  # noqa: BLE001
                pass

        # Date?
        best: tuple[pl.Series, int] | None = None
        for fmt in DATE_FORMATS:
            try:
                parsed = series.str.to_date(fmt, strict=False)
            except Exception:  # noqa: BLE001
                continue
            valid = parsed.drop_nulls().len()
            if best is None or valid > best[1]:
                best = (parsed, valid)
        if best is not None and best[1] >= max(1, int(non_null.len() * 0.9)):
            failures = non_null.len() - best[1]
            if failures > 0:
                issues.append({
                    "column": name,
                    "issue": "date_parse_partial",
                    "count": int(failures),
                    "detail": f"{failures} value(s) did not match the detected date format.",
                })
            casts[name] = best[0]
            continue

    updated = frame.with_columns(list(casts.values())) if casts else frame
    return {"frame": updated, "issues": issues}


def frame_preview(frame: pl.DataFrame, limit: int = 50) -> dict:
    limit = max(1, min(limit, 500))
    head = frame.head(limit)
    rows = []
    for row in head.iter_rows(named=True):
        rows.append({k: _json_safe(v) for k, v in row.items()})
    return {"columns": list(head.columns), "rows": rows, "row_count": frame.height, "preview_rows": len(rows)}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_parquet(frame: pl.DataFrame, path) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(str(path), compression="zstd")


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------
def _col_type(series: pl.Series) -> str:
    dtype = series.dtype
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return "integer"
    if dtype in (pl.Float32, pl.Float64, pl.Decimal):
        return "decimal"
    if dtype == pl.Boolean:
        return "boolean"
    if dtype == pl.Date:
        return "date"
    if dtype in (pl.Datetime,):
        return "datetime"
    return "string"


def _numeric_stats(series: pl.Series) -> dict:
    values = series.drop_nulls()
    if values.len() == 0:
        return {}
    try:
        q1 = float(values.quantile(0.25))
        q3 = float(values.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = values.filter((values < lower) | (values > upper))
        return {
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": round(float(values.mean()), 4),
            "median": float(values.median()),
            "std": round(float(values.std() or 0), 4),
            "p25": round(q1, 4),
            "p75": round(q3, 4),
            "sum": round(float(values.sum()), 4),
            "non_negative": bool((values >= 0).all()),
            "outliers": {
                "method": "IQR (1.5x)",
                "lower_bound": round(lower, 4),
                "upper_bound": round(upper, 4),
                "count": int(outliers.len()),
                "pct": round(100 * outliers.len() / max(1, values.len()), 3),
                "examples": [float(v) for v in outliers.head(5).to_list()],
            },
        }
    except Exception:  # noqa: BLE001 - guard exotic dtypes
        return {}


def _top_values(series: pl.Series, limit: int = 8) -> list[dict]:
    counts = series.drop_nulls().value_counts(sort=True).head(limit)
    value_col = counts.columns[0]
    return [
        {"value": _json_safe(row[value_col]), "count": int(row["count"])}
        for row in counts.iter_rows(named=True)
    ]


def _consistency_issues(series: pl.Series) -> int:
    if series.dtype not in (pl.String, pl.Utf8):
        return 0
    values = series.drop_nulls().cast(pl.String)
    if values.len() == 0:
        return 0
    untrimmed = values.filter(values != values.str.strip_chars()).len()
    lowered = values.str.to_lowercase()
    mixed_case = values.filter(values != lowered).len() if lowered.n_unique() < values.n_unique() else 0
    return int(untrimmed + max(0, mixed_case - untrimmed))


def profile_frame(frame: pl.DataFrame, coercion_issues: list[dict] | None = None) -> dict:
    rows = frame.height
    cols = frame.width
    coercion_issues = coercion_issues or []
    duplicate_rows = max(0, rows - frame.unique(maintain_order=True).height)
    missing_cells = int(sum(frame.get_column(c).null_count() for c in frame.columns))
    total_cells = max(1, rows * cols)
    completeness = 1 - missing_cells / total_cells
    uniqueness = 1 - (duplicate_rows / rows if rows else 0)

    columns: list[dict] = []
    invalid_cells = sum(int(i.get("count", 0)) for i in coercion_issues)
    consistency_penalty = 0
    outlier_cells = 0
    categorical_cols: list[str] = []
    date_cols: list[str] = []

    for idx, name in enumerate(frame.columns):
        series = frame.get_column(name)
        col_type = _col_type(series)
        non_null = series.drop_nulls()
        null_count = int(series.null_count())
        unique_count = int(non_null.n_unique())
        entry: dict = {
            "name": name,
            "inferred_type": col_type,
            "ordinal_position": idx,
            "null_count": null_count,
            "null_pct": round(100 * null_count / max(1, rows), 2),
            "unique_count": unique_count,
            "unique_pct": round(100 * unique_count / max(1, len(non_null)), 2),
            "sample_values": [_json_safe(v) for v in non_null.head(5).to_list()],
            "stats": {},
            "top_values": [],
            "issues": [],
        }
        if col_type in ("integer", "decimal"):
            stats = _numeric_stats(series)
            entry["stats"] = stats
            outliers = stats.get("outliers", {})
            outlier_cells += int(outliers.get("count", 0))
            if outliers.get("count", 0) > 0:
                entry["issues"].append(
                    f"{outliers['count']} statistical outlier(s) flagged for review (not removed)."
                )
            if stats.get("min", 0) is not None and stats.get("min", 0) < 0:
                entry["issues"].append("Contains negative values — confirm whether these are refunds or corrections.")
            entry["top_values"] = _top_values(series)
        elif col_type in ("date", "datetime"):
            date_cols.append(name)
            if non_null.len():
                entry["stats"] = {
                    "min": str(non_null.min()),
                    "max": str(non_null.max()),
                    "span_days": (non_null.max() - non_null.min()).days
                    if hasattr(non_null.max() - non_null.min(), "days")
                    else None,
                }
            entry["top_values"] = _top_values(series)
        else:
            entry["top_values"] = _top_values(series)
            consistency_penalty += _consistency_issues(series)
            if unique_count <= 50:
                categorical_cols.append(name)
            if unique_count == len(non_null) and len(non_null) > 50:
                entry["stats"] = {"identifier_like": True, "cardinality": "unique"}
        if null_count:
            entry["issues"].append(f"{null_count} missing value(s) ({entry['null_pct']}%).")
        columns.append(entry)

    validity = 1 - (invalid_cells / total_cells)
    consistency = 1 - min(0.5, consistency_penalty / total_cells)
    outlier_control = 1 - min(0.25, (outlier_cells / max(1, rows)) / 4)

    components = {
        "completeness": round(completeness, 4),
        "uniqueness": round(max(0.0, uniqueness), 4),
        "validity": round(max(0.0, validity), 4),
        "consistency": round(max(0.0, consistency), 4),
        "outlier_control": round(max(0.0, outlier_control), 4),
    }
    score = 100 * (
        0.35 * components["completeness"]
        + 0.15 * components["uniqueness"]
        + 0.20 * components["validity"]
        + 0.15 * components["consistency"]
        + 0.15 * components["outlier_control"]
    )

    recommendations = _recommendations(columns, duplicate_rows, rows, coercion_issues)
    issues = [
        {"column": i["column"], "issue": i["issue"], "detail": i["detail"]} for i in coercion_issues
    ]
    if duplicate_rows:
        issues.append({
            "column": None,
            "issue": "duplicate_rows",
            "detail": f"{duplicate_rows} fully duplicated row(s) detected.",
        })

    return {
        "row_count": rows,
        "column_count": cols,
        "duplicate_rows": duplicate_rows,
        "duplicate_pct": round(100 * duplicate_rows / max(1, rows), 3),
        "missing_cells": missing_cells,
        "completeness_pct": round(100 * completeness, 2),
        "quality_score": round(score, 1),
        "quality_components": components,
        "quality_formula": {
            "expression": "100 * (0.35*completeness + 0.15*uniqueness + 0.20*validity + 0.15*consistency + 0.15*outlier_control)",
            "definitions": {
                "completeness": "1 - null cells / total cells",
                "uniqueness": "1 - fully duplicated rows / row count",
                "validity": "1 - values that failed type coercion / total cells",
                "consistency": "1 - whitespace/case inconsistencies in text columns / total cells (capped at 0.5 penalty)",
                "outlier_control": "1 - (share of IQR outliers / 4), capped at a 0.25 penalty",
            },
        },
        "columns": columns,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "date_ranges": {
            c: next((col["stats"] for col in columns if col["name"] == c), {}) for c in date_cols
        },
        "issues": issues,
        "recommendations": recommendations,
        "cleaning_plan": _cleaning_plan(duplicate_rows, columns),
    }


def _recommendations(columns: list[dict], duplicates: int, rows: int, coercion: list[dict]) -> list[dict]:
    recs: list[dict] = []
    if duplicates:
        recs.append({
            "id": "drop_duplicates",
            "title": "Remove fully duplicated rows",
            "detail": f"{duplicates} of {rows} rows are exact duplicates.",
            "impact": "high",
            "action": "drop_duplicates",
        })
    null_cols = [c for c in columns if c["null_count"] > 0]
    if null_cols:
        worst = sorted(null_cols, key=lambda c: c["null_pct"], reverse=True)[:3]
        recs.append({
            "id": "review_missing",
            "title": "Review missing values before modelling",
            "detail": "Columns with missing values: " + ", ".join(f"{c['name']} ({c['null_pct']}%)" for c in worst),
            "impact": "medium",
            "action": "review_missing",
        })
    for issue in coercion:
        recs.append({
            "id": f"fix_{issue['column']}",
            "title": f"Normalise values in '{issue['column']}'",
            "detail": issue["detail"],
            "impact": "medium",
            "action": "review_type",
        })
    outlier_cols = [c for c in columns if c["stats"].get("outliers", {}).get("count", 0) > 0]
    if outlier_cols:
        recs.append({
            "id": "review_outliers",
            "title": "Investigate statistical outliers",
            "detail": "IQR outliers in: " + ", ".join(c["name"] for c in outlier_cols[:4]),
            "impact": "low",
            "action": "review_outliers",
        })
    text_cols = [c for c in columns if c["inferred_type"] == "string" and c["unique_count"] > 0]
    if text_cols:
        recs.append({
            "id": "trim_whitespace",
            "title": "Trim whitespace in text columns",
            "detail": "Removes leading/trailing spaces that fragment categorical groupings.",
            "impact": "low",
            "action": "trim_whitespace",
        })
    return recs


def _cleaning_plan(duplicates: int, columns: list[dict]) -> dict:
    operations = []
    if duplicates:
        operations.append({"op": "drop_duplicates", "label": "Drop fully duplicated rows", "rows": duplicates})
    operations.append({"op": "trim_whitespace", "label": "Trim whitespace in text columns"})
    null_cols = [c["name"] for c in columns if c["null_count"] > 0]
    if null_cols:
        operations.append({"op": "drop_all_null_rows", "label": "Drop rows where every value is null"})
    return {"operations": operations, "auto_applied": False}


def apply_cleaning(frame: pl.DataFrame, operations: list[str]) -> tuple[pl.DataFrame, list[dict]]:
    """Apply only explicitly approved, reversible, documented cleaning operations."""
    applied: list[dict] = []
    allowed = {"drop_duplicates", "trim_whitespace", "drop_all_null_rows"}
    for op in operations:
        if op not in allowed:
            continue
        before = frame.height
        if op == "drop_duplicates":
            frame = frame.unique(maintain_order=True)
        elif op == "trim_whitespace":
            string_cols = [c for c, dt in frame.schema.items() if dt in (pl.String, pl.Utf8)]
            if string_cols:
                frame = frame.with_columns([pl.col(c).str.strip_chars().alias(c) for c in string_cols])
        elif op == "drop_all_null_rows":
            frame = frame.filter(~pl.all_horizontal(pl.all().is_null()))
        applied.append({"op": op, "rows_before": before, "rows_after": frame.height})
    return frame, applied
