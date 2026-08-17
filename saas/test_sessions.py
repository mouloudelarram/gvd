"""Server-side session tests (F-03): the OAuth token must never hit a cookie."""

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_server_side_session_backend_enabled():
    # A server-side backend is configured (filesystem locally, redis in prod).
    assert app.config.get("SESSION_TYPE") in ("filesystem", "redis")
    # The session interface comes from Flask-Session, not the default cookie one.
    assert "flask_session" in type(app.session_interface).__module__


def test_access_token_never_appears_in_cookies(client):
    secret = "SECRET_GH_TOKEN_should_never_be_in_a_cookie"
    with client.session_transaction() as sess:
        sess["access_token"] = secret

    resp = client.get("/livez")
    # The token must not appear in any Set-Cookie header...
    for header in resp.headers.getlist("Set-Cookie"):
        assert secret not in header
    # ...nor in the stored session cookie value (which is an opaque id).
    cookie = client.get_cookie("gvd_session")
    if cookie is not None:
        assert secret not in cookie.value


def test_rotate_session_clears_pre_auth_data():
    from session_config import rotate_session

    with app.test_request_context():
        from flask import session

        session["oauth_state"] = "pre-auth-value"
        rotate_session(session)
        assert "oauth_state" not in session

