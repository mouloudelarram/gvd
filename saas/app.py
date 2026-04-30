import os
import json
import logging
import threading
import uuid
import subprocess
import requests
import platform
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import wrap

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from markupsafe import escape

from auth import get_github_auth_url, get_github_token, get_github_user, validate_oauth_state
from clone import clone_repos, ensure_repo_cloned
from github import get_repo_details, get_repos, search_repos
from config import generate_csrf_token, setup_error_handlers, require_login


def load_env():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        print(f"Warning: .env file not found at {env_path}")
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    except IOError as e:
        print(f"Error reading .env file: {e}")


load_env()

# Validate required environment variables
required_env_vars = ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "FLASK_SECRET_KEY"]
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}. Please check your .env file.")

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security configuration for session cookies
app.config.update(
    SESSION_COOKIE_SECURE=True,  # Only send over HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # No JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',  # CSRF protection
    SESSION_COOKIE_NAME='gvd_session',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max request size
)

# Setup error handlers
setup_error_handlers(app)

# Register CSRF token generation for all templates
@app.before_request
def before_request():
    """Generate CSRF token for forms before each request."""
    generate_csrf_token()

BASE_DIR = Path(__file__).resolve().parent

def timeago_filter(date_string):
    """Convert a date string to a relative time format."""
    if not date_string:
        return "No recent activity"
    
    try:
        # Parse the date string - GitHub API returns ISO 8601 format
        if isinstance(date_string, str):
            date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        else:
            date_obj = date_string
        
        # Convert to UTC for comparison
        now = datetime.utcnow()
        if date_obj.tzinfo:
            date_obj = date_obj.astimezone().replace(tzinfo=None)
        
        delta = now - date_obj
        seconds = delta.total_seconds()
        
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 2592000:  # 30 days
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 31536000:  # 365 days
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = int(seconds / 31536000)
            return f"{years} year{'s' if years != 1 else ''} ago"
    except (ValueError, TypeError, AttributeError):
        return "Unknown time"

# Register the custom filter
app.jinja_env.filters['timeago'] = timeago_filter


def get_gvd_executable():
    """Get the path to the GVD executable based on the operating system."""
    # For development, use the Python script directly
    # In production, this should be the compiled executable
    cli_script = BASE_DIR.parent / "cli" / "cli.py"
    if cli_script.exists():
        return cli_script
    
    # Fallback to compiled executable if available
    dist_dir = BASE_DIR.parent / "cli" / "dist"
    if platform.system() == "Windows":
        exe_path = dist_dir / "cli.exe"
    else:
        exe_path = dist_dir / "cli"
    
    return exe_path if exe_path.exists() else cli_script

CLI_EXE = get_gvd_executable()
SCAN_REPORTS_DIR = BASE_DIR / "scan_reports"
BULK_SCAN_JOBS = {}
BULK_SCAN_JOBS_LOCK = threading.Lock()
WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class RepoSkippedError(Exception):
    def __init__(self, owner, repo_name):
        super().__init__(f"Skipped {owner}/{repo_name}")
        self.owner = owner
        self.repo_name = repo_name


def build_repo_key(owner, repo_name):
    return f"{Path(owner).name}/{Path(repo_name).name}"


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
    """Handle GitHub OAuth callback."""
    try:
        token = get_github_token()
        user = get_github_user(token)
        session["access_token"] = token
        session["user"] = user
        session.permanent = True
        return redirect(url_for("dashboard"))
    except ValueError as e:
        # OAuth validation error (CSRF, invalid code, etc.)
        return render_template("error.html",
                             status=400,
                             message="Authentication Error",
                             detail=str(e)), 400
    except RuntimeError as e:
        # GitHub API error
        return render_template("error.html",
                             status=500,
                             message="GitHub Connection Error",
                             detail="Could not connect to GitHub. Please try again later."), 500
    except Exception as e:
        # Unexpected error
        return render_template("error.html",
                             status=500,
                             message="Internal Server Error",
                             detail="An unexpected error occurred during authentication."), 500


