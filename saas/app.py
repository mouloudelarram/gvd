import os
import json
import logging
import threading
import uuid
import subprocess
import requests
import platform
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import wrap

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from markupsafe import escape

from auth import get_github_auth_url, get_github_token, get_github_user, validate_oauth_state
from clone import clone_repos, ensure_repo_cloned
from github import get_repo_details, get_repos, search_repos
from config import generate_csrf_token, setup_error_handlers, require_login, validate_csrf
from network_config import configure_github_network
from session_config import configure_server_side_sessions, rotate_session
from api_common import api_error, validate_scan_request, build_openapi_spec
import jobs_repo
import observability


def load_env():
    """Load environment variables from .env file (if it exists).
    
    In Docker, the env_file directive in docker-compose.yml passes
    environment variables directly, so the .env file may not exist.
    This function silently skips loading if the file doesn't exist.
    """
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        # Silently skip - env vars may be loaded from docker-compose env_file
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
configure_github_network()

# Validate required environment variables
required_env_vars = ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "FLASK_SECRET_KEY"]
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}. Please check your .env file.")

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Configure logging: structured JSON in production, human-readable in dev,
# with automatic credential redaction (F-16).
observability.configure_logging()


class _CorrelationIdFilter(logging.Filter):
    """Attach the current request's correlation id to every log record."""

    def filter(self, record):  # noqa: A003 - logging API name
        from flask import g, has_request_context

        if has_request_context():
            cid = getattr(g, "correlation_id", None)
            if cid:
                record.correlation_id = cid
        return True


logging.getLogger().addFilter(_CorrelationIdFilter())
logger = logging.getLogger(__name__)

# Security configuration for session cookies
# In development (localhost), use HTTP; in production, require HTTPS
is_production = os.environ.get("FLASK_ENV") == "production" or os.environ.get("ENVIRONMENT") == "production"
is_localhost = os.environ.get("LOCALHOST_DEV", "false").lower() == "true"

app.config.update(
    SESSION_COOKIE_SECURE=is_production and not is_localhost,  # Only HTTPS in production
    SESSION_COOKIE_HTTPONLY=True,  # No JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',  # CSRF protection
    SESSION_COOKIE_NAME='gvd_session',
    SESSION_COOKIE_DOMAIN=None,  # Allow localhost
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max request size
)

# Server-side sessions: the GitHub token is stored on the server, never in a
# cookie (F-03). The browser only holds an opaque, signed session id.
configure_server_side_sessions(app)

# Setup error handlers
setup_error_handlers(app)

# Register CSRF token generation for all templates
@app.before_request
def before_request():
    """Assign a correlation id, ensure a CSRF token, then enforce CSRF."""
    from flask import g
    import time as _time
    g.correlation_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    g.request_start = _time.perf_counter()
    generate_csrf_token()
    validate_csrf()


@app.after_request
def add_correlation_header(response):
    """Echo the correlation id and record request metrics (F-16)."""
    from flask import g
    import time as _time
    cid = getattr(g, "correlation_id", None)
    if cid:
        response.headers["X-Request-ID"] = cid
    start = getattr(g, "request_start", None)
    if start is not None:
        duration = _time.perf_counter() - start
        # Use the matched route rule (low cardinality) instead of the raw path.
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        observability.observe_http_request(
            request.method, endpoint, response.status_code, duration
        )
    return response


@app.context_processor
def inject_csrf_token():
    """Make the CSRF token available to every template (e.g. base.html meta tag)."""
    return {"csrf_token": session.get("_csrf_token", "")}

BASE_DIR = Path(__file__).resolve().parent

# ============================================================================
# SESSION-BASED RESULT STORAGE & NOTIFICATIONS (Production-Grade)
# ============================================================================

# Session-based temporary result storage
SESSION_SCAN_RESULTS = {}  # {session_id: {bulk_report_id: report}}
SESSION_NOTIFICATIONS = {}  # {session_id: [notifications]}
SESSION_DATA_LOCK = threading.Lock()


def get_session_id():
    """Get or create unique session identifier"""
    if 'session_id' not in session:
        session['session_id'] = uuid.uuid4().hex
    return session['session_id']


def cleanup_old_session_data(session_id):
    """Clean up old session data on logout"""
    with SESSION_DATA_LOCK:
        SESSION_SCAN_RESULTS.pop(session_id, None)
        SESSION_NOTIFICATIONS.pop(session_id, None)


