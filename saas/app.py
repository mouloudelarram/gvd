import os
import json
import subprocess
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from auth import get_github_auth_url, get_github_token, get_github_user
from clone import clone_repos, ensure_repo_cloned
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
BASE_DIR = Path(__file__).resolve().parent
CLI_EXE = BASE_DIR.parent / "cli" / "dist" / "cli.exe"
SCAN_REPORTS_DIR = BASE_DIR / "scan_reports"


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


def build_scan_result(report_data, owner, repo_name, repo_path, scan_output_dir, command_output):
    findings = report_data.get("findings", [])
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in findings:
        severity = finding.get("severity", "")
        if severity in severity_counts:
            severity_counts[severity] += 1

    return {
        "repo_name": report_data.get("repo_name") or repo_name,
        "owner": owner,
        "repo_path": str(repo_path),
        "scan_output_dir": str(scan_output_dir),
        "total_findings": report_data.get("total_findings", len(findings)),
        "severity_counts": severity_counts,
        "findings": findings,
        "command_output": command_output.strip(),
    }


@app.route("/scan", methods=["POST"])
def scan():
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or request.form
    repo_url = (payload.get("repo_url") or "").strip()
    owner = (payload.get("owner") or "").strip()
    repo_name = (payload.get("repo_name") or "").strip()

    if not repo_url or not owner or not repo_name:
        return jsonify({"error": "Missing repository data."}), 400

    repo = next(
        (
            item for item in get_repos(token)
            if item.get("clone_url") == repo_url
            and (item.get("owner") or {}).get("login") == owner
            and item.get("name") == repo_name
        ),
        None,
    )
    if not repo:
        return jsonify({"error": "Repository not found."}), 404

    if not CLI_EXE.exists():
        return jsonify({"error": f"Scanner executable not found at {CLI_EXE}."}), 500

    try:
        repo_path = ensure_repo_cloned(repo, token)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").replace(token, "[redacted]").strip()
        return jsonify({"error": "Repository clone failed.", "details": stderr}), 500
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    scan_output_dir = SCAN_REPORTS_DIR / Path(owner).name / Path(repo_name).name / timestamp
    scan_output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(CLI_EXE),
        "scan",
        "--path",
        str(repo_path),
        "--output",
        str(scan_output_dir),
        "--format",
        "json",
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=BASE_DIR.parent,
        )
    except subprocess.CalledProcessError as exc:
        return jsonify(
            {
                "error": "Scanner execution failed.",
                "details": (exc.stderr or exc.stdout or "").strip(),
            }
        ), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Scanner timed out."}), 504

    report_path = scan_output_dir / "report.json"
    if not report_path.exists():
        return jsonify({"error": "Scan completed but no report was generated."}), 500

    with open(report_path, encoding="utf-8") as report_file:
        report_data = json.load(report_file)

    return jsonify(
        build_scan_result(
            report_data,
            owner,
            repo_name,
            repo_path,
            scan_output_dir,
            (result.stdout or "") + ("\n" + result.stderr if result.stderr else ""),
        )
    )


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
