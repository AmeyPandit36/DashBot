"""Semantic model proposal, editing, approval and glossary indexing."""
from __future__ import annotations

import copy

import pytest

from tests.conftest import load_demo


@pytest.fixture()
def dataset(account):
    return load_demo(account)


def test_proposal_is_grounded_in_real_columns(account, dataset):
    model = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    definition = model["definition"]
    assert model["status"] == "proposed"
    assert model["generated_by"] in {"heuristic", "gemini"}
    names = {metric["name"] for metric in definition["metrics"]}
    assert {"total_revenue", "total_orders", "average_order_value"} <= names
    assert {dim["name"] for dim in definition["dimensions"]} >= {"region", "category", "customer_segment"}
    assert definition["time_dimensions"][0]["name"] == "order_date"
    # Every metric must point at a real column (RATIO metrics point at their numerator's column).
    profile = account.get(f"/datasets/{dataset['dataset_id']}/profile").json()["data"]["profile"]
    columns = {column["name"] for column in profile["columns"]}
    for metric in definition["metrics"]:
        assert metric["source_column"] in columns


def test_invalid_metrics_are_dropped_with_a_report(account, dataset):
    model = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    definition = copy.deepcopy(model["definition"])
    definition["metrics"].append(
        {
            "name": "ghost_metric",
            "label": "Ghost Metric",
            "source_column": "does_not_exist",
            "aggregation": "SUM",
            "format": "number",
        }
    )
    response = account.put(f"/semantic-models/{model['id']}", json={"definition": definition})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert "ghost_metric" not in {m["name"] for m in payload["definition"]["metrics"]}
    assert any("ghost_metric" in dropped for dropped in payload["validation"]["dropped_metrics"])


def test_approval_indexes_glossary_and_creates_draft_dashboard(account, dataset):
    model = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    response = account.post(f"/semantic-models/{model['id']}/approve", json={"approved": True})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["status"] == "approved"
    assert payload["approved_at"]
    assert payload["dashboard_draft"]["status"] == "draft"

    documents = account.get(f"/documents?workspace_id={account.workspace_id}").json()["data"]
    glossary = [doc for doc in documents if doc["document_type"] == "glossary"]
    assert glossary and glossary[0]["chunk_count"] >= 1

    dataset_payload = account.get(f"/datasets/{dataset['dataset_id']}").json()["data"]
    assert dataset_payload["semantic_status"] == "approved"


def test_editing_an_approved_model_creates_a_review_version(account, dataset):
    model = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    approved = account.post(f"/semantic-models/{model['id']}/approve", json={"approved": True}).json()["data"]
    definition = copy.deepcopy(approved["definition"])
    definition["metrics"][0]["description"] = "Edited description for review."

    response = account.put(f"/semantic-models/{approved['id']}", json={"definition": definition})
    assert response.status_code == 200, response.text
    edited = response.json()["data"]
    assert edited["version"] == approved["version"] + 1
    assert edited["status"] == "proposed"
    assert edited["generated_by"] == "user"
    assert edited["definition"]["metrics"][0]["description"] == "Edited description for review."


def test_regeneration_creates_a_new_version(account, dataset):
    before = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    response = account.post("/semantic-models/generate", json={"dataset_id": dataset["dataset_id"], "regenerate": True})
    assert response.status_code == 200, response.text
    after = response.json()["data"]
    assert after["version"] > before["version"]
    assert after["status"] == "proposed"


def test_rejecting_a_model(account, dataset):
    model = account.get(f"/semantic-models/dataset/{dataset['dataset_id']}").json()["data"]
    response = account.post(f"/semantic-models/{model['id']}/approve", json={"approved": False})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "rejected"
