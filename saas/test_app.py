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
        """Mock session with user data."""
        with app.test_request_context():
            session = {
                'access_token': 'test_token',
                'user': {'login': 'testuser', 'name': 'Test User'}
            }
            yield session
    
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
    
    def test_timeago_filter(self):
        """Test timeago filter functionality."""
        # Test None input
        assert timeago_filter(None) == "No recent activity"
        
        # Test empty string
        assert timeago_filter("") == "No recent activity"
        
        # Test invalid date
        assert timeago_filter("invalid") == "Unknown time"
    
    def test_build_repo_key(self):
        """Test repository key building."""
        assert build_repo_key("owner", "repo") == "owner/repo"
        assert build_repo_key("owner/sub", "repo") == "owner/repo"
        assert build_repo_path("owner", "repo-name") == "owner/repo-name"
    
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


class TestAuthModule:
    """Test authentication module."""
    
    def test_github_auth_url_generation(self):
        """Test GitHub OAuth URL generation."""
        from auth import get_github_auth_url
        
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
        
        with patch('flask.session', {'oauth_state': 'test_state'}):
            assert validate_oauth_state('test_state') == True
            assert validate_oauth_state('wrong_state') == False
            assert validate_oauth_state(None) == False


class TestGitHubModule:
    """Test GitHub API module."""
    
    @patch('github.requests.get')
    def test_get_repos_success(self, mock_get):
        """Test successful repository fetching."""
        from github import get_repos
        
        mock_response = Mock()
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
    
    def test_build_clone_url(self):
        """Test clone URL building."""
        from clone import build_clone_url
        
        url = build_clone_url('https://github.com/user/repo.git', 'token123')
        assert url == 'https://x-access-token:token123@github.com/user/repo.git'
        
        # Test invalid URLs
        with pytest.raises(ValueError):
            build_clone_url('http://github.com/user/repo.git', 'token')
        
        with pytest.raises(ValueError):
            build_clone_url('https://notgithub.com/user/repo.git', 'token')


class TestConfigModule:
    """Test configuration module."""
    
    def test_csrf_token_generation(self):
        """Test CSRF token generation."""
        from config import generate_csrf_token
        
        with patch('flask.session', {}):
            token = generate_csrf_token()
            assert token is not None
            assert len(token) > 20
            assert '_csrf_token' in session
    
    def test_require_login_decorator(self):
        """Test login requirement decorator."""
        from config import require_login
        
        @require_login
        def protected_function():
            return "protected"
        
        with patch('flask.session', {'access_token': 'test_token'}):
            result = protected_function()
            assert result == "protected"
        
        with patch('flask.session', {}):
            with patch('flask.redirect') as mock_redirect, \
                 patch('flask.url_for') as mock_url_for:
                mock_url_for.return_value = '/index'
                protected_function()
                mock_redirect.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