@app.route("/dashboard")
def dashboard():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))
    visibility = (request.args.get("visibility") or "both").strip().lower()
    if visibility not in {"public", "private", "both"}:
        visibility = "both"
    
    try:
        repos = get_repos(token)
    except Exception as e:
        return render_template("error.html",
                             status=500,
                             message="GitHub API Error",
                             detail="Failed to fetch repositories from GitHub."), 500
    
    if visibility != "both":
        repos = [repo for repo in repos if repo.get("visibility") == visibility]
    
    return render_template(
        "dashboard.html",
        user=session.get("user"),
        repos=repos,
        current_visibility=visibility,
        message=session.pop("message", None),
        csrf_token=generate_csrf_token(),
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

    scan_id = Path(scan_output_dir).name
    return {
        "repo_name": report_data.get("repo_name") or repo_name,
        "owner": owner,
        "scan_id": scan_id,
        "repo_path": str(repo_path),
        "scan_output_dir": str(scan_output_dir),
        "total_findings": report_data.get("total_findings", len(findings)),
        "severity_counts": severity_counts,
        "findings": findings,
        "command_output": command_output.strip(),
        "report_urls": {
            "view_json": f"/repo-report/{Path(owner).name}/{Path(repo_name).name}/{scan_id}.json",
            "download_json": f"/repo-report/{Path(owner).name}/{Path(repo_name).name}/{scan_id}.json?download=1",
            "view_pdf": f"/repo-report/{Path(owner).name}/{Path(repo_name).name}/{scan_id}.pdf",
            "download_pdf": f"/repo-report/{Path(owner).name}/{Path(repo_name).name}/{scan_id}.pdf?download=1",
        },
    }


def sanitize_command_error(exc, token):
    stderr = (exc.stderr or "").replace(token, "[redacted]").strip()
    stdout = (exc.stdout or "").strip()
    return stderr or stdout or "Scan failed."


def update_bulk_scan_job(job_id, **changes):
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return None
        job.update(changes)
        return dict(job)


def serialize_bulk_scan_job(job):
    return {
        key: value
        for key, value in job.items()
        if key not in {"current_process", "skip_requests"}
    }


def append_bulk_scan_log(job_id, message):
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return
        logs = job.setdefault("logs", [])
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        logs.append(f"[{timestamp}] {message}")
        job["updated_at"] = datetime.utcnow().isoformat() + "Z"


def is_repo_skip_requested(job_id, repo_key):
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return False
        skip_requests = job.get("skip_requests") or set()
        return repo_key in skip_requests


def update_bulk_pending_repositories(job_id, pending_repositories):
    update_bulk_scan_job(job_id, pending_repositories=list(pending_repositories))


def terminate_process_tree(process):
    if not process:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            process.kill()
    except OSError:
        pass


def build_repo_pdf_lines(scan_result):
    severity_counts = scan_result.get("severity_counts") or {}
    lines = [
        f"GVD Repository Report - {scan_result.get('owner', '')}/{scan_result.get('repo_name', '')}",
        "",
        f"Local path: {scan_result.get('repo_path', '')}",
        f"Findings: {scan_result.get('total_findings', 0)}",
        f"Critical: {severity_counts.get('CRITICAL', 0)}",
        f"High: {severity_counts.get('HIGH', 0)}",
        f"Medium: {severity_counts.get('MEDIUM', 0)}",
        f"Low: {severity_counts.get('LOW', 0)}",
        "",
        "Findings detail",
        "",
    ]

    findings = scan_result.get("findings", [])
    if not findings:
        lines.append("No vulnerabilities found.")
        return lines

    for finding in findings:
        lines.extend(
            [
                f"- Severity: {finding.get('severity', 'Unknown')}",
                f"  Type: {finding.get('secret_type', 'Unknown')}",
                f"  File: {finding.get('file_path', 'Unknown file')}",
                f"  Commit: {finding.get('commit_hash', 'N/A')}",
                f"  Fix: {finding.get('fix_recommendation', 'None')}",
                "",
            ]
        )
    return lines


def execute_scan_command(repo_path, scan_output_dir, job_id=None, repo_key=None):
    # Build command based on whether CLI_EXE is a Python script or executable
    if CLI_EXE.suffix == '.py':
        command = [
            "python",
            str(CLI_EXE),
            "scan",
            "--path",
            str(repo_path),
            "--output",
        str(scan_output_dir),
            "--format",
            "json",
        ]
    else:
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

    process = subprocess.Popen(
        command,
        cwd=BASE_DIR.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=WINDOWS_CREATION_FLAGS,
    )
    if job_id and repo_key:
        update_bulk_scan_job(
            job_id,
            current_repo_key=repo_key,
            current_process=process,
        )

    try:
        stdout, stderr = process.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    finally:
        if job_id and repo_key:
            with BULK_SCAN_JOBS_LOCK:
                job = BULK_SCAN_JOBS.get(job_id)
                if job and job.get("current_repo_key") == repo_key:
                    job["current_repo_key"] = None
                    job["current_process"] = None

    if process.returncode != 0:
        if job_id and repo_key and is_repo_skip_requested(job_id, repo_key):
            owner, repo_name = repo_key.split("/", 1)
            raise RepoSkippedError(owner, repo_name)
        raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)

    return (stdout or "") + ("\n" + stderr if stderr else "")


