import os

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from auth import get_github_auth_url, get_github_token, get_github_user
from clone import clone_repos
from github import get_repo_details, get_repos


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]


@app.route("/")
def index():
    if session.get("access_token"):
        return redirect(url_for("dashboard"))
    return render_template("login.html", login_url=get_github_auth_url())


@app.route("/login")
def login():
    return redirect(get_github_auth_url())


@app.route("/callback")
def callback():
    token = get_github_token()
    session["access_token"] = token
    session["user"] = get_github_user(token)
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))
    return render_template(
        "dashboard.html",
        user=session.get("user"),
        repos=get_repos(token),
        message=session.pop("message", None),
    )


@app.route("/clone", methods=["POST"])
def clone():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))
    selected_urls = set(request.form.getlist("repo_urls"))
    repos = [repo for repo in get_repos(token) if repo.get("clone_url") in selected_urls]
    clone_repos(repos, token)
    session["message"] = f"Processed {len(repos)} repos."
    return redirect(url_for("dashboard"))


@app.route("/repo-details/<owner>/<repo_name>")
def repo_details(owner, repo_name):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_repo_details(token, owner, repo_name))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
