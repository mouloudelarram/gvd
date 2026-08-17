"""Comprehensive test suite for GVD Flask application."""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from app import app, timeago_filter, build_repo_key


class TestFlaskApp:
    """Test Flask application functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        with app.test_client() as client:
            yield client
    
    @pytest.fixture
    def mock_session(self):
        """Session data for authenticated requests."""
        return {
            'access_token': 'test_token',
            'user': {'login': 'testuser', 'name': 'Test User'},
        }

    def test_index_redirects_to_login_when_not_authenticated(self, client):
        """Test index redirects to login when not authenticated."""
        response = client.get('/')
        assert response.status_code == 302 or response.status_code == 200
        if response.status_code == 200:
            assert b'login' in response.data.lower()
    
    def test_dashboard_requires_authentication(self, client):
        """Test dashboard requires authentication."""
        response = client.get('/dashboard')
        assert response.status_code == 302

    def test_callback_access_denied_shows_friendly_message(self, client):
        """User declining GitHub consent gets a clear, journey-specific page."""
        response = client.get('/callback?error=access_denied'
                              '&error_description=The+user+denied+the+request')
        assert response.status_code == 400
        body = response.data.decode()
        assert 'Authorization Cancelled' in body
        # GitHub-controlled error_description must NOT be reflected into the page.
        assert 'denied the request' not in body

    def test_callback_generic_oauth_error_shows_error_page(self, client):
        """Any other OAuth provider error renders the generic error page (400)."""
        response = client.get('/callback?error=server_error')
        assert response.status_code == 400
        assert b'Authentication Error' in response.data

    def test_404_renders_error_page_with_status_code(self, client):
        """404 error page must show the status code + a human message (not blank)."""
        response = client.get('/this-route-does-not-exist')
        assert response.status_code == 404
        body = response.data.decode()
        # The template renders {{ status }}; the buggy handler passed status_code=.
        assert '404' in body
        assert 'Page Not Found' in body

    def test_timeago_filter(self):
        """Test timeago filter functionality."""
        # Test None input
        assert timeago_filter(None) == "No recent activity"
        
        # Test empty string
        assert timeago_filter("") == "No recent activity"
        
        # Test invalid date
        assert timeago_filter("invalid") == "Unknown time"
    
    def test_build_repo_key(self):
        """Test repository key building (with path-traversal defense)."""
        assert build_repo_key("owner", "repo") == "owner/repo"
        # Traversal attempts are reduced to their final path component.
        assert build_repo_key("../etc", "repo") == "etc/repo"
        assert build_repo_key("owner", "repo-name") == "owner/repo-name"

    @patch('app.get_repos')
    def test_dashboard_with_authentication(self, mock_get_repos, client, mock_session):
        """Test dashboard with authentication."""
        mock_get_repos.return_value = [
            {
                'name': 'test-repo',
                'full_name': 'testuser/test-repo',
                'visibility': 'public',
                'description': 'Test repository',
                'clone_url': 'https://github.com/testuser/test-repo.git',
                'html_url': 'https://github.com/testuser/test-repo',
                'language': 'Python',
                'updated_at': '2024-01-01T00:00:00Z',
                'default_branch': 'main',
                'stargazers_count': 10,
                'forks_count': 5,
                'owner': {'login': 'testuser'}
            }
        ]
        
        with client.session_transaction() as sess:
            sess.update(mock_session)
        
        response = client.get('/dashboard')
        assert response.status_code == 200
        assert b'test-repo' in response.data
    
    @patch('app.run_repo_scan')
    @patch('app.get_repos')
    def test_scan_endpoint(self, mock_get_repos, mock_run_scan, client, mock_session):
        """Test scan endpoint."""
        mock_get_repos.return_value = [
            {
                'name': 'test-repo',
                'clone_url': 'https://github.com/testuser/test-repo.git',
                'owner': {'login': 'testuser'}
            }
        ]
        
        mock_run_scan.return_value = {
            'repo_name': 'test-repo',
            'total_findings': 0,
            'severity_counts': {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0},
            'findings': []
        }
        
        with client.session_transaction() as sess:
            sess.update(mock_session)
        
        response = client.post('/scan', data={
            'repo_url': 'https://github.com/testuser/test-repo.git',
            'owner': 'testuser',
            'repo_name': 'test-repo'
        })
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'total_findings' in data
    
    def test_scan_endpoint_unauthorized(self, client):
        """Test scan endpoint without authentication."""
        response = client.post('/scan')
        assert response.status_code == 401
    
    def test_logout(self, client, mock_session):
        """Test logout functionality."""
        with client.session_transaction() as sess:
            sess.update(mock_session)
        
        response = client.get('/logout')
        assert response.status_code == 302

    def test_repo_report_denies_cross_user(self, client, tmp_path, monkeypatch):
        """A report is only downloadable by the user who initiated the scan (F-06)."""
        import app as app_module
        monkeypatch.setattr(app_module, 'SCAN_REPORTS_DIR', tmp_path)

        scan_dir = tmp_path / 'alice' / 'repo' / '20260101000000'
        scan_dir.mkdir(parents=True)
        (scan_dir / 'report.json').write_text('{"total_findings": 0}', encoding='utf-8')
        app_module.write_scan_owner(scan_dir, 'alice')

        # A different authenticated user must be forbidden.
        with client.session_transaction() as sess:
            sess['access_token'] = 'token'
            sess['user'] = {'login': 'mallory'}
        forbidden = client.get('/repo-report/alice/repo/20260101000000.json')
        assert forbidden.status_code == 403

        # The initiating user is allowed.
        with client.session_transaction() as sess:
            sess['access_token'] = 'token'
            sess['user'] = {'login': 'alice'}
        allowed = client.get('/repo-report/alice/repo/20260101000000.json')
        assert allowed.status_code == 200

    def test_api_get_job_enforces_owner(self, client, monkeypatch):
        """GET /api/v1/jobs/<id> is owner-scoped (anti-IDOR, F-06)."""
        import app as app_module
        monkeypatch.setattr(
            app_module.jobs_repo, 'get_job',
            lambda jid: {"id": jid, "owner_login": "alice", "status": "completed"},
        )
        # A different user is forbidden.
        with client.session_transaction() as sess:
            sess['access_token'] = 't'
            sess['user'] = {'login': 'mallory'}
        assert client.get('/api/v1/jobs/abc').status_code == 403
        # The owner can read it.
        with client.session_transaction() as sess:
            sess['access_token'] = 't'
            sess['user'] = {'login': 'alice'}
        ok = client.get('/api/v1/jobs/abc')
        assert ok.status_code == 200
        assert ok.get_json()['id'] == 'abc'

    def test_api_list_jobs_scoped_to_user(self, client, monkeypatch):
        """GET /api/v1/jobs only returns the current user's jobs."""
        import app as app_module
        monkeypatch.setattr(
            app_module.jobs_repo, 'list_jobs_for_user',
            lambda login: [{"id": "1", "owner_login": login}],
        )
        with client.session_transaction() as sess:
            sess['access_token'] = 't'
            sess['user'] = {'login': 'alice'}
        resp = client.get('/api/v1/jobs')
        assert resp.status_code == 200
        assert resp.get_json()['jobs'][0]['owner_login'] == 'alice'

    def test_scan_all_status_enforces_owner(self, client, monkeypatch):
        """Polling another user's live job status is forbidden (F-06)."""
        import app as app_module
        monkeypatch.setattr(
            app_module.jobs_repo, 'get_job',
            lambda jid: {"id": jid, "owner_login": "alice"},
        )
        with app_module.BULK_SCAN_JOBS_LOCK:
            app_module.BULK_SCAN_JOBS['job-x'] = {"job_id": "job-x", "status": "running"}
        try:
            with client.session_transaction() as sess:
                sess['access_token'] = 't'
                sess['user'] = {'login': 'mallory'}
            assert client.get('/scan-all/job-x').status_code == 403
            with client.session_transaction() as sess:
                sess['access_token'] = 't'
                sess['user'] = {'login': 'alice'}
            assert client.get('/scan-all/job-x').status_code == 200
        finally:
            with app_module.BULK_SCAN_JOBS_LOCK:
                app_module.BULK_SCAN_JOBS.pop('job-x', None)


