"""Configuration and utilities for GVD Flask application."""

import secrets
from flask import session, render_template


def generate_csrf_token():
    """Generate and store a CSRF token in the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_urlsafe(32)
    return session['_csrf_token']


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
