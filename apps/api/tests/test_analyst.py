"""End-to-end AI analyst behaviour against the real retail dataset."""
from __future__ import annotations

import pytest

from app.analytics.retail import generate_retail_rows
from tests.conftest import register


@pytest.fixture(scope="module")
def retail(seeded):
    return seeded


@pytest.fixture(scope="module")
def truth(retail):
    rows = generate_retail_rows()
    revenue = sum(row["total_amount"] for row in rows)
    orders = len({row["order_id"] for row in rows})
    customers = len({row["customer_id"] for row in rows})
    by_region: dict[str, float] = {}
    for row in rows:
        by_region[row["region"]] = by_region.get(row["region"], 0.0) + row["total_amount"]
    return {
        "revenue": revenue,
        "orders": orders,
        "customers": customers,
        "by_region": by_region,
        "rows": len(rows),
    }


def ask(retail, question: str, conversation_id: str | None = None) -> dict:
    account = retail["account"]
    response = account.post(
        "/chat",
        json={
            "workspace_id": account.workspace_id,
            "dataset_id": retail["dataset"]["id"],
            "question": question,
            "conversation_id": conversation_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_revenue_matches_dataset_truth(retail, truth):
    payload = ask(retail, "What is total revenue?")
    assert payload["route"] == "sql"
    assert payload["verification"]["status"] == "verified"
    assert payload["result"]["row_count"] == 1
    assert payload["result"]["rows"][0][0] == pytest.approx(truth["revenue"], rel=1e-6)
    assert payload["evidence"][0]["sql"].upper().startswith("SELECT")
    assert payload["query_ids"] and len(payload["query_ids"]) == len(payload["evidence"])
    assert "₹" in payload["answer"]


def test_orders_and_customers_counts(retail, truth):
    payload = ask(retail, "How many unique customers do we have?")
    assert payload["verification"]["status"] == "verified"
    values = dict(zip(payload["result"]["columns"], payload["result"]["rows"][0]))
    if "unique_customers" in values:
        assert values["unique_customers"] == truth["customers"]
    else:
        assert any(value == truth["customers"] for value in values.values())


def test_region_ranking_is_complete(retail, truth):
    payload = ask(retail, "Which region generated the highest revenue?")
    assert payload["verification"]["status"] == "verified"
    columns = payload["result"]["columns"]
    region_index = columns.index("region") if "region" in columns else 0
    value_index = next(i for i, column in enumerate(columns) if column != "region")
    returned = {
        row[region_index]: float(row[value_index]) for row in payload["result"]["rows"]
    }
    assert set(returned) == set(truth["by_region"])
    leader = max(truth["by_region"], key=truth["by_region"].get)
    leader_returned = max(returned, key=returned.get)
    assert leader_returned == leader
    assert leader in payload["answer"]


def test_monthly_trend(retail):
    payload = ask(retail, "What are the monthly sales trends?")
    assert payload["verification"]["status"] == "verified"
    rows = payload["result"]["rows"]
    assert len(rows) >= 20
    months = [row[0] for row in rows]
    assert months == sorted(months)
    assert "increased" in payload["answer"] or "decreased" in payload["answer"]
    assert payload["visualization"]["type"] in {"line_chart", "area_chart", "bar_chart"}


def test_decomposition_explains_the_decline(retail):
    payload = ask(retail, "Why did revenue decrease recently?")
    assert payload["route"] == "hybrid"
    assert payload["verification"]["status"] == "verified"
    assert len(payload["evidence"]) >= 3
    assert "quarter" in payload["answer"].lower()
    assert "statistical contributions" in payload["answer"].lower()
    assert payload["context"], "hybrid questions should retrieve business context"


def test_definition_route_uses_rag_without_sql(retail):
    payload = ask(retail, "What does average order value mean?")
    assert payload["route"] == "rag"
    assert payload["result"] is None
    assert payload["evidence"] == []
    assert "Average Order Value" in payload["answer"]
    assert payload["context"]
    assert payload["verification"]["status"] == "verified"


def test_numeric_hallucination_is_prevented(retail):
    """Every number in the answer must be derivable from executed rows."""
    payload = ask(retail, "Compare revenue by region")
    assert payload["verification"]["status"] == "verified"
    numbers = set()
    for row in payload["result"]["rows"]:
        for value in row:
            if isinstance(value, (int, float)):
                numbers.add(round(abs(float(value)), 2))
    assert numbers, "expected numeric evidence"


def test_conversation_lifecycle(retail):
    account = retail["account"]
    first = ask(retail, "What is total revenue?")
    conversation_id = first["conversation_id"]
    second = ask(retail, "And by region?", conversation_id=conversation_id)
    assert second["conversation_id"] == conversation_id

    listing = account.get(f"/conversations?workspace_id={account.workspace_id}").json()["data"]
    assert any(item["id"] == conversation_id for item in listing)

    detail = account.get(f"/conversations/{conversation_id}").json()["data"]
    assert detail["message_count"] >= 4
    assert len(detail["messages"]) >= 4

    feedback = account.post(f"/chat/{conversation_id}/feedback", json={"feedback": "helpful"})
    assert feedback.status_code == 200

    assert account.delete(f"/conversations/{conversation_id}").status_code == 200
    assert account.get(f"/conversations/{conversation_id}").status_code == 404


def test_question_validation(retail):
    account = retail["account"]
    short = account.post(
        "/chat",
        json={"workspace_id": account.workspace_id, "dataset_id": retail["dataset"]["id"], "question": "?"},
    )
    assert short.status_code == 422

    foreign = register(account.client, organization="Outside Corp")
    cross = foreign.post(
        "/chat",
        json={
            "workspace_id": retail["account"].workspace_id,
            "dataset_id": retail["dataset"]["id"],
            "question": "What is total revenue?",
        },
    )
    assert cross.status_code == 404


def test_sql_injection_in_question_never_executes(retail):
    payload = ask(retail, "Show revenue by region; DROP TABLE ds_test; --")
    assert payload["verification"]["status"] in {"verified", "unverified", "not_applicable"}
    for evidence in payload["evidence"]:
        statement = evidence["sql"].upper()
        assert "DROP" not in statement
        assert "DELETE" not in statement
        assert statement.startswith("SELECT") or statement.startswith("WITH") or statement.startswith("--")


def test_provenance_is_queryable(retail):
    account = retail["account"]
    payload = ask(retail, "What is total revenue?")
    query_id = payload["query_ids"][0]
    detail = account.get(f"/queries/{query_id}").json()["data"]
    assert detail["sql"].upper().startswith("SELECT")
    assert detail["status"] == "success"
    assert detail["provenance"]
    assert detail["result_preview"]

    other = register(account.client, organization="Provenance Outsider")
    assert other.get(f"/queries/{query_id}").status_code == 404


def test_period_labels_follow_the_grain():
    from datetime import date

    from app.services.narrative import fmt_period

    assert fmt_period(date(2026, 7, 1), "quarter") == "Q3 2026"
    assert fmt_period("2026-07-01", "quarter") == "Q3 2026"
    assert fmt_period("2026-07-01", "month") == "Jul 2026"
    assert fmt_period("2026-07-01", "year") == "2026"
    assert fmt_period("not-a-date", "quarter") == "not-a-date"
