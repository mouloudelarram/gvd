"""Server-side session configuration (F-03).

Stores all session data (including the GitHub access token) on the server. The
browser only ever receives an opaque, signed session id â€” the token is never
serialized into a cookie. Defaults to a filesystem backend for local dev; uses
Redis in production (SESSION_TYPE=redis + REDIS_URL).
"""

import os
from pathlib import Path

from flask_session import Session

BASE_DIR = Path(__file__).resolve().parent


def configure_server_side_sessions(app):
    """Attach a server-side session backend to the Flask app."""
    backend = os.environ.get("SESSION_TYPE", "filesystem").strip().lower()

    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_KEY_PREFIX"] = "gvd:"

    if backend == "redis":
        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        app.config["SESSION_TYPE"] = "redis"
        app.config["SESSION_REDIS"] = redis.from_url(redis_url)
    else:
        # Filesystem backend: session payloads live on the server, not the client.
        session_dir = BASE_DIR / "data" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = str(session_dir)

    Session(app)
    return app


def rotate_session(session):
    """Best-effort session hardening after authentication.

    Clears any pre-authentication data (e.g. the OAuth state) so a value planted
    before login cannot survive into the authenticated session, mitigating
    session fixation. Callers set the authenticated values afterwards.
    """
    preserved = {}
    session.clear()
    session.update(preserved)
    session.modified = True

