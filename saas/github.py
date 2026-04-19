import requests


def get_repos(token):
    response = requests.get(
        "https://api.github.com/user/repos",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
        params={"visibility": "all", "affiliation": "owner,collaborator,organization_member", "per_page": 100},
        timeout=30,
    )
    response.raise_for_status()
    repos = response.json()
    return [
        {
            "name": repo.get("name"),
            "visibility": "private" if repo.get("private") else "public",
            "description": repo.get("description") or "",
        }
        for repo in repos
    ]
