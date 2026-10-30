"""The synthetic retail generator is deterministic and tells the documented story."""
from __future__ import annotations

import hashlib

from app.analytics.retail import generate_retail_rows, retail_csv_bytes, retail_customers_csv_bytes


def test_generator_is_deterministic():
    first = retail_csv_bytes()
    second = retail_csv_bytes()
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    other_seed = retail_csv_bytes(seed=12345)
    assert other_seed != first


def test_contract_columns_and_monthly_coverage():
    rows = generate_retail_rows()
    assert len(rows) > 5000
    expected = {
        "order_id", "order_date", "customer_id", "customer_segment", "region",
        "product_id", "product_name", "category", "quantity", "unit_price",
        "discount", "total_amount",
    }
    assert set(rows[0]) == expected
    months = {row["order_date"][:7] for row in rows}
    assert len(months) >= 20
    assert max(months) == "2026-09"


def test_revenue_arithmetic_is_consistent():
    for row in generate_retail_rows()[:500]:
        expected = round(row["quantity"] * row["unit_price"] * (1 - row["discount"]), 2)
        assert abs(row["total_amount"] - expected) < 0.02
        assert row["quantity"] >= 1
        assert 0 <= row["discount"] <= 0.35


def test_last_quarter_softness_is_real():
    rows = generate_retail_rows()
    def revenue(month_prefixes):
        return sum(row["total_amount"] for row in rows if row["order_date"][:7] in month_prefixes)
    recent = revenue({"2026-07", "2026-08", "2026-09"})
    prior = revenue({"2026-04", "2026-05", "2026-06"})
    assert recent < prior  # the generated decline the demo story relies on


def test_customer_reference_table():
    data = retail_customers_csv_bytes().decode()
    lines = data.strip().splitlines()
    assert lines[0] == "customer_id,segment,region,lifetime_value"
    assert len(lines) == 401
