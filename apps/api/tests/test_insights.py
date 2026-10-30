"""Insight generation must be evidence-backed and tenant scoped."""
from __future__ import annotations

import pytest

from tests.conftest import load_demo, register


@pytest.fixture(scope="module")
def insights_payload(seeded):
    account = seeded["account"]
    response = account.post("/insights/generate", json={"dataset_id": seeded["dataset"]["id"]})
    assert response.status_code == 200, response.text
    return account, response.json()["data"]


def test_insights_have_evidence_and_verification(insights_payload):
    _, insights = insights_payload
    assert len(insights) >= 4
    for insight in insights:
        assert insight["title"]
        assert insight["summary"]
        assert insight["verified"] is True
        assert insight["evidence"]
        assert insight["severity"] in {"positive", "warning", "critical", "info"}


def test_insights_are_listed_and_filterable(insights_payload):
    account, insights = insights_payload
    listing = account.get(f"/insights?workspace_id={account.workspace_id}").json()["data"]
    assert len(listing) >= len(insights)

    dataset_id = insights[0]["dataset_id"]
    filtered = account.get(
        f"/insights?workspace_id={account.workspace_id}&dataset_id={dataset_id}"
    ).json()["data"]
    assert all(item["dataset_id"] == dataset_id for item in filtered)


def test_insight_generation_is_tenant_scoped(insights_payload):
    account, _ = insights_payload
    outsider = register(account.client, organization="Insights Outsider")
    response = outsider.post("/insights/generate", json={"dataset_id": insights_payload[1][0]["dataset_id"]})
    assert response.status_code == 404
