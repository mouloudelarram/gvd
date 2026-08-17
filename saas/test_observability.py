"""Observability tests: correlation IDs + liveness/readiness probes (F-16)."""

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_livez_ok(client):
    resp = client.get("/livez")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "alive"


def test_correlation_id_generated(client):
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) >= 8


def test_correlation_id_echoed(client):
    resp = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert resp.headers.get("X-Request-ID") == "trace-123"


def test_readyz_ready(client, monkeypatch):
    import db

    monkeypatch.setattr(db, "check_db_ready", lambda *a, **k: True)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ready"


def test_readyz_not_ready(client, monkeypatch):
    import db

    monkeypatch.setattr(db, "check_db_ready", lambda *a, **k: False)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "not_ready"


def test_check_db_ready_with_temp_engine(tmp_path):
    import pathlib

    from sqlalchemy import create_engine

    import db

    url = f"sqlite:///{pathlib.Path(tmp_path, 'r.db').as_posix()}"
    engine = create_engine(url, future=True)
    assert db.check_db_ready(engine) is True


# --------------------------------------------------------------------------- #
# Structured logging: redaction (F-16)
# --------------------------------------------------------------------------- #


def test_redact_github_token():
    import observability

    dirty = "cloning with token ghp_" + "a" * 36 + " done"
    clean = observability.redact(dirty)
    assert "ghp_" not in clean
    assert "REDACTED" in clean


def test_redact_bearer_and_kv():
    import observability

    assert "secret-value" not in observability.redact("Authorization: Bearer secret-value")
    assert "hunter2" not in observability.redact("password=hunter2&user=x")


def test_redact_url_credentials():
    import observability

    clean = observability.redact("https://user:tok123@github.com/x/y.git")
    assert "tok123" not in clean
    assert "github.com" in clean


def test_json_formatter_redacts_and_includes_correlation_id():
    import json
    import logging

    import observability

    formatter = observability.JsonFormatter()
    record = logging.makeLogRecord(
        {
            "name": "test",
            "levelname": "INFO",
            "msg": "token ghp_" + "b" * 36,
            "correlation_id": "abc123",
        }
    )
    payload = json.loads(formatter.format(record))
    assert payload["correlation_id"] == "abc123"
    assert "ghp_" not in payload["msg"]
    assert payload["level"] == "INFO"


# --------------------------------------------------------------------------- #
# Metrics registry + /metrics endpoint (F-16)
# --------------------------------------------------------------------------- #


def test_metrics_registry_counter_and_histogram():
    from observability import MetricsRegistry

    reg = MetricsRegistry()
    reg.counter("c_total", "help")
    reg.histogram("h_seconds", "help", buckets=[0.1, 1])
    reg.inc("c_total", {"outcome": "ok"})
    reg.inc("c_total", {"outcome": "ok"})
    reg.observe("h_seconds", 0.05)
    reg.observe("h_seconds", 2.0)
    out = reg.render()
    assert 'c_total{outcome="ok"} 2' in out
    assert "h_seconds_bucket" in out
    assert 'le="+Inf"' in out
    assert "h_seconds_count" in out


def test_metrics_gauge_set():
    from observability import MetricsRegistry

    reg = MetricsRegistry()
    reg.gauge("g", "help")
    reg.set_gauge("g", 5)
    reg.set_gauge("g", 3)
    assert "g 3" in reg.render()


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "gvd_http_requests_total" in body
    assert "gvd_queue_depth" in body


def test_http_request_metric_recorded(client):
    from observability import render_metrics

    client.get("/livez")
    assert "gvd_http_requests_total" in render_metrics()


def test_count_queued_jobs_empty(tmp_path):
    import pathlib

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import db
    import jobs_repo

    url = f"sqlite:///{pathlib.Path(tmp_path, 'jobs.db').as_posix()}"
    engine = create_engine(url, future=True)
    db.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    assert jobs_repo.count_queued_jobs(session_factory=factory) == 0


# --------------------------------------------------------------------------- #
# GitHub API call metrics (F-16)
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_github_get_records_success(monkeypatch):
    import github
    import observability

    monkeypatch.setattr(github.requests, "get", lambda *a, **k: _FakeResponse(200))
    before = observability.render_metrics()
    github.github_get("https://api.github.com/user")
    after = observability.render_metrics()
    assert 'gvd_github_api_calls_total{outcome="success"}' in after
    assert after != before


def test_github_get_records_rate_limited(monkeypatch):
    import github
    import observability

    monkeypatch.setattr(
        github.requests,
        "get",
        lambda *a, **k: _FakeResponse(403, {"X-RateLimit-Remaining": "0"}),
    )
    github.github_get("https://api.github.com/user")
    assert 'gvd_github_api_calls_total{outcome="rate_limited"}' in observability.render_metrics()


def test_github_get_records_network_error(monkeypatch):
    import github
    import observability

    def boom(*a, **k):
        raise github.requests.RequestException("boom")

    monkeypatch.setattr(github.requests, "get", boom)
    with pytest.raises(github.requests.RequestException):
        github.github_get("https://api.github.com/user")
    assert 'gvd_github_api_calls_total{outcome="error"}' in observability.render_metrics()