def add_session_notification(notification_type, title, message, data=None):
    """Add notification to current session"""
    session_id = get_session_id()
    with SESSION_DATA_LOCK:
        if session_id not in SESSION_NOTIFICATIONS:
            SESSION_NOTIFICATIONS[session_id] = []
        
        notification = {
            "id": uuid.uuid4().hex,
            "type": notification_type,
            "title": title,
            "message": message,
            "data": data or {},
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
        }
        
        SESSION_NOTIFICATIONS[session_id].append(notification)
    
    return notification

# ============================================================================
# STATISTICS TRACKING (durable, per-user) — see db.py / stats_repo.py (F-11)
# ============================================================================

from stats_repo import get_today_stats, record_scan_event


def get_statistics(user_login=""):
    """Return today's aggregated statistics for a single user (durable store)."""
    return get_today_stats(user_login)


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
        now = datetime.now(timezone.utc)
        if date_obj.tzinfo:
            date_obj = date_obj.astimezone(timezone.utc)
        else:
            # If naive, assume UTC
            date_obj = date_obj.replace(tzinfo=timezone.utc)
        
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
# Scanner execution mode: 'inprocess' (default, portable, container-safe — F-19)
# runs the scan in this process via scanner_lib; 'subprocess' shells out to the CLI.
SCANNER_MODE = os.environ.get("SCANNER_MODE", "inprocess").strip().lower()
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


# ============================================================================
# PER-RESOURCE AUTHORIZATION (anti-IDOR) — see docs F-06
# ----------------------------------------------------------------------------
# Reports may contain secrets discovered in a repository, so a report must only
# be readable by the user who initiated the scan. Until the durable persistence
# layer lands, ownership is recorded as a small restart-safe marker written next
# to the report artifacts, and enforced on every download.
# ============================================================================

def current_user_login():
    """Return the authenticated user's GitHub login, or '' if unknown."""
    user = session.get("user") or {}
    return (user.get("login") or "").strip()


def write_scan_owner(scan_output_dir, scanned_by):
    """Persist which user initiated a scan, next to its report artifacts."""
    try:
        meta_path = Path(scan_output_dir) / "meta.json"
        with open(meta_path, "w", encoding="utf-8") as meta_file:
            json.dump({"scanned_by": (scanned_by or "").strip()}, meta_file)
    except OSError as exc:
        logger.warning(f"Could not write scan ownership marker: {exc}")


def read_scan_owner(scan_dir):
    """Return the login that initiated the scan in ``scan_dir`` (or '')."""
    meta_path = Path(scan_dir) / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        with open(meta_path, encoding="utf-8") as meta_file:
            return (json.load(meta_file).get("scanned_by") or "").strip()
    except (OSError, ValueError):
        return ""


def is_authorized_for_scan(scan_dir, login):
    """Owner-only access: the marker must exist and match the given login."""
    owner = read_scan_owner(scan_dir)
    return bool(owner) and owner == (login or "").strip()


def is_authorized_for_bulk_report(report_json_path, login):
    """Owner-only access for bulk reports (owner recorded inside the JSON)."""
    path = Path(report_json_path)
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as report_file:
            owner = (json.load(report_file).get("owner_login") or "").strip()
    except (OSError, ValueError):
        return False
    return bool(owner) and owner == (login or "").strip()


def enforce_job_owner(job_id):
    """Abort 403 if a durable job exists and is owned by another user (F-06).

    Best-effort: if the durable record is missing (e.g. DB write failed), fall
    back to the existing behaviour rather than hard-blocking control of a live job.
    """
    try:
        job = jobs_repo.get_job(Path(job_id).name)
    except Exception:  # pragma: no cover - defensive
        return
    if job and job.get("owner_login") != current_user_login():
        app.logger.warning("Denied cross-user job control for %s", job_id)
        abort(403)


@app.route("/health")
def health():
    """Health check endpoint for Docker/Kubernetes healthchecks.
    
    Returns 200 OK immediately without requiring authentication.
    """
    return jsonify({"status": "healthy"}), 200


@app.route("/livez")
def livez():
    """Liveness probe: the process is up and serving (no dependencies checked)."""
    return jsonify({"status": "alive"}), 200


@app.route("/readyz")
def readyz():
    """Readiness probe: returns 503 unless the database is reachable."""
    from db import check_db_ready

    if check_db_ready():
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "not_ready", "reason": "database_unavailable"}), 503