def run_repo_scan(repo, token, job_id=None):
    owner = ((repo.get("owner") or {}).get("login") or "").strip()
    repo_name = (repo.get("name") or "").strip()
    if not owner or not repo_name:
        raise ValueError("Invalid repository data.")

    if not CLI_EXE.exists():
        raise FileNotFoundError(f"Scanner executable not found at {CLI_EXE}.")

    repo_key = build_repo_key(owner, repo_name)
    try:
        repo_path = ensure_repo_cloned(
            repo,
            token,
            process_callback=(
                (lambda process: update_bulk_scan_job(job_id, current_repo_key=repo_key, current_process=process))
                if job_id else None
            ),
        )
    except subprocess.CalledProcessError:
        if job_id and is_repo_skip_requested(job_id, repo_key):
            raise RepoSkippedError(owner, repo_name)
        raise
    finally:
        if job_id:
            with BULK_SCAN_JOBS_LOCK:
                job = BULK_SCAN_JOBS.get(job_id)
                if job and job.get("current_repo_key") == repo_key:
                    job["current_process"] = None

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    scan_output_dir = SCAN_REPORTS_DIR / Path(owner).name / Path(repo_name).name / timestamp
    scan_output_dir.mkdir(parents=True, exist_ok=True)
    command_output = execute_scan_command(repo_path, scan_output_dir, job_id=job_id, repo_key=repo_key)

    report_path = scan_output_dir / "report.json"
    if not report_path.exists():
        raise FileNotFoundError("Scan completed but no report was generated.")

    with open(report_path, encoding="utf-8") as report_file:
        report_data = json.load(report_file)

    scan_result = build_scan_result(
        report_data,
        owner,
        repo_name,
        repo_path,
        scan_output_dir,
        command_output,
    )
    
    # Use GVD executable to generate PDF (executable already creates all report formats)
    pdf_path = scan_output_dir / "report.pdf"
    if not pdf_path.exists():
        # Fallback to basic PDF if executable didn't generate it
        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(build_pdf_bytes(build_repo_pdf_lines(scan_result)))
    
    return scan_result


def build_aggregate_summary(scan_results, failures, visibility="both"):
    totals = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    total_findings = 0
    for result in scan_results:
        total_findings += result.get("total_findings", 0)
        for severity, count in (result.get("severity_counts") or {}).items():
            if severity in totals:
                totals[severity] += count

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "visibility": visibility,
        "total_repositories": len(scan_results) + len(failures),
        "scanned_repositories": len(scan_results),
        "failed_repositories": len(failures),
        "total_findings": total_findings,
        "severity_counts": totals,
        "repositories": scan_results,
        "failures": failures,
    }