class TestAuthModule:
    """Test authentication module."""
    
    def test_github_auth_url_generation(self):
        """Test GitHub OAuth URL generation."""
        from auth import get_github_auth_url

        with app.test_request_context():
            with patch.dict(os.environ, {
                'GITHUB_CLIENT_ID': 'test_client_id',
                'OAUTH_REDIRECT_URI': 'http://localhost:5000/callback'
            }):
                url = get_github_auth_url()
                assert 'github.com/login/oauth/authorize' in url
                assert 'client_id=test_client_id' in url
                assert 'state=' in url

    def test_oauth_state_validation(self):
        """Test OAuth state validation."""
        from auth import validate_oauth_state
        from flask import session

        with app.test_request_context():
            session['oauth_state'] = 'test_state'
            assert validate_oauth_state('test_state') is True
            assert validate_oauth_state('wrong_state') is False
            assert validate_oauth_state(None) is False


class TestGitHubModule:
    """Test GitHub API module."""
    
    @patch('github.requests.get')
    def test_get_repos_success(self, mock_get):
        """Test successful repository fetching."""
        from github import get_repos
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'X-RateLimit-Remaining': '100'}
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                'name': 'test-repo',
                'full_name': 'testuser/test-repo',
                'private': False,
                'description': 'Test repo',
                'clone_url': 'https://github.com/testuser/test-repo.git',
                'html_url': 'https://github.com/testuser/test-repo',
                'language': 'Python',
                'updated_at': '2024-01-01T00:00:00Z',
                'default_branch': 'main',
                'stargazers_count': 10,
                'forks_count': 5,
                'owner': {'login': 'testuser'}
            }
        ]
        
        mock_get.return_value = mock_response
        
        repos = get_repos('test_token')
        assert len(repos) == 1
        assert repos[0]['name'] == 'test-repo'
        assert repos[0]['visibility'] == 'public'
    
    @patch('github.requests.get')
    def test_get_repos_api_error(self, mock_get):
        """Test GitHub API error handling."""
        from github import get_repos
        import requests
        
        mock_get.side_effect = requests.RequestException("API Error")
        
        with pytest.raises(requests.RequestException):
            get_repos('test_token')


