"""Versioned API tests (F-13): validation, error envelope, OpenAPI."""

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client, login="alice"):
    with client.session_transaction() as sess:
        sess["access_token"] = "token"
        sess["user"] = {"login": login}


def test_openapi_document_is_valid(client):
    resp = client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    spec = resp.get_json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/scans" in spec["paths"]
    assert "/api/v1/jobs" in spec["paths"]
    assert "Error" in spec["components"]["schemas"]


def test_scans_requires_auth_with_envelope(client):
    resp = client.post("/api/v1/scans", json={"type": "bulk"})
    assert resp.status_code == 401
    body = resp.get_json()
    assert body["error"]["code"] == "unauthorized"
    assert "correlation_id" in body["error"]
    # Correlation id is echoed in the header too.
    assert "X-Request-ID" in resp.headers


def test_scans_validation_error_envelope(client):
    _login(client)
    resp = client.post("/api/v1/scans", json={"type": "invalid"})
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["error"]["code"] == "validation_error"
    fields = [d["field"] for d in body["error"]["details"]]
    assert "type" in fields


def test_scans_single_missing_repository(client):
    _login(client)
    resp = client.post("/api/v1/scans", json={"type": "single"})
    assert resp.status_code == 422
    fields = [d["field"] for d in resp.get_json()["error"]["details"]]
    assert "repository" in fields


def test_scans_success_returns_202(client, monkeypatch):
    _login(client)
    import app as app_module

    monkeypatch.setattr(
        app_module, "get_repos",
        lambda token: [{"name": "r", "visibility": "public", "owner": {"login": "alice"}}],
    )
    # Do not actually start a worker thread or touch the DB.
    monkeypatch.setattr(
        app_module, "launch_bulk_scan",
        lambda *a, **k: {"job_id": "j1", "status": "running", "visibility": "both",
                         "total_repositories": 1},
    )
    resp = client.post("/api/v1/scans", json={"type": "bulk", "visibility": "both"})
    assert resp.status_code == 202
    assert resp.get_json()["job_id"] == "j1"


def test_scans_idempotent_replay_returns_200(client, monkeypatch):
    _login(client)
    import app as app_module

    monkeypatch.setattr(
        app_module, "get_repos",
        lambda token: [{"name": "r", "visibility": "public", "owner": {"login": "alice"}}],
    )
    monkeypatch.setattr(
        app_module, "launch_bulk_scan",
        lambda *a, **k: {"job_id": "j1", "status": "running", "idempotent": True},
    )
    resp = client.post(
        "/api/v1/scans", json={"type": "bulk"}, headers={"Idempotency-Key": "abc"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["idempotent"] is True


def test_cancel_job_owner_only(client, monkeypatch):
    import app as app_module

    calls = {}

    def fake_cancel(job_id, owner_login=None):
        calls["args"] = (job_id, owner_login)
        return owner_login == "alice"

    monkeypatch.setattr(app_module.jobs_repo, "request_cancel", fake_cancel)

    _login(client, "alice")
    ok = client.post("/api/v1/jobs/j1/cancel")
    assert ok.status_code == 200
    assert ok.get_json()["status"] == "cancel_requested"
    assert calls["args"] == ("j1", "alice")

    # A non-owner (fake_cancel returns False) gets 404 with the envelope.
    _login(client, "mallory")
    denied = client.post("/api/v1/jobs/j1/cancel")
    assert denied.status_code == 404
    assert denied.get_json()["error"]["code"] == "not_found"
