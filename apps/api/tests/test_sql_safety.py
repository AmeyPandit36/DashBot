"""The SQL policy layer is the security boundary between the LLM and the data."""
from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.sql.builder import QueryFilter, QuerySpec, build_query, quote
from app.sql.validator import validate_sql

ALLOWED = {"ds_test"}
COLUMNS = {
    "order_id", "order_date", "customer_id", "customer_segment", "region",
    "product_id", "product_name", "category", "quantity", "unit_price",
    "discount", "total_amount",
}

SEMANTIC = {
    "metrics": [
        {"name": "total_revenue", "label": "Revenue", "source_column": "total_amount", "aggregation": "SUM", "format": "currency"},
        {"name": "total_orders", "label": "Orders", "source_column": "order_id", "aggregation": "COUNT_DISTINCT", "format": "integer"},
        {"name": "average_order_value", "label": "AOV", "source_column": "total_amount", "aggregation": "RATIO",
         "format": "currency", "numerator": "total_revenue", "denominator": "total_orders"},
    ],
    "dimensions": [
        {"name": "region", "label": "Region", "source_column": "region", "data_type": "categorical"},
        {"name": "category", "label": "Category", "source_column": "category", "data_type": "categorical"},
    ],
    "time_dimensions": [
        {"name": "order_date", "label": "Order date", "source_column": "order_date", "default_grain": "month"},
    ],
}


def _ok(sql: str) -> bool:
    return validate_sql(sql, ALLOWED, COLUMNS).valid


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT region, SUM(total_amount) FROM ds_test GROUP BY 1",
        "WITH x AS (SELECT * FROM ds_test) SELECT COUNT(*) FROM x",
        "SELECT * FROM main.ds_test LIMIT 10",
    ],
)
def test_read_only_queries_are_allowed(sql):
    assert _ok(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE ds_test",
        "DELETE FROM ds_test",
        "UPDATE ds_test SET region = 'X'",
        "INSERT INTO ds_test SELECT * FROM ds_test",
        "CREATE TABLE evil AS SELECT 1",
        "SELECT * FROM ds_test; DROP TABLE ds_test",
        "SELECT * FROM secrets",
        "SELECT * FROM other_schema.ds_test",
        "ATTACH '/tmp/evil.db' AS evil",
        "COPY ds_test TO '/tmp/leak.csv'",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "PRAGMA database_list",
        "CALL pragma_version()",
        "INSTALL httpfs",
        "SET memory_limit='10GB'",
    ],
)
def test_dangerous_sql_is_rejected(sql):
    result = validate_sql(sql, ALLOWED, COLUMNS)
    assert result.valid is False, sql
    assert result.errors


def test_unknown_columns_are_rejected_when_column_policy_is_enabled():
    result = validate_sql("SELECT region, password FROM ds_test", ALLOWED, COLUMNS)
    assert result.valid is False
    assert any("password" in error for error in result.errors)


def test_row_limit_is_enforced_inside_the_statement():
    capped = validate_sql("SELECT * FROM ds_test LIMIT 100000", ALLOWED, COLUMNS, row_limit=5000)
    assert capped.valid is True
    assert capped.sql.lower().endswith("limit 5000")
    assert any("5000" in warning for warning in capped.warnings)

    unbounded = validate_sql("SELECT * FROM ds_test", ALLOWED, COLUMNS, row_limit=250)
    assert unbounded.valid is True
    assert unbounded.sql.lower().endswith("limit 250")


def test_quote_rejects_non_identifiers():
    assert quote("region") == '"region"'
    for hostile in ('bad"column', "x; DROP TABLE y", "region) --", "1abc"):
        with pytest.raises(AppError):
            quote(hostile)


def test_query_builder_parameterises_filters():
    spec = QuerySpec(
        metrics=["total_revenue"],
        group_by=["region"],
        filters=[QueryFilter(field="region", operator="eq", value="North")],
        limit=5,
    )
    sql, params, columns = build_query(spec, SEMANTIC, "ds_test")
    assert '"region"' in sql
    assert "?" in sql
    assert params == ["North"]
    assert columns == ["region", "total_revenue"]


def test_query_builder_rejects_unknown_metric():
    with pytest.raises(AppError):
        build_query(QuerySpec(metrics=["nonexistent"]), SEMANTIC, "ds_test")


def test_query_spec_rejects_invalid_grain():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        QuerySpec(metrics=["total_revenue"], group_by=["order_date"], grain="fortnight")


def test_ratio_metric_builds_safe_arithmetic():
    sql, _, _ = build_query(QuerySpec(metrics=["average_order_value"]), SEMANTIC, "ds_test")
    assert "NULLIF" in sql.upper()
