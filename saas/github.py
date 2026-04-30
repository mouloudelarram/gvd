import base64
import requests
from typing import List, Dict
import time


def github_headers(token):
    """Generate headers for GitHub API requests."""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }


def get_repos(token) -> List[Dict]:
    """Fetch all user repositories with pagination."""
    repos = []
    page = 1
    max_pages = 10  # Limit to 1000 repos (100 per page * 10)
    
    while page <= max_pages:
        try:
            response = requests.get(
                "https://api.github.com/user/repos",
                headers=github_headers(token),
                params={
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc",
                },
                timeout=30,
            )
            
            # Check rate limiting
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            if remaining < 10:
                print(f"Warning: GitHub API rate limit approaching ({remaining} requests remaining)")
            
            response.raise_for_status()
            page_repos = response.json()
            
            if not page_repos:
                break
            
            repos.extend([_normalize_repo(repo) for repo in page_repos])
            
            # Check if there are more pages
            if len(page_repos) < 100:
                break
            
            page += 1
            # Be respectful with API calls
            time.sleep(0.1)
            
        except requests.RequestException as e:
            print(f"Error fetching repositories (page {page}): {e}")
            if page == 1:
                # If first page fails, raise error
                raise
            # For subsequent pages, just return what we have
            break
    
    return repos


def _normalize_repo(repo: Dict) -> Dict:
    """Normalize repository data from GitHub API."""
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "visibility": "private" if repo.get("private") else "public",
        "description": repo.get("description") or "",
        "clone_url": repo.get("clone_url"),
        "html_url": repo.get("html_url"),
        "language": repo.get("language") or "Not specified",
        "updated_at": repo.get("updated_at") or "",
        "default_branch": repo.get("default_branch") or "",
        "stargazers_count": repo.get("stargazers_count", 0),
        "forks_count": repo.get("forks_count", 0),
        "owner": {"login": (repo.get("owner") or {}).get("login", "")},
    }


def search_repos(token, query, visibility="all", page=1, per_page=20):
    """Search user's repositories."""
    if not query or len(query.strip()) < 2:
        return {"repos": [], "total_count": 0, "page": page, "per_page": per_page}
    
    try:
        user_response = requests.get(
            "https://api.github.com/user",
            headers=github_headers(token),
            timeout=30,
        )
        user_response.raise_for_status()
        user_data = user_response.json()
        user_login = user_data.get("login")
        if not user_login:
            return {"repos": [], "total_count": 0, "page": page, "per_page": per_page}
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return {"repos": [], "total_count": 0, "page": page, "per_page": per_page}
    
    params = {
        "q": f"{query} user:{user_login}",
        "type": "repository",
        "sort": "updated",
        "order": "desc",
        "page": page,
        "per_page": per_page,
    }
    
    if visibility != "all":
        params["q"] += f" visibility:{visibility}"
    
    try:
        response = requests.get(
            "https://api.github.com/search/repositories",
            headers=github_headers(token),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        
        repos = [_normalize_repo(item) for item in data.get("items", [])]
        
        return {
            "repos": repos,
            "total_count": data.get("total_count", 0),
            "page": page,
            "per_page": per_page,
            "has_next": len(repos) == per_page,
        }
    except requests.RequestException as e:
        print(f"Error searching repositories: {e}")
        return {"repos": [], "total_count": 0, "page": page, "per_page": per_page}


def get_repo_details(token, owner, repo_name):
    """Fetch detailed information about a specific repository."""
    try:
        repo_response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo_name}",
            headers=github_headers(token),
            timeout=30,
        )
        repo_response.raise_for_status()
        repo = repo_response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch repository details: {e}")
    
    # Fetch README
    readme_text = "README not available for this repository."
    try:
        readme_response = requests.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/readme",
            headers=github_headers(token),
            timeout=30,
        )
        
        if readme_response.status_code == 200:
            try:
                readme_payload = readme_response.json()
                encoded_content = readme_payload.get("content", "")
                if encoded_content:
                    readme_text = base64.b64decode(encoded_content).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                pass
        elif readme_response.status_code != 404:
            readme_response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch README: {e}")
    
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "visibility": "private" if repo.get("private") else "public",
        "description": repo.get("description") or "No description provided.",
        "html_url": repo.get("html_url"),
        "language": repo.get("language") or "Not specified",
        "default_branch": repo.get("default_branch") or "Unknown",
        "stargazers_count": repo.get("stargazers_count", 0),
        "forks_count": repo.get("forks_count", 0),
        "open_issues_count": repo.get("open_issues_count", 0),
        "updated_at": repo.get("updated_at") or "",
        "readme": readme_text,
        "owner": {"login": (repo.get("owner") or {}).get("login", "")},
    }

