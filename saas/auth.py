import os
import secrets
from urllib.parse import urlencode, parse_qs
import requests
from flask import request, session


def get_github_auth_url():
    """Generate GitHub OAuth authorization URL with state parameter."""
    # Generate a random state token for CSRF protection
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:5000/callback")
    
    params = urlencode(
        {
            "client_id": os.environ["GITHUB_CLIENT_ID"],
            "redirect_uri": redirect_uri,
            "scope": "repo read:user",
            "state": state,
        }
    )
    return f"https://github.com/login/oauth/authorize?{params}"


def validate_oauth_state(request_state):
    """Validate OAuth state parameter to prevent CSRF attacks."""
    stored_state = session.get('oauth_state')
    if not stored_state or not request_state:
        return False
    # Use constant-time comparison to prevent timing attacks
    import hmac
    return hmac.compare_digest(stored_state, request_state)


def get_github_token():
    """Exchange OAuth code for GitHub access token."""
    code = request.args.get("code")
    state = request.args.get("state")
    
    if not code:
        raise ValueError("Missing 'code' parameter in OAuth callback")
    
    if not validate_oauth_state(state):
        raise ValueError("Invalid state parameter - CSRF protection failed")
    
    # Clear the state token after validation
    session.pop('oauth_state', None)
    
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:5000/callback")
    
    try:
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": os.environ["GITHUB_CLIENT_ID"],
                "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            raise ValueError(f"GitHub OAuth error: {data.get('error_description', data.get('error'))}")
        
        if "access_token" not in data:
            raise ValueError("No access token in GitHub response")
        
        return data["access_token"]
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to exchange GitHub OAuth code: {str(e)}")


def get_github_user(token):
    """Fetch authenticated GitHub user profile."""
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "login": data.get("login"),
            "name": data.get("name"),
            "avatar_url": data.get("avatar_url"),
            "email": data.get("email"),
        }
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch GitHub user: {str(e)}")

