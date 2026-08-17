"""Configuration and utilities for GVD Flask application."""

import hmac
import secrets

from flask import abort, current_app, render_template, request, session


def generate_csrf_token():
    """Generate and store a CSRF token in the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


# Methods that never change state and are therefore CSRF-exempt.
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# Paths exempt from CSRF (unauthenticated infra endpoints).
CSRF_EXEMPT_PATHS = {"/health"}


def _csrf_token_from_request():
    """Read the CSRF token from a header (fetch/XHR) or a form field."""
    return (
        request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
        or (request.form.get("csrf_token") if request.form else None)
        or ""
    )


def validate_csrf():
    """Reject state-changing browser requests without a valid CSRF token.

    Uses a constant-time comparison against the per-session token. Skipped for
    safe methods, exempt infra paths, and during tests (``TESTING``), where CSRF
    is covered by dedicated unit tests instead of every integration POST.
    """
    if request.method in CSRF_SAFE_METHODS:
        return
    if request.path in CSRF_EXEMPT_PATHS:
        return
    if current_app.config.get("TESTING"):
        return
    sent = str(_csrf_token_from_request())
    stored = str(session.get("_csrf_token", ""))
    if not stored or not sent or not hmac.compare_digest(stored, sent):
        abort(400, description="CSRF validation failed")


def setup_error_handlers(app):
    """Register error handlers for the Flask app."""
    
    @app.errorhandler(400)
    def bad_request(error):
        """Handle bad request errors."""
        return render_template('error.html', 
                             status=400, 
                             message="Bad Request", 
                             detail="The request was invalid or malformed."), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        """Handle unauthorized access."""
        return render_template('error.html',
                             status=401,
                             message="Unauthorized",
                             detail="Please log in to access this page."), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        """Handle forbidden access."""
        return render_template('error.html',
                             status=403,
                             message="Forbidden",
                             detail="You do not have permission to access this resource."), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Handle not found errors."""
        return render_template('error.html',
                             status=404,
                             message="Page Not Found",
                             detail="The page you requested does not exist."), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle internal server errors."""
        return render_template('error.html',
                             status=500,
                             message="Internal Server Error",
                             detail="An unexpected error occurred. Please try again later."), 500


def require_login(f):
    """Decorator to require user to be logged in."""
    from functools import wraps
    from flask import session, redirect, url_for
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('access_token'):
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
