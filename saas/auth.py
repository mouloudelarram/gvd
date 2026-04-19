import os
from urllib.parse import urlencode

import requests
from flask import request


def get_github_auth_url():
    params = urlencode(
        {
            "client_id": os.environ["GITHUB_CLIENT_ID"],
            "redirect_uri": "http://localhost:5000/callback",
            "scope": "repo read:user",
        }
    )
    return f"https://github.com/login/oauth/authorize?{params}"


def get_github_token():
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": os.environ["GITHUB_CLIENT_ID"],
            "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
            "code": request.args.get("code"),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_github_user(token):
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
    }