def pdf_escape(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_bytes(lines):
    wrapped_lines = []
    for line in lines:
        line = line or ""
        wrapped_lines.extend(wrap(line, width=95) or [""])

    lines_per_page = 44
    pages = [
        wrapped_lines[index:index + lines_per_page]
        for index in range(0, len(wrapped_lines), lines_per_page)
    ] or [["GVD report"]]

    objects = []
    kids = []
    font_ref = 3
    next_object_id = 4

    for page_lines in pages:
        page_id = next_object_id
        content_id = next_object_id + 1
        kids.append(f"{page_id} 0 R")

        text_commands = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
        for line in page_lines:
            text_commands.append(f"({pdf_escape(line)}) Tj")
            text_commands.append("T*")
        text_commands.append("ET")
        content_stream = "\n".join(text_commands).encode("latin-1", errors="replace")

        objects.append(
            (
                page_id,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_ref} 0 R >> >> /Contents {content_id} 0 R >>".encode("latin-1")
            )
        )
        objects.append(
            (
                content_id,
                b"<< /Length " + str(len(content_stream)).encode("ascii") + b" >>\nstream\n" + content_stream + b"\nendstream"
            )
        )
        next_object_id += 2

    pages_object = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("latin-1")
    objects = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, pages_object),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    ] + objects

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, payload in objects:
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_position = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_bulk_pdf_lines(report):
    severity_counts = report.get("severity_counts") or {}
    lines = [
        "GVD Bulk Scan Report",
        "",
        f"Generated at: {report.get('generated_at', '')}",
        f"Repositories scanned: {report.get('scanned_repositories', 0)}",
        f"Repositories failed: {report.get('failed_repositories', 0)}",
        f"Total findings: {report.get('total_findings', 0)}",
        f"Critical: {severity_counts.get('CRITICAL', 0)}",
        f"High: {severity_counts.get('HIGH', 0)}",
        f"Medium: {severity_counts.get('MEDIUM', 0)}",
        f"Low: {severity_counts.get('LOW', 0)}",
        "",
        "Repository results",
        "",
    ]

    for repo in report.get("repositories", []):
        repo_counts = repo.get("severity_counts") or {}
        lines.extend(
            [
                f"- {repo.get('owner', '')}/{repo.get('repo_name', '')}",
                f"  Findings: {repo.get('total_findings', 0)}",
                f"  Critical: {repo_counts.get('CRITICAL', 0)} | High: {repo_counts.get('HIGH', 0)} | Medium: {repo_counts.get('MEDIUM', 0)} | Low: {repo_counts.get('LOW', 0)}",
                f"  Local path: {repo.get('repo_path', '')}",
            ]
        )
        findings = repo.get("findings", [])
        if findings:
            lines.append("  Findings detail:")
            for finding in findings:
                lines.append(
                    f"    {finding.get('severity', 'Unknown')} | {finding.get('secret_type', 'Unknown')} | "
                    f"{finding.get('file_path', 'Unknown file')} | Fix: {finding.get('fix_recommendation', 'None')}"
                )
        lines.append("")

    if report.get("failures"):
        lines.extend(["Failed repositories", ""])
        for failure in report["failures"]:
            lines.append(f"- {failure.get('owner', '')}/{failure.get('repo_name', '')}: {failure.get('error', 'Unknown error')}")

    return lines


def save_bulk_report(report):
    report_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    output_dir = SCAN_REPORTS_DIR / "bulk" / report_id
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "bulk-report.json"
    pdf_path = output_dir / "bulk-report.pdf"

    with open(json_path, "w", encoding="utf-8") as json_file:
        json.dump(report, json_file, indent=2)

    # Use GVD executable PDF (executable already creates all report formats)
    if not pdf_path.exists():
        # Fallback to basic PDF if executable didn't generate it
        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(build_pdf_bytes(build_bulk_pdf_lines(report)))

    report["report_id"] = report_id
    report["download_urls"] = {
        "json": f"/download-report/{report_id}.json?download=1",
        "pdf": f"/download-report/{report_id}.pdf?download=1",
    }
    report["view_urls"] = {
        "json": f"/download-report/{report_id}.json",
        "pdf": f"/download-report/{report_id}.pdf",
    }
    return report


