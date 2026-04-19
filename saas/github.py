import base64

import requests


def github_headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }


def get_repos(token):
    response = requests.get(
        "https://api.github.com/user/repos",
        headers=github_headers(token),
        params={"visibility": "all", "affiliation": "owner,collaborator,organization_member", "per_page": 100},
        timeout=30,
    )
    response.raise_for_status()
    repos = response.json()
    return [
        {
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
            "owner": {"login": (repo.get("owner") or {}).get("login", "")},
        }
        for repo in repos
    ]


def get_repo_details(token, owner, repo_name):
    repo_response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo_name}",
        headers=github_headers(token),
        timeout=30,
    )
    repo_response.raise_for_status()
    repo = repo_response.json()

    readme_text = "README not available for this repository."
    readme_response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo_name}/readme",
        headers=github_headers(token),
        timeout=30,
    )
    if readme_response.status_code == 200:
        readme_payload = readme_response.json()
        encoded_content = readme_payload.get("content", "")
        if encoded_content:
            readme_text = base64.b64decode(encoded_content).decode("utf-8", errors="replace")
    elif readme_response.status_code != 404:
        readme_response.raise_for_status()

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