class TestCloneModule:
    """Test repository cloning module."""
    
    def test_sanitize_path_component(self):
        """Test path component sanitization."""
        from clone import sanitize_path_component
        
        assert sanitize_path_component('valid-name') == 'valid-name'
        assert sanitize_path_component('name_with.dots') == 'name_with.dots'
        assert sanitize_path_component('name_with-underscores') == 'name_with-underscores'
        
        # Test dangerous components
        with pytest.raises(ValueError):
            sanitize_path_component('..')
        
        with pytest.raises(ValueError):
            sanitize_path_component('')
        
        with pytest.raises(ValueError):
            sanitize_path_component('name/with/slashes')
    
    def test_validate_github_clone_url(self):
        """Clone URLs must be HTTPS, on an approved GitHub host, without creds."""
        from clone import validate_github_clone_url

        # Valid GitHub URL is returned normalized without userinfo.
        assert validate_github_clone_url('https://github.com/user/repo.git') == \
            'https://github.com/user/repo.git'

        # Non-HTTPS scheme is rejected.
        with pytest.raises(ValueError):
            validate_github_clone_url('http://github.com/user/repo.git')

        # Non-approved host is rejected.
        with pytest.raises(ValueError):
            validate_github_clone_url('https://notgithub.com/user/repo.git')

        # Look-alike host (substring bypass) is rejected via parsed hostname.
        with pytest.raises(ValueError):
            validate_github_clone_url('https://github.com.attacker.tld/user/repo.git')

        # Embedded credentials are rejected.
        with pytest.raises(ValueError):
            validate_github_clone_url('https://x-access-token:tok@github.com/user/repo.git')

    def test_git_auth_env_keeps_token_out_of_argv(self):
        """The token must be injected via git config env vars, not the URL/argv."""
        from clone import git_auth_env

        env = git_auth_env('https://github.com/user/repo.git', 'super-secret-token')
        assert env.get('GIT_CONFIG_COUNT') == '1'
        assert env.get('GIT_CONFIG_KEY_0') == 'http.https://github.com/.extraheader'
        # Token is base64-wrapped in a header value, never in plaintext argv.
        assert 'super-secret-token' not in env['GIT_CONFIG_KEY_0']
        assert env['GIT_CONFIG_VALUE_0'].startswith('Authorization: Basic ')
        assert env.get('GIT_TERMINAL_PROMPT') == '0'