@app.route("/metrics")
def metrics():
    """Prometheus metrics exposition (F-16).

    Reflects the queue depth on scrape so the gauge stays current, then renders
    the shared registry in the Prometheus text format.
    """
    try:
        observability.set_queue_depth(jobs_repo.count_queued_jobs())
    except Exception:  # pragma: no cover - metrics must never break scraping
        pass
    from flask import Response

    return Response(observability.render_metrics(), mimetype="text/plain; version=0.0.4")


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
    """
    Handle GitHub OAuth callback.
    Validates CSRF state, exchanges code for token, fetches user profile.
    """
    # Handle the case where GitHub redirects back with an error (e.g. the user
    # declined the authorization on the consent screen). GitHub sends
    # ?error=access_denied&error_description=... and no code, so surface a
    # friendly, journey-specific message instead of a generic "missing code".
    oauth_error = request.args.get("error")
    if oauth_error:
        app.logger.info(f"OAuth authorization not granted: {oauth_error}")
        if oauth_error == "access_denied":
            message = "Authorization Cancelled"
            detail = (
                "You did not authorize GVD to access your GitHub account. "
                "Sign in again and approve the requested permissions to continue."
            )
        else:
            message = "Authentication Error"
            detail = (
                "GitHub could not complete the sign-in. Please try again. "
                "If the problem persists, contact your administrator."
            )
        return render_template(
            "error.html", status=400, message=message, detail=detail
        ), 400

    try:
        # Exchange OAuth code for access token (validates state internally)
        token = get_github_token()
        
        # Fetch user profile
        user = get_github_user(token)
        
        # Rotate the session after authentication (mitigates session fixation),
        # then store credentials server-side only (F-03).
        rotate_session(session)
        session["access_token"] = token
        session["user"] = user
        session.permanent = True
        
        app.logger.info(f"User {user['login']} successfully authenticated")
        return redirect(url_for("dashboard"))
        
    except ValueError as e:
        # OAuth validation error (CSRF, invalid code, etc.)
        app.logger.warning(f"OAuth validation error: {e}")
        return render_template("error.html",
                             status=400,
                             message="Authentication Error",
                             detail=f"Authentication failed: {str(e)}"), 400
                             
    except RuntimeError as e:
        # GitHub API error (network, timeout, rate limit, etc.)
        app.logger.error(f"GitHub authentication error: {e}")
        return render_template("error.html",
                             status=503,
                             message="GitHub Service Temporarily Unavailable",
                             detail=f"Could not complete authentication: {str(e)}"), 503
                             
    except Exception as e:
        # Unexpected error - log and show generic message
        app.logger.error(f"Unexpected authentication error: {e}", exc_info=True)
        return render_template("error.html",
                             status=500,
                             message="Authentication Failed",
                             detail="An unexpected error occurred during authentication. Please try again."), 500


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
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        logs.append(f"[{timestamp}] {message}")
        job["updated_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


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
    """Terminate a process and all its children with better error handling."""
    if not process:
        return
    
    try:
        pid = process.pid
        if not pid:
            return
            
        if os.name == "nt":  # Windows
            # Use taskkill with /T (terminate tree) and /F (force)
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                logger.info(f"taskkill result: {result.returncode}, stdout: {result.stdout}, stderr: {result.stderr}")
            except Exception as e:
                logger.error(f"taskkill failed: {e}")
            
            # Try multiple times to ensure termination
            for attempt in range(3):
                try:
                    if process.poll() is None:  # Process still running
                        logger.info(f"Process still running, attempt {attempt + 1} to terminate")
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                            logger.info("Process terminated successfully")
                            return
                        except subprocess.TimeoutExpired:
                            logger.warning("Terminate timed out, trying kill")
                            process.kill()
                            try:
                                process.wait(timeout=2)
                                logger.info("Process killed successfully")
                                return
                            except:
                                logger.error("Kill also failed")
                    else:
                        logger.info("Process already terminated")
                        return
                except Exception as e:
                    logger.error(f"Error in termination attempt {attempt + 1}: {e}")
        else:  # Unix/Linux
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    except Exception as e:
        logger.error(f"Error in terminate_process_tree: {e}")


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
        # Use communicate with timeout and periodically check if scan should stop
        stdout_data = []
        stderr_data = []
        
        # Use a shorter timeout in communicate() to allow checking stop status
        scan_timeout = 300  # 5 minutes total
        chunk_timeout = 5   # Check every 5 seconds if we should stop
        elapsed = 0
        
        try:
            while elapsed < scan_timeout:
                try:
                    # Check if we should stop scanning
                    should_stop = False
                    with BULK_SCAN_JOBS_LOCK:
                        job = BULK_SCAN_JOBS.get(job_id)
                        if job and job.get("status") == "stopped":
                            should_stop = True
                    
                    if should_stop:
                        logger.info(f"Stop requested during scan, terminating process PID {process.pid}")
                        terminate_process_tree(process)
                        raise subprocess.CalledProcessError(1, "scan", output="Scan stopped by user", stderr="")
                    
                    # Try to wait for process with short timeout
                    stdout, stderr = process.communicate(timeout=chunk_timeout)
                    stdout_data.append(stdout or "")
                    stderr_data.append(stderr or "")
                    break  # Process completed
                except subprocess.TimeoutExpired:
                    elapsed += chunk_timeout
                    # Continue loop to check stop status again
                    continue
            
            # If we've exceeded the total scan timeout
            if elapsed >= scan_timeout:
                logger.warning(f"Scan exceeded timeout for {repo_key}")
                terminate_process_tree(process)
                raise subprocess.TimeoutExpired("scan", scan_timeout)
                
        except subprocess.TimeoutExpired:
            # Final attempt to check if stopped
            with BULK_SCAN_JOBS_LOCK:
                job = BULK_SCAN_JOBS.get(job_id)
                if job and job.get("status") == "stopped":
                    logger.info("Scan stopped by user during timeout")
                else:
                    logger.warning("Scan timed out")
            terminate_process_tree(process)
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
        raise subprocess.CalledProcessError(process.returncode, command, output="".join(stdout_data), stderr="".join(stderr_data))

    return ("".join(stdout_data) or "") + ("\n" + "".join(stderr_data) if "".join(stderr_data) else "")


def run_repo_scan(repo, token, job_id=None, scanned_by=None):
    owner = ((repo.get("owner") or {}).get("login") or "").strip()
    repo_name = (repo.get("name") or "").strip()
    if not owner or not repo_name:
        raise ValueError("Invalid repository data.")

    if SCANNER_MODE == "subprocess" and not CLI_EXE.exists():
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

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    scan_output_dir = SCAN_REPORTS_DIR / Path(owner).name / Path(repo_name).name / timestamp
    scan_output_dir.mkdir(parents=True, exist_ok=True)
    # Record the initiating user for per-user report authorization (F-06).
    write_scan_owner(scan_output_dir, scanned_by)
    if SCANNER_MODE == "inprocess":
        # In-process scan (portable, container-safe): writes report.json (F-19).
        import scanner_lib
        scanner_lib.scan_to_dir(repo_path, scan_output_dir, repo_name)
        command_output = ""
    else:
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
    
    # Track this scan in durable, per-user statistics (best-effort).
    try:
        record_scan_event(
            scanned_by,
            scan_result.get("severity_counts"),
            scan_result.get("total_findings"),
        )
    except Exception as exc:
        logger.warning(f"Failed to record scan statistics: {exc}")

    # Emit scan + findings metrics (F-16).
    try:
        observability.observe_scan("success")
        for severity, count in (scan_result.get("severity_counts") or {}).items():
            observability.observe_findings(str(severity).lower(), int(count or 0))
    except Exception:  # pragma: no cover - metrics must never break a scan
        pass

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
        "generated_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
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
    # Unguessable id (defense in depth alongside the owner check, F-06).
    report_id = uuid.uuid4().hex
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


def run_bulk_scan_job(job_id, repos, token, visibility, session_id=None, scanned_by=None):
    try:
        append_bulk_scan_log(job_id, f"Starting bulk scan for {len(repos)} repositories.")
        successes = []
        failures = []
        skipped = []
        pending_repositories = [build_repo_key(((repo.get("owner") or {}).get("login") or "").strip(), (repo.get("name") or "").strip()) for repo in repos]
        update_bulk_pending_repositories(job_id, pending_repositories)

        for index, repo in enumerate(repos, start=1):
            # Check if scan should be stopped (check status flag)
            should_stop = False
            with BULK_SCAN_JOBS_LOCK:
                job = BULK_SCAN_JOBS.get(job_id)
                if job and job.get("status") != "running":
                    should_stop = True
            
            if should_stop:
                append_bulk_scan_log(job_id, f"[{index}/{len(repos)}] 🛑 Scan stopped by user, skipping remaining repositories.")
                break
            
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
                result = run_repo_scan(repo, token, job_id=job_id, scanned_by=scanned_by)
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
                
                # Check if we should stop after this repo
                with BULK_SCAN_JOBS_LOCK:
                    job = BULK_SCAN_JOBS.get(job_id)
                    if job and job.get("status") != "running":
                        append_bulk_scan_log(job_id, f"🛑 Stop detected after {label}, will exit loop after this iteration.")
                        # Force break on next iteration by not continuing the loop naturally

        # Check one final time if we should exit due to stop request
        with BULK_SCAN_JOBS_LOCK:
            job = BULK_SCAN_JOBS.get(job_id)
            if job and job.get("status") != "running":
                append_bulk_scan_log(job_id, "🛑 Bulk scan stopped - all remaining repositories skipped.")

        report = build_aggregate_summary(successes, failures, visibility)
        report["skipped_repositories"] = skipped
        # Record the initiating user so only they can download the bulk report (F-06).
        report["owner_login"] = (scanned_by or "").strip()
        report = save_bulk_report(report)
        # Durable terminal state (F-01), best-effort.
        try:
            jobs_repo.update_job(
                job_id,
                status="completed",
                scanned_repositories=report.get("scanned_repositories", 0),
                failed_repositories=report.get("failed_repositories", 0),
                report_id=report.get("report_id"),
            )
        except Exception as exc:
            logger.warning(f"Could not persist completed job {job_id}: {exc}")
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
            updated_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        )
        
        # NEW: Create completion notification
        if session_id:
            high_risk = sum(1 for r in successes for f in r.get("findings", []) 
                          if f.get("severity") in ["CRITICAL", "HIGH"])
            add_session_notification(
                "scan_completed",
                "Bulk Scan Completed",
                f"{report.get('scanned_repositories', 0)} scanned, {report.get('failed_repositories', 0)} failed, {high_risk} high-risk findings",
                {
                    "job_id": job_id,
                    "scanned": report.get('scanned_repositories', 0),
                    "failed": report.get('failed_repositories', 0),
                    "total_findings": report.get('total_findings', 0),
                    "high_risk_findings": high_risk
                }
            )
    except Exception as exc:
        append_bulk_scan_log(job_id, f"Bulk scan crashed: {exc}")
        update_bulk_scan_job(
            job_id,
            status="failed",
            error=str(exc),
            pending_repositories=[],
            updated_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        )
        # Durable failure state (F-01), best-effort.
        try:
            jobs_repo.update_job(job_id, status="failed", error=str(exc)[:1000])
        except Exception as db_exc:
            logger.warning(f"Could not persist failed job {job_id}: {db_exc}")

        # NEW: Create failure notification
        if session_id:
            add_session_notification(
                "scan_failed",
                "Bulk Scan Failed",
                f"Scan encountered an error: {str(exc)[:100]}",
                {"job_id": job_id, "error": str(exc)}
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
        result = run_repo_scan(repo, token, scanned_by=current_user_login())

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


def launch_bulk_scan(repos, token, visibility, scanned_by, idempotency_key=None):
    """Create and start a durable bulk scan job.

    Shared by the legacy ``/scan-all`` route and the versioned ``/api/v1/scans``
    endpoint so the orchestration logic lives in exactly one place. Returns a
    dict describing the job (or the idempotent replay).
    """
    job_id = uuid.uuid4().hex
    session_id = get_session_id()

    # Durable job record + idempotency (F-01 / F-13). Best-effort so a DB hiccup
    # never blocks scanning, but an idempotent replay short-circuits here.
    try:
        db_job, is_new = jobs_repo.create_job(
            job_id,
            scanned_by,
            job_type="bulk",
            total_repositories=len(repos),
            visibility=visibility,
            idempotency_key=idempotency_key,
            status="running",
        )
        if not is_new:
            return {
                "job_id": db_job["id"],
                "status": db_job["status"],
                "visibility": db_job.get("visibility"),
                "total_repositories": db_job.get("total_repositories", 0),
                "idempotent": True,
            }
        job_id = db_job["id"]
    except Exception as exc:
        logger.warning(f"Could not persist scan job: {exc}")

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
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "updated_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }

    worker = threading.Thread(
        target=run_bulk_scan_job,
        args=(job_id, repos, token, visibility, session_id, scanned_by),
        daemon=True,
    )
    worker.start()

    append_bulk_scan_log(job_id, "Bulk scan job created.")
    add_session_notification(
        "scan_started",
        "Bulk Scan Starting",
        f"Preparing to scan {len(repos)} repositories...",
        {"job_id": job_id, "repo_count": len(repos)},
    )
    return {
        "job_id": job_id,
        "status": "running",
        "visibility": visibility,
        "total_repositories": len(repos),
    }


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

    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None
    result = launch_bulk_scan(repos, token, visibility, current_user_login(), idempotency_key)
    return jsonify(result)


@app.route("/scan-all/<job_id>")
def scan_all_status(job_id):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    enforce_job_owner(job_id)
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Bulk scan job not found."}), 404
        
        response = serialize_bulk_scan_job(job)
        
        # NEW: If job completed, cache result in session
        if job.get("status") == "completed" and "report" in job:
            session_id = job.get("session_id") or get_session_id()
            with SESSION_DATA_LOCK:
                if session_id not in SESSION_SCAN_RESULTS:
                    SESSION_SCAN_RESULTS[session_id] = {}
                SESSION_SCAN_RESULTS[session_id][job_id] = job.get("report")

    return jsonify(response)


@app.route("/scan-all/<job_id>/skip", methods=["POST"])
def scan_all_skip(job_id):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    enforce_job_owner(job_id)
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


@app.route("/scan-all/<job_id>/stop", methods=["POST"])
def scan_all_stop(job_id):
    """Stop a running bulk scan job and terminate any active CLI process."""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401

    enforce_job_owner(job_id)
    process_to_kill = None
    current_repo = None
    current_pid = None
    
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Bulk scan job not found."}), 404
        
        if job.get("status") != "running":
            return jsonify({"error": "Bulk scan job is not running."}), 400
        
        # Mark job as stopped
        job["status"] = "stopped"
        job["updated_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Get process to kill and current repo info
        process_to_kill = job.get("current_process")
        current_repo = job.get("current_repo") or "unknown"
        if process_to_kill and hasattr(process_to_kill, 'pid'):
            current_pid = process_to_kill.pid

    # Log the stop attempt
    append_bulk_scan_log(job_id, f"🛑 Stop signal received - Current repo: {current_repo}")
    
    # Kill the process if it exists
    if process_to_kill:
        try:
            append_bulk_scan_log(job_id, f"Terminating CLI process (PID: {current_pid})...")
            terminate_process_tree(process_to_kill)
            append_bulk_scan_log(job_id, "✓ CLI process terminated successfully")
        except Exception as e:
            append_bulk_scan_log(job_id, f"⚠ Error terminating process: {str(e)}")
    else:
        append_bulk_scan_log(job_id, "No active CLI process to terminate")
    
    append_bulk_scan_log(job_id, "⛔ Bulk scan stopped by user - remaining repositories will be skipped")

    return jsonify({"status": "stopped", "job_id": job_id, "pid_killed": current_pid})


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

    # Owner-only access: reject cross-user downloads (anti-IDOR, F-06).
    if not is_authorized_for_bulk_report(report_dir / "bulk-report.json", current_user_login()):
        app.logger.warning("Denied cross-user bulk report access for %s", Path(report_id).name)
        abort(403)

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

    # Owner-only access: reject cross-user downloads (anti-IDOR, F-06).
    if not is_authorized_for_scan(report_dir, current_user_login()):
        app.logger.warning("Denied cross-user report access for %s/%s/%s", owner, repo_name, scan_id)
        abort(403)

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
                            # Only surface scans initiated by the current user (F-06).
                            if not is_authorized_for_scan(scan_dir, current_user_login()):
                                continue
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


# ============================================================================
# NOTIFICATION API ENDPOINTS (Production-Grade)
# ============================================================================

@app.route("/api/notifications")
def get_notifications():
    """Get all notifications for current session"""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    session_id = get_session_id()
    with SESSION_DATA_LOCK:
        notifications = SESSION_NOTIFICATIONS.get(session_id, [])
        unread_count = sum(1 for n in notifications if not n.get("read"))
    
    return jsonify({
        "notifications": notifications,
        "unread_count": unread_count
    })


@app.route("/api/notifications/<notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    """Mark notification as read"""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    session_id = get_session_id()
    with SESSION_DATA_LOCK:
        notifications = SESSION_NOTIFICATIONS.get(session_id, [])
        for notif in notifications:
            if notif.get("id") == notification_id:
                notif["read"] = True
                break
    
    return jsonify({"status": "ok"})


@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    """Clear all notifications"""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    session_id = get_session_id()
    with SESSION_DATA_LOCK:
        SESSION_NOTIFICATIONS[session_id] = []
    
    return jsonify({"status": "ok"})


# ============================================================================
# REPOSITORY API ENDPOINTS (Production-Grade)
# ============================================================================

@app.route("/api/all-user-repos")
def all_user_repos():
    """Get ALL user repositories (with pagination)"""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        repos = get_repos(token)
        return jsonify(repos)
    except Exception as e:
        logger.error(f"Failed to fetch all repos: {e}")
        return jsonify({"error": "Failed to fetch repositories", "details": str(e)}), 500


@app.route("/api/session-stats")
def session_stats():
    """
    Get scan statistics for dashboard (scanned today, high-risk findings).
    Returns real-time aggregated statistics from all completed scans today.
    """
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        # Get today's statistics for the current user
        stats = get_statistics(current_user_login())

        # Add total repository count
        total_repositories = len(get_repos(token)) if token else 0
        stats["total_repositories"] = total_repositories
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        # Return defaults instead of failing
        return jsonify({
            "scanned_today": 0,
            "high_risk_findings": 0,
            "total_findings_today": 0,
            "total_repositories": 0,
            "breakdown": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        })


@app.route("/api/bulk-scan/start", methods=["POST"])
@require_login
def start_bulk_scan():
    """Start a bulk scan session."""
    from bulk_scan_service import get_bulk_scan_manager
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    
    manager = get_bulk_scan_manager()
    manager.create_session(session_id)
    
    # Get repositories to scan
    token = session.get("github_token")
    try:
        repositories = get_repos(token)
        repo_names = [f"{repo['owner']['login']}/{repo['name']}" for repo in repositories]
    except Exception as e:
        logger.error(f"Failed to get repositories: {e}")
        return jsonify({"error": "Failed to fetch repositories"}), 500
    
    # Start the scan
    manager.start_scan(session_id, repo_names)
    
    return jsonify({
        "session_id": session_id,
        "status": "started",
        "repositories_count": len(repo_names)
    })


@app.route("/api/bulk-scan/stop", methods=["POST"])
@require_login
def stop_bulk_scan():
    """Stop an ongoing bulk scan."""
    from bulk_scan_service import get_bulk_scan_manager
    
    data = request.get_json() or {}
    session_id = data.get("session_id")
    
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    
    manager = get_bulk_scan_manager()
    success = manager.stop_scan(session_id)
    
    if not success:
        return jsonify({"error": "Failed to stop scan"}), 400
    
    return jsonify({"session_id": session_id, "status": "stopped"})


@app.route("/api/bulk-scan/progress/<session_id>")
@require_login
def get_bulk_scan_progress(session_id):
    """Get the progress of a bulk scan session."""
    from bulk_scan_service import get_bulk_scan_manager
    
    manager = get_bulk_scan_manager()
    progress = manager.get_progress(session_id)
    
    if "error" in progress:
        return jsonify(progress), 404
    
    return jsonify(progress)


@app.route("/api/bulk-scan/sessions")
@require_login
def get_bulk_scan_sessions():
    """Get all bulk scan sessions."""
    from bulk_scan_service import get_bulk_scan_manager
    
    manager = get_bulk_scan_manager()
    sessions = manager.get_all_sessions()
    
    return jsonify({"sessions": sessions})


# ============================================================================
# DURABLE JOBS API (v1) — owner-scoped, survives restarts (F-01)
# ============================================================================

@app.route("/api/v1/jobs")
@require_login
def api_list_jobs():
    """List the current user's durable scan jobs (most recent first)."""
    return jsonify({"jobs": jobs_repo.list_jobs_for_user(current_user_login())})


@app.route("/api/v1/openapi.json")
def api_openapi():
    """OpenAPI 3 document for the versioned API (F-13)."""
    return jsonify(build_openapi_spec())


@app.route("/api/v1/scans", methods=["POST"])
def api_create_scan():
    """Create a scan job (versioned API, validated, idempotent).

    Uses the consistent error envelope with the request correlation id. Bulk
    scans reuse the shared ``launch_bulk_scan`` orchestration.
    """
    token = session.get("access_token")
    if not token:
        return api_error("unauthorized", "Authentication required", 401)

    payload = request.get_json(silent=True)
    data, errors = validate_scan_request(payload if payload is not None else {})
    if errors:
        return api_error("validation_error", "Request validation failed", 422, details=errors)

    # Idempotency-Key header takes precedence over the body field.
    idempotency_key = (
        (request.headers.get("Idempotency-Key") or "").strip()
        or data.get("idempotency_key")
        or None
    )

    if data["type"] == "single":
        return api_error(
            "not_implemented",
            "Single-repository scans via the v1 API are not yet available; use bulk.",
            501,
        )

    visibility = data["visibility"]
    try:
        repos = get_repos(token)
    except Exception as exc:
        app.logger.error(f"Failed to list repositories: {exc}")
        return api_error("upstream_error", "Failed to list repositories from GitHub", 502)

    if visibility != "both":
        repos = [repo for repo in repos if repo.get("visibility") == visibility]
    if not repos:
        return api_error("no_repositories", "No repositories available to scan", 422)

    result = launch_bulk_scan(repos, token, visibility, current_user_login(), idempotency_key)
    status = 200 if result.get("idempotent") else 202
    return jsonify(result), status


@app.route("/api/v1/jobs/<job_id>/cancel", methods=["POST"])
@require_login
def api_cancel_job(job_id):
    """Request cancellation of a job (owner-only). Cooperative: the worker stops
    at the next safe checkpoint (F-02)."""
    ok = jobs_repo.request_cancel(Path(job_id).name, owner_login=current_user_login())
    if not ok:
        return api_error("not_found", "Job not found or not owned by you", 404)
    return jsonify({"status": "cancel_requested", "job_id": Path(job_id).name})


@app.route("/api/v1/jobs/<job_id>")
@require_login
def api_get_job(job_id):
    """Fetch a single durable job, enforcing ownership (anti-IDOR, F-06)."""
    job = jobs_repo.get_job(Path(job_id).name)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.get("owner_login") != current_user_login():
        app.logger.warning("Denied cross-user job access for %s", job_id)
        abort(403)
    return jsonify(job)


# ============================================================================
# LEGAL & DOCUMENTATION PAGES
# ============================================================================

@app.route("/documentation")
def documentation():
    """Display comprehensive documentation and help."""
    return render_template("documentation.html")


@app.route("/privacy")
def privacy_policy():
    """Display privacy policy."""
    return render_template("privacy_policy.html")


@app.route("/terms")
def terms_of_service():
    """Display terms of service."""
    return render_template("terms_of_service.html")


@app.route("/support")
def support():
    """Display support and help page."""
    return render_template("support.html")


@app.route("/logout")
def logout():
    session_id = session.get("session_id")
    if session_id:
        cleanup_old_session_data(session_id)
    session.clear()
    return redirect(url_for("index"))


# Global error handlers for graceful error responses
@app.errorhandler(400)
def bad_request(error):
    """Handle 400 Bad Request errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Bad request", "details": str(error)}), 400
    return render_template(
        "error.html",
        status=400,
        message="Bad Request",
        detail="The request was invalid or malformed.",
    ), 400


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 Forbidden errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Forbidden", "details": str(error)}), 403
    return render_template(
        "error.html",
        status=403,
        message="Forbidden",
        detail="You do not have permission to access this resource.",
    ), 403


@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found errors."""
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Not found", "details": str(error)}), 404
    return render_template(
        "error.html",
        status=404,
        message="Page Not Found",
        detail="The page you requested does not exist.",
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    """Handle 500 Internal Server Error."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error", "details": "Please try again later"}), 500
    return render_template(
        "error.html",
        status=500,
        message="Internal Server Error",
        detail="An unexpected error occurred. Please try again later.",
    ), 500


if __name__ == "__main__":
    # Startup recovery: any job left 'running'/'queued' by a previous process is
    # orphaned (its thread died with the process); mark it 'interrupted' (F-01).
    try:
        interrupted = jobs_repo.mark_stale_running_as_interrupted()
        if interrupted:
            logger.info(f"Startup recovery: marked {interrupted} stale job(s) as interrupted")
    except Exception as exc:
        logger.warning(f"Startup job recovery failed: {exc}")

    # Only use debug mode in development
    debug_mode = os.environ.get("FLASK_ENV", "development") == "development"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
