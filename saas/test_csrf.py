"""CSRF protection tests (F-12)."""

from app import app
from config import validate_csrf


def test_safe_methods_are_exempt():
    with app.test_request_context("/dashboard", method="GET"):
        # Should not raise even without a token.
        validate_csrf()


def test_health_path_is_exempt():
    with app.test_request_context("/health", method="POST"):
        validate_csrf()


def test_post_without_token_is_rejected():
    from werkzeug.exceptions import BadRequest

    # TESTING must be off so enforcement runs.
    prev = app.config.get("TESTING")
    app.config["TESTING"] = False
    try:
        with app.test_request_context("/scan", method="POST"):
            from flask import session
            session["_csrf_token"] = "expected-token"
            try:
                validate_csrf()
                raised = False
            except BadRequest:
                raised = True
            assert raised is True
    finally:
        app.config["TESTING"] = prev


def test_post_with_matching_header_token_passes():
    prev = app.config.get("TESTING")
    app.config["TESTING"] = False
    try:
        with app.test_request_context(
            "/scan", method="POST", headers={"X-CSRFToken": "expected-token"}
        ):
            from flask import session
            session["_csrf_token"] = "expected-token"
            validate_csrf()  # should not raise
    finally:
        app.config["TESTING"] = prev


def test_post_with_wrong_token_is_rejected():
    from werkzeug.exceptions import BadRequest

    prev = app.config.get("TESTING")
    app.config["TESTING"] = False
    try:
        with app.test_request_context(
            "/scan", method="POST", headers={"X-CSRFToken": "wrong"}
        ):
            from flask import session
            session["_csrf_token"] = "expected-token"
            try:
                validate_csrf()
                raised = False
            except BadRequest:
                raised = True
            assert raised is True
    finally:
        app.config["TESTING"] = prev
