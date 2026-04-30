"""Scanning service module for GVD Flask application."""

import json
import logging
import threading
import uuid
import subprocess
import platform
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import wrap

from flask import session

from clone import ensure_repo_cloned
from config import generate_csrf_token

logger = logging.getLogger(__name__)

# Global scan job tracking
BULK_SCAN_JOBS = {}
BULK_SCAN_JOBS_LOCK = threading.Lock()
WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class RepoSkippedError(Exception):
    def __init__(self, owner, repo_name):
        super().__init__(f"Skipped {owner}/{repo_name}")
        self.owner = owner
        self.repo_name = repo_name


def build_repo_key(owner, repo_name):
    """Build a repository key for tracking."""
    return f"{Path(owner).name}/{Path(repo_name).name}"


def update_bulk_scan_job(job_id, **changes):
    """Update bulk scan job with thread safety."""
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return None
        job.update(changes)
        return dict(job)


def serialize_bulk_scan_job(job):
    """Serialize bulk scan job for JSON response."""
    return {
        key: value
        for key, value in job.items()
        if key not in {"current_process", "skip_requests"}
    }


def append_bulk_scan_log(job_id, message):
    """Append log message to bulk scan job."""
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return
        logs = job.setdefault("logs", [])
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        logs.append(f"[{timestamp}] {message}")
        job["updated_at"] = datetime.utcnow().isoformat() + "Z"


def is_repo_skip_requested(job_id, repo_key):
    """Check if repository skip was requested."""
    with BULK_SCAN_JOBS_LOCK:
        job = BULK_SCAN_JOBS.get(job_id)
        if not job:
            return False
        skip_requests = job.get("skip_requests") or set()
        return repo_key in skip_requests


def update_bulk_pending_repositories(job_id, pending_repositories):
    """Update pending repositories list for bulk scan job."""
    update_bulk_scan_job(job_id, pending_repositories=list(pending_repositories))


def terminate_process_tree(process):
    """Terminate a process and all its children."""
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


def sanitize_command_error(exc, token):
    """Sanitize command error by removing sensitive tokens."""
    stderr = (exc.stderr or "").replace(token, "[redacted]").strip()
    stdout = (exc.stdout or "").strip()
    return stderr or stdout or "Scan failed."


def build_scan_result(report_data, owner, repo_name, repo_path, scan_output_dir, command_output):
    """Build scan result from report data."""
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
