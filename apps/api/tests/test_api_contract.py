"""HTTP contract, authentication and tenancy boundaries."""
from __future__ import annotations

import pytest

from tests.conftest import register


def test_health_and_config_are_public(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["llm"]["configured"] is False  # no key in tests -> deterministic mode

    config = client.get("/api/v1/meta/config").json()
    assert config["success"] is True
    assert config["data"]["demo_dataset"]["synthetic"] is True
    assert config["data"]["query_limits"]["row_limit"] > 0


def test_envelope_shape_on_error(client):
    response = client.get("/api/v1/datasets")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"]
    assert body["error"]["request_id"].startswith("req_")


def test_register_login_me_logout(client):
    account = register(client)
    me = account.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"]["email"] == account.email
    assert me.json()["data"]["workspaces"][0]["id"] == account.workspace_id

    logout = account.post("/auth/logout")
    assert logout.status_code == 200

    login = client.post(
        "/api/v1/auth/login", json={"email": account.email, "password": account.password}
    )
    assert login.status_code == 200
    token = login.json()["data"]["token"]
    assert token

    bad = client.post("/api/v1/auth/login", json={"email": account.email, "password": "wrong-password"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_cookie_session_authenticates_browser_requests(client):
    register(client)
    # A browser only carries the http-only cookie; no Authorization header.
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"]


def test_password_reset_flow(client):
    account = register(client)
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": account.email})
    assert forgot.status_code == 200
    token = forgot.json()["data"]["development_reset_token"]
    assert token

    reset = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "BrandNewPass456!"})
    assert reset.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": account.email, "password": "BrandNewPass456!"})
    assert login.status_code == 200


def test_registration_validation(client):
    weak = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "short", "full_name": "X"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "VALIDATION_ERROR"

    duplicate = client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "StrongPass123!", "full_name": "Dupe"},
    )
    assert duplicate.status_code == 200
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "dupe@example.com", "password": "StrongPass123!", "full_name": "Dupe"},
    )
    assert again.status_code == 409


def test_workspaces_and_members(account):
    created = account.post("/workspaces", json={"name": "Second workspace"})
    assert created.status_code == 200
    workspace_id = created.json()["data"]["id"]

    listing = account.get("/workspaces").json()["data"]
    assert {workspace["id"] for workspace in listing} >= {account.workspace_id, workspace_id}

    renamed = account.patch(f"/workspaces/{workspace_id}", json={"name": "Renamed workspace"})
    assert renamed.json()["data"]["name"] == "Renamed workspace"

    invite = account.post("/members/invite", json={"email": "colleague@example.com", "role": "analyst"})
    assert invite.status_code == 200
    assert invite.json()["data"]["invited"] is True

    members = account.get("/members").json()["data"]
    assert members["members"][0]["email"] == account.email
    assert members["members"][0]["role"] == "owner"


def test_viewer_role_cannot_write(account):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import Membership

    # Build a dataset while the caller still owns the organisation.
    created = account.post("/datasets/demo", json={"workspace_id": account.workspace_id})
    assert created.status_code == 200
    dataset_id = created.json()["data"]["dataset_id"]

    db = SessionLocal()
    try:
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == account.user_id,
                Membership.organization_id == account.organization_id,
            )
        )
        membership.role = "viewer"
        db.commit()
    finally:
        db.close()

    blocked = account.post("/datasets/demo", json={"workspace_id": account.workspace_id})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    clean = account.post(f"/datasets/{dataset_id}/clean", json={"operations": ["trim_whitespace"]})
    assert clean.status_code == 403

    readable = account.get(f"/datasets/{dataset_id}")
    assert readable.status_code == 200

    db = SessionLocal()
    try:
        membership = db.get(Membership, membership.id)
        membership.role = "owner"
        db.commit()
    finally:
        db.close()


def test_cross_tenant_isolation(client, seeded):
    outsider = register(client, organization="Other Corp")
    dataset_id = seeded["dataset"]["id"]

    assert outsider.get(f"/datasets/{dataset_id}").status_code == 404
    assert outsider.get(f"/datasets/{dataset_id}/profile").status_code == 404
    assert outsider.get(f"/dashboards/{seeded['dashboard']['id']}").status_code == 404
    assert outsider.get(f"/semantic-models/dataset/{dataset_id}").status_code == 404

    # list endpoints never leak another tenant's rows
    assert outsider.get(f"/datasets?workspace_id={seeded['account'].workspace_id}").status_code == 404
    assert outsider.get("/insights?workspace_id=" + seeded["account"].workspace_id).status_code == 404


def test_workspace_scoping_inside_same_organization(account):
    other = account.post("/workspaces", json={"name": "Isolated workspace"}).json()["data"]
    response = account.get(f"/datasets?workspace_id={other['id']}")
    assert response.status_code == 200
    assert response.json()["data"] == []
