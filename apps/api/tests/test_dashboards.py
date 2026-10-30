"""Dashboard generation, strict schema validation and widget data resolution."""
from __future__ import annotations

import copy

import pytest

from tests.conftest import approve_semantic, load_demo


def _spec(dashboard: dict) -> dict:
    return dashboard["specification"]


def test_automatic_generation_produces_valid_spec(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = _spec(dashboard)
    assert spec["schema_version"]
    assert spec["layout"]["columns"] == 12
    types = {widget["type"] for widget in spec["widgets"]}
    assert {"kpi", "line_chart", "bar_chart", "donut_chart", "data_table"} <= types
    assert len(spec["widgets"]) >= 8
    for widget in spec["widgets"]:
        assert widget["query_ref"] in spec["queries"]
        assert widget["layout"]["x"] + widget["layout"]["w"] <= 12
    assert spec["filters"]
    assert dashboard["status"] == "published"


def test_widget_data_executes_real_sql(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = _spec(dashboard)
    kpi = next(widget for widget in spec["widgets"] if widget["type"] == "kpi")
    response = account.post(f"/dashboards/{dashboard['id']}/widgets/{kpi['id']}/data", json={"filters": []})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["sql"].upper().startswith("SELECT")
    assert payload["rows"] and isinstance(payload["rows"][0][0], (int, float))
    assert payload["row_count"] >= 1

    date_filter = next(f for f in spec["filters"] if f["type"] == "date_range")
    default = date_filter["default_value"]
    filtered = account.post(
        f"/dashboards/{dashboard['id']}/widgets/{kpi['id']}/data",
        json={"filters": [
            {"field": date_filter["field"], "operator": "gte", "value": default["start"]},
            {"field": date_filter["field"], "operator": "lte", "value": default["end"]},
        ]},
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["data"]["row_count"] == 1


def test_widget_filters_are_validated(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = _spec(dashboard)
    kpi = spec["widgets"][0]

    unknown_field = account.post(
        f"/dashboards/{dashboard['id']}/widgets/{kpi['id']}/data",
        json={"filters": [{"field": "total_amount", "operator": "eq", "value": 1}]},
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["error"]["code"] == "INVALID_FILTER"

    bad_value = account.post(
        f"/dashboards/{dashboard['id']}/widgets/{kpi['id']}/data",
        json={"filters": [{"field": "region", "operator": "eq", "value": {"$ne": None}}]},
    )
    assert bad_value.status_code in (400, 422)


def test_unknown_widget_type_is_rejected_at_validation(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = copy.deepcopy(_spec(dashboard))
    spec["widgets"][0]["type"] = "iframe_embed"
    response = account.put(f"/dashboards/{dashboard['id']}", json={"specification": spec})
    assert response.status_code == 422
    assert response.json()["error"]["code"] in {"DASHBOARD_INVALID", "VALIDATION_ERROR"}


def test_dangling_query_reference_is_rejected(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = copy.deepcopy(_spec(dashboard))
    spec["widgets"][0]["query_ref"] = "missing_query"
    response = account.put(f"/dashboards/{dashboard['id']}", json={"specification": spec})
    assert response.status_code == 422


def test_edit_creates_new_version_and_publish_switches(seeded):
    account = seeded["account"]
    dashboard = seeded["dashboard"]
    spec = copy.deepcopy(_spec(dashboard))
    spec["widgets"][0]["title"] = "Edited KPI title"
    response = account.put(f"/dashboards/{dashboard['id']}", json={"specification": spec})
    assert response.status_code == 200, response.text
    updated = response.json()["data"]
    assert updated["version"] > dashboard["version"]
    assert updated["specification"]["widgets"][0]["title"] == "Edited KPI title"

    publish = account.post(f"/dashboards/{dashboard['id']}/publish")
    assert publish.status_code == 200
    versions = account.get(f"/dashboards/{dashboard['id']}/versions").json()["data"]
    assert versions[0]["is_active"] is True


def test_review_mode_creates_draft(account):
    load_demo(account)
    dataset = account.get(f"/datasets?workspace_id={account.workspace_id}").json()["data"][0]
    approve_semantic(account, dataset["id"])
    response = account.post("/dashboards/generate", json={"dataset_id": dataset["id"], "mode": "review"})
    assert response.status_code == 200, response.text
    dashboard = response.json()["data"]
    assert dashboard["status"] == "draft"
    assert dashboard["generation_mode"] == "review"
    assert dashboard["generation_report"]["provider"] in {"deterministic", "gemini"}


def test_generation_requires_approved_semantic_model(account):
    load_demo(account)
    dataset = account.get(f"/datasets?workspace_id={account.workspace_id}").json()["data"][0]
    response = account.post("/dashboards/generate", json={"dataset_id": dataset["id"], "mode": "automatic"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SEMANTIC_NOT_APPROVED"
