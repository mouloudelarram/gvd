import os
import json
import threading
import uuid
import subprocess
import requests
from datetime import datetime
from pathlib import Path
from textwrap import wrap

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for

from auth import get_github_auth_url, get_github_token, get_github_user
from clone import clone_repos, ensure_repo_cloned
from github import get_repo_details, get_repos, search_repos


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
    token = get_github_token()
    session["access_token"] = token
    session["user"] = get_github_user(token)
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("index"))
    visibility = (request.args.get("visibility") or "both").strip().lower()
    if visibility not in {"public", "private", "both"}:
        visibility = "both"
    repos = get_repos(token)
    if visibility != "both":
        repos = [repo for repo in repos if repo.get("visibility") == visibility]
    return render_template(
        "dashboard.html",
        user=session.get("user"),
        repos=repos,
        current_visibility=visibility,
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
    pdf_path = scan_output_dir / "report.pdf"
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

    try:
        result = run_repo_scan(repo, token)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").replace(token, "[redacted]").strip()
        return jsonify({"error": "Scan failed.", "details": stderr or (exc.stdout or "").strip()}), 500
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Scanner timed out."}), 504
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


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

    report_dir = SCAN_REPORTS_DIR / Path(owner).name / Path(repo_name).name / Path(scan_id).name
    files = {
        "json": report_dir / "report.json",
        "pdf": report_dir / "report.pdf",
    }
    target = files.get(file_format)
    if not target or not target.exists():
        abort(404)

    as_attachment = request.args.get("download") == "1"
    return send_file(target, as_attachment=as_attachment, download_name=target.name)


@app.route("/repo-details/<owner>/<repo_name>")
def repo_details(owner, repo_name):
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_repo_details(token, owner, repo_name))


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


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