def run_bulk_scan_job(job_id, repos, token, visibility):
    try:
        append_bulk_scan_log(job_id, f"Starting bulk scan for {len(repos)} repositories.")
        successes = []
        failures = []
        skipped = []
        pending_repositories = [build_repo_key(((repo.get("owner") or {}).get("login") or "").strip(), (repo.get("name") or "").strip()) for repo in repos]
        update_bulk_pending_repositories(job_id, pending_repositories)

        for index, repo in enumerate(repos, start=1):
            owner = ((repo.get("owner") or {}).get("login") or "").strip()
            repo_name = (repo.get("name") or "").strip()
            label = f"{owner}/{repo_name}"
            repo_key = build_repo_key(owner, repo_name)
            pending_repositories = [item for item in pending_repositories if item != repo_key]
            update_bulk_pending_repositories(job_id, pending_repositories)

            append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Preparing {label}.")
            try:
                if is_repo_skip_requested(job_id, repo_key):
                    skipped.append({"owner": owner, "repo_name": repo_name, "error": "Skipped by user."})
                    append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Skipped {label} before scan start.")
                    update_bulk_scan_job(
                        job_id,
                        repositories=list(successes),
                        failures=list(failures),
                        skipped_repositories=list(skipped),
                        scanned_repositories=len(successes),
                        failed_repositories=len(failures),
                    )
                    continue

                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Cloning or reusing local copy for {label}.")
                update_bulk_scan_job(job_id, current_repo=label, current_repo_key=repo_key)
                result = run_repo_scan(repo, token, job_id=job_id)
                successes.append(result)
                append_bulk_scan_log(
                    job_id,
                    f"[{index}/{len(repos)}] Completed {label} with {result.get('total_findings', 0)} finding(s).",
                )
                append_bulk_scan_log(
                    job_id,
                    f"[{index}/{len(repos)}] Reports ready for {label}: JSON and PDF.",
                )
                update_bulk_scan_job(
                    job_id,
                    repositories=list(successes),
                    failures=list(failures),
                    skipped_repositories=list(skipped),
                    current_repo=None,
                    scanned_repositories=len(successes),
                    failed_repositories=len(failures),
                )
            except RepoSkippedError:
                skipped.append({"owner": owner, "repo_name": repo_name, "error": "Skipped by user."})
                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Skipped {label} during scan.")
                update_bulk_scan_job(
                    job_id,
                    repositories=list(successes),
                    failures=list(failures),
                    skipped_repositories=list(skipped),
                    current_repo=None,
                    scanned_repositories=len(successes),
                    failed_repositories=len(failures),
                )
            except subprocess.CalledProcessError as exc:
                error = sanitize_command_error(exc, token)
                failures.append({"owner": owner, "repo_name": repo_name, "error": error})
                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Failed {label}: {error}")
                update_bulk_scan_job(
                    job_id,
                    repositories=list(successes),
                    failures=list(failures),
                    skipped_repositories=list(skipped),
                    current_repo=None,
                    scanned_repositories=len(successes),
                    failed_repositories=len(failures),
                )
            except subprocess.TimeoutExpired:
                failures.append({"owner": owner, "repo_name": repo_name, "error": "Scanner timed out."})
                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Failed {label}: scanner timed out.")
                update_bulk_scan_job(
                    job_id,
                    repositories=list(successes),
                    failures=list(failures),
                    skipped_repositories=list(skipped),
                    current_repo=None,
                    scanned_repositories=len(successes),
                    failed_repositories=len(failures),
                )
            except (FileNotFoundError, ValueError) as exc:
                failures.append({"owner": owner, "repo_name": repo_name, "error": str(exc)})
                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] Failed {label}: {exc}")
                update_bulk_scan_job(
                    job_id,
                    repositories=list(successes),
                    failures=list(failures),
                    skipped_repositories=list(skipped),
                    current_repo=None,
                    scanned_repositories=len(successes),
                    failed_repositories=len(failures),
                )
            finally:
                update_bulk_scan_job(job_id, current_repo=None, current_repo_key=None)

        report = build_aggregate_summary(successes, failures, visibility)
        report["skipped_repositories"] = skipped
        report = save_bulk_report(report)
        append_bulk_scan_log(
            job_id,
            f"Bulk scan finished. {report.get('scanned_repositories', 0)} succeeded, {report.get('failed_repositories', 0)} failed, {len(skipped)} skipped.",
        )
        update_bulk_scan_job(
            job_id,
            status="completed",
            report=report,
            repositories=list(successes),
            failures=list(failures),
            skipped_repositories=list(skipped),
            pending_repositories=[],
            scanned_repositories=report.get("scanned_repositories", 0),
            failed_repositories=report.get("failed_repositories", 0),
            updated_at=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as exc:
        append_bulk_scan_log(job_id, f"Bulk scan crashed: {exc}")
        update_bulk_scan_job(
            job_id,
            status="failed",
            error=str(exc),
            pending_repositories=[],
            updated_at=datetime.utcnow().isoformat() + "Z",
        )


@app.route("/scan", methods=["POST"])
def scan():
    token = session.get("access_token")
    if not token:
        app.logger.warning("Scan attempt without access token")
        return jsonify({"error": "Unauthorized"}), 401

    # Validate request data
    try:
        payload = request.get_json(silent=True) or request.form
        if not payload:
            return jsonify({"error": "Invalid request format"}), 400
            
        repo_url = (payload.get("repo_url") or "").strip()
        owner = (payload.get("owner") or "").strip()
        repo_name = (payload.get("repo_name") or "").strip()

        # Validate required fields
        if not repo_url or not owner or not repo_name:
            return jsonify({
                "error": "Missing repository data.",
                "details": "repo_url, owner, and repo_name are required"
            }), 400

        # Sanitize inputs to prevent path traversal
        owner = Path(owner).name
        repo_name = Path(repo_name).name
        
        if len(owner) > 100 or len(repo_name) > 100:
            return jsonify({"error": "Invalid repository name length"}), 400

    except Exception as e:
        app.logger.error(f"Request validation failed: {e}")
        return jsonify({"error": "Invalid request format"}), 400

    # Verify repository exists and user has access
    try:
        repos = get_repos(token)
        if not repos:
            return jsonify({"error": "No repositories found"}), 404
            
        repo = next(
            (
                item for item in repos
                if item.get("clone_url") == repo_url
                and (item.get("owner") or {}).get("login") == owner
                and item.get("name") == repo_name
            ),
            None,
        )
        if not repo:
            app.logger.warning(f"Repository not found: {owner}/{repo_name}")
            return jsonify({"error": "Repository not found."}), 404

    except Exception as e:
        app.logger.error(f"Failed to verify repository: {e}")
        return jsonify({"error": "Failed to verify repository"}), 500

    # Run scan with comprehensive error handling
    try:
        result = run_repo_scan(repo, token)
        
        # Validate scan result
        if not result or not isinstance(result, dict):
            return jsonify({"error": "Invalid scan result"}), 500
            
        # Ensure report URLs are properly formatted
        if "report_urls" in result:
            for key, url in result["report_urls"].items():
                if not url or not url.startswith("/"):
                    result["report_urls"][key] = None
                    
        return jsonify(result)
        
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").replace(token, "[redacted]").strip()
        stdout = (exc.stdout or "").replace(token, "[redacted]").strip()
        app.logger.error(f"Scan failed: {exc}")
        return jsonify({
            "error": "Scan failed.", 
            "details": stderr or stdout or "Unknown scan error"
        }), 500
    except FileNotFoundError as exc:
        app.logger.error(f"Scanner not found: {exc}")
        return jsonify({"error": "Scanner not available"}), 500
    except subprocess.TimeoutExpired:
        app.logger.error("Scan timed out")
        return jsonify({"error": "Scanner timed out."}), 504
    except ValueError as exc:
        app.logger.error(f"Invalid scan parameters: {exc}")
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.error(f"Unexpected scan error: {exc}")
        return jsonify({"error": "Unexpected scan error"}), 500


@app.route("/scan-all", methods=["POST"])
def scan_all():
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or request.form
    visibility = (payload.get("visibility") or "both").strip().lower()
    if visibility not in {"public", "private", "both"}:
        return jsonify({"error": "Invalid visibility filter."}), 400

    repos = get_repos(token)
    if visibility != "both":
        repos = [repo for repo in repos if repo.get("visibility") == visibility]
    if not repos:
        return jsonify({"error": "No repositories available to scan."}), 400

    job_id = uuid.uuid4().hex
    with BULK_SCAN_JOBS_LOCK:
        BULK_SCAN_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "logs": [],
            "report": None,
            "repositories": [],
            "failures": [],
            "skipped_repositories": [],
            "visibility": visibility,
            "total_repositories": len(repos),
            "scanned_repositories": 0,
            "failed_repositories": 0,
            "pending_repositories": [],
            "current_repo": None,
            "current_repo_key": None,
            "current_process": None,
            "skip_requests": set(),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    worker = threading.Thread(
        target=run_bulk_scan_job,
        args=(job_id, repos, token, visibility),
        daemon=True,
    )
    worker.start()

    append_bulk_scan_log(job_id, "Bulk scan job created.")
    return jsonify(
        {
            "job_id": job_id,
            "status": "running",
            "visibility": visibility,
            "total_repositories": len(repos),
        }
    )


@app.route("/scan-all/<job_id>")
def scan_all_status(job_id):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Bulk scan job not found."}), 404
        response = serialize_bulk_scan_job(job)

    return jsonify(response)


@app.route("/scan-all/<job_id>/skip", methods=["POST"])
def scan_all_skip(job_id):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or request.form
    owner = (payload.get("owner") or "").strip()
    repo_name = (payload.get("repo_name") or "").strip()
    if not owner or not repo_name:
        return jsonify({"error": "Missing repository data."}), 400

    repo_key = build_repo_key(owner, repo_name)
    process_to_kill = None
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Bulk scan job not found."}), 404
        if job.get("status") != "running":
            return jsonify({"error": "Bulk scan job is not running."}), 400
        skip_requests = job.setdefault("skip_requests", set())
        skip_requests.add(repo_key)
        if job.get("current_repo_key") == repo_key:
            process_to_kill = job.get("current_process")

    append_bulk_scan_log(job_id, f"Skip requested for {repo_key}.")
    if process_to_kill:
        terminate_process_tree(process_to_kill)

    return jsonify({"status": "skip_requested", "repo_key": repo_key})


@app.route("/download-report/<report_id>.<file_format>")
def download_bulk_report(report_id, file_format):
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))

    report_dir = SCAN_REPORTS_DIR / "bulk" / Path(report_id).name
    files = {
        "json": report_dir / "bulk-report.json",
        "pdf": report_dir / "bulk-report.pdf",
    }
    target = files.get(file_format)
    if not target or not target.exists():
        abort(404)

    as_attachment = request.args.get("download") == "1"
    return send_file(target, as_attachment=as_attachment, download_name=target.name)