class TestReportAuthorization:
    """Per-resource authorization for reports (anti-IDOR, F-06)."""

    def test_scan_owner_round_trip(self, tmp_path):
        from app import write_scan_owner, read_scan_owner

        write_scan_owner(tmp_path, 'alice')
        assert read_scan_owner(tmp_path) == 'alice'

    def test_is_authorized_for_scan(self, tmp_path):
        from app import write_scan_owner, is_authorized_for_scan

        write_scan_owner(tmp_path, 'alice')
        assert is_authorized_for_scan(tmp_path, 'alice') is True
        # A different user is rejected.
        assert is_authorized_for_scan(tmp_path, 'mallory') is False

    def test_is_authorized_for_scan_missing_marker(self, tmp_path):
        from app import is_authorized_for_scan

        # No ownership marker -> access denied (privacy-by-default).
        assert is_authorized_for_scan(tmp_path, 'alice') is False

    def test_is_authorized_for_bulk_report(self, tmp_path):
        import json as _json
        from app import is_authorized_for_bulk_report

        report_path = tmp_path / 'bulk-report.json'
        report_path.write_text(_json.dumps({'owner_login': 'alice'}), encoding='utf-8')
        assert is_authorized_for_bulk_report(report_path, 'alice') is True
        assert is_authorized_for_bulk_report(report_path, 'mallory') is False

    def test_is_authorized_for_bulk_report_missing_owner(self, tmp_path):
        import json as _json
        from app import is_authorized_for_bulk_report

        report_path = tmp_path / 'bulk-report.json'
        report_path.write_text(_json.dumps({'total_findings': 0}), encoding='utf-8')
        # No owner recorded -> denied.
        assert is_authorized_for_bulk_report(report_path, 'alice') is False
        # Missing file -> denied.
        assert is_authorized_for_bulk_report(tmp_path / 'nope.json', 'alice') is False


class TestConfigModule:
    """Test configuration module."""
    
    def test_csrf_token_generation(self):
        """Test CSRF token generation."""
        from config import generate_csrf_token
        from flask import session

        with app.test_request_context():
            token = generate_csrf_token()
            assert token is not None
            assert len(token) > 20
            assert '_csrf_token' in session
            # Subsequent calls within the same session return the same token.
            assert generate_csrf_token() == token

    def test_require_login_decorator(self):
        """Test login requirement decorator."""
        from config import require_login

        @require_login
        def protected_function():
            return "protected"

        with app.test_request_context():
            from flask import session
            session['access_token'] = 'test_token'
            assert protected_function() == "protected"

        with app.test_request_context():
            response = protected_function()
            # Unauthenticated access is redirected to the index.
            assert response.status_code in (301, 302)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