@app.route("/repo-report/<owner>/<repo_name>/<scan_id>.<file_format>")
def repo_report(owner, repo_name, scan_id, file_format):
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))

    # Validate file format
    if file_format not in ["json", "pdf"]:
        abort(400, description="Invalid file format")
    
    # Sanitize path components to prevent directory traversal
    owner = Path(owner).name
    repo_name = Path(repo_name).name
    scan_id = Path(scan_id).name
    
    report_dir = SCAN_REPORTS_DIR / owner / repo_name / scan_id
    files = {
        "json": report_dir / "report.json",
        "pdf": report_dir / "report.pdf",
    }
    target = files.get(file_format)
    
    if not target or not target.exists():
        # Log the missing file for debugging
        app.logger.error(f"Report file not found: {target}")
        abort(404, description=f"Report file not found: {file_format}")
    
    # Verify file size to prevent serving empty files
    if target.stat().st_size == 0:
        app.logger.error(f"Report file is empty: {target}")
        abort(404, description="Report file is empty")
    
    as_attachment = request.args.get("download") == "1"
    
    # Set appropriate MIME type and headers
    if file_format == "pdf":
        mimetype = "application/pdf"
        download_name = f"{owner}-{repo_name}-scan-{scan_id}.pdf"
        # Add headers to ensure proper PDF handling
        response = send_file(
            target, 
            as_attachment=as_attachment, 
            download_name=download_name,
            mimetype=mimetype,
            conditional=True
        )
        response.headers['Content-Type'] = mimetype
        response.headers['Content-Disposition'] = f'{"attachment" if as_attachment else "inline"}; filename="{download_name}"'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    else:  # JSON
        mimetype = "application/json"
        download_name = f"{owner}-{repo_name}-scan-{scan_id}.json"
        return send_file(
            target, 
            as_attachment=as_attachment, 
            download_name=download_name,
            mimetype=mimetype
        )


@app.route("/repo-details/<owner>/<repo_name>")
def repo_details(owner, repo_name):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    owner = (owner or "").strip()
    repo_name = (repo_name or "").strip()
    if not owner or not repo_name:
        return jsonify({"error": "Invalid repository reference"}), 400
    
    try:
        result = get_repo_details(token, owner, repo_name)
        if not result:
            return jsonify({"error": "Repository not found"}), 404
        return jsonify(result)
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API error for {owner}/{repo_name}: {e}")
        return jsonify({"error": "GitHub API error", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error getting repo details: {e}")
        return jsonify({"error": "Failed to get repository details", "details": str(e)}), 500


@app.route("/search")
def search():
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    query = request.args.get("q", "").strip()
    visibility = request.args.get("visibility", "all").strip().lower()
    if visibility not in {"all", "public", "private"}:
        visibility = "all"
    
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(5, int(request.args.get("per_page", 20))))
    except (ValueError, TypeError):
        page = 1
        per_page = 20
    
    try:
        result = search_repos(token, query, visibility, page, per_page)
        return jsonify(result)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "GitHub API error", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "Search failed", "details": str(e)}), 500


@app.route("/scan-history")
def scan_history():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))
    
    # Get all scan reports from the scan_reports directory
    scan_reports = []
    try:
        if SCAN_REPORTS_DIR.exists():
            for owner_dir in SCAN_REPORTS_DIR.iterdir():
                if not owner_dir.is_dir():
                    continue
                for repo_dir in owner_dir.iterdir():
                    if not repo_dir.is_dir():
                        continue
                    for scan_dir in repo_dir.iterdir():
                        if not scan_dir.is_dir():
                            continue
                        report_json = scan_dir / "report.json"
                        if report_json.exists():
                            try:
                                with open(report_json, encoding="utf-8") as f:
                                    report_data = json.load(f)
                                    scan_reports.append({
                                        "owner": owner_dir.name,
                                        "repo_name": repo_dir.name,
                                        "scan_id": scan_dir.name,
                                        "scan_date": report_data.get("scan_date"),
                                        "total_findings": report_data.get("total_findings", 0),
                                        "severity_counts": report_data.get("severity_counts", {}),
                                        "report_path": str(report_json.relative_to(BASE_DIR))
                                    })
                            except (json.JSONDecodeError, IOError, ValueError) as e:
                                logger.warning(f"Failed to load report {report_json}: {e}")
                                continue
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to read scan reports directory: {e}")
        flash("Failed to load scan history. Please try again.", "error")
        return render_template("scan_history.html", scan_reports=[])
    except Exception as e:
        logger.error(f"Unexpected error in scan_history: {e}")
        flash("An error occurred while loading scan history.", "error")
        return render_template("scan_history.html", scan_reports=[])
    
    # Sort by scan date (newest first)
    scan_reports.sort(key=lambda x: x.get("scan_date", ""), reverse=True)
    
    return render_template("scan_history.html", scan_reports=scan_reports)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# Global error handlers for graceful error responses
@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Bad request", "details": str(error)}), 400
    return render_template("error.html", status_code=400, message="Bad request"), 400


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Forbidden", "details": str(error)}), 403
    return render_template("error.html", status_code=403, message="Forbidden"), 403


@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Not found", "details": str(error)}), 404
    return render_template("error.html", status_code=404, message="Page not found"), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Handle 500 Internal Server Error."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error", "details": "Please try again later"}), 500
    return render_template("error.html", status_code=500, message="Internal server error"), 500


if __name__ == "__main__":
    # Only use debug mode in development
    debug_mode = os.environ.get("FLASK_ENV", "development") == "development"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
