#!/usr/bin/env python3
"""
GVD Enterprise Bulk Scanning Backend Enhancements
Additions to saas/app.py after the existing /logout route
"""

# ADD THESE IMPORTS AT THE TOP OF app.py (with existing imports):
# from datetime import datetime, timedelta  # (already there)
# Add this line:
# import os  # (already there)

# ADD THIS AFTER the /logout route, before error handlers:

@app.route("/bulk-scan-stats")
def bulk_scan_stats():
    """Get dashboard stats including scan counts for the session."""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Get today's date for filtering
    today = datetime.utcnow().date()
    
    scanned_today = 0
    high_risk_findings = 0
    
    try:
        # Scan through scan_reports directory for today's scans
        if SCAN_REPORTS_DIR.exists():
            for owner_dir in SCAN_REPORTS_DIR.iterdir():
                if not owner_dir.is_dir() or owner_dir.name == "bulk":
                    continue
                for repo_dir in owner_dir.iterdir():
                    if not repo_dir.is_dir():
                        continue
                    for scan_dir in repo_dir.iterdir():
                        if not scan_dir.is_dir():
                            continue
                        # Check if scan is from today
                        try:
                            scan_date = datetime.strptime(scan_dir.name, "%Y%m%d%H%M%S").date()
                            if scan_date == today:
                                scanned_today += 1
                                report_json = scan_dir / "report.json"
                                if report_json.exists():
                                    with open(report_json, encoding="utf-8") as f:
                                        report_data = json.load(f)
                                        severity_counts = report_data.get("severity_counts", {})
                                        high_risk_findings += severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
                        except ValueError:
                            continue
    except (OSError, PermissionError) as e:
        logger.warning(f"Failed to read scan statistics: {e}")
    
    return jsonify({
        "scanned_today": scanned_today,
        "high_risk_findings": high_risk_findings,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })


@app.route("/bulk-scan-history")
def bulk_scan_history():
    """Get recent bulk scan reports from this session."""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Track bulk scans in session
    bulk_scans = session.get("bulk_scans", [])
    
    # Enrich with job status
    reports = []
    for scan_id in bulk_scans:
        try:
            bulk_dir = SCAN_REPORTS_DIR / "bulk" / scan_id
            if bulk_dir.exists():
                report_json = bulk_dir / "bulk-report.json"
                if report_json.exists():
                    with open(report_json, encoding="utf-8") as f:
                        report_data = json.load(f)
                        reports.append({
                            "report_id": scan_id,
                            "generated_at": report_data.get("generated_at"),
                            "total_repositories": report_data.get("total_repositories", 0),
                            "scanned_repositories": report_data.get("scanned_repositories", 0),
                            "failed_repositories": report_data.get("failed_repositories", 0),
                            "total_findings": report_data.get("total_findings", 0),
                            "severity_counts": report_data.get("severity_counts", {})
                        })
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load bulk scan {scan_id}: {e}")
    
    return jsonify({"reports": reports})


# MODIFY THE /logout ROUTE TO CLEAN UP BULK SCANS:

@app.route("/logout")
def logout():
    """Logout and cleanup session."""
    # Get session user for logging
    user = session.get("user", {})
    user_login = user.get("login", "unknown")
    
    # Get bulk scan jobs to cleanup
    bulk_scans = session.get("bulk_scans", [])
    
    # Cleanup BULK_SCAN_JOBS entries for this session
    with BULK_SCAN_JOBS_LOCK:
        for job_id in list(BULK_SCAN_JOBS.keys()):
            job = BULK_SCAN_JOBS.get(job_id)
            if job and job.get("created_by") == user_login:
                # Terminate any running processes
                current_process = job.get("current_process")
                if current_process:
                    terminate_process_tree(current_process)
                # Remove job
                del BULK_SCAN_JOBS[job_id]
    
    logger.info(f"User {user_login} logged out. Cleaned up {len(bulk_scans)} bulk scan reports.")
    session.clear()
    return redirect(url_for("index"))


# MODIFY /scan-all ENDPOINT TO TRACK USER AND ADD RATE LIMITING:

@app.route("/scan-all", methods=["POST"])
def scan_all():
    """Start a bulk scan job for all user repositories."""
    token = session.get("access_token")
    if not token:
        return jsonify({"error": "Unauthorized"}), 401
    
    user = session.get("user", {})
    user_login = user.get("login", "unknown")
    
    # RATE LIMITING: Check if user already has a running scan
    with BULK_SCAN_JOBS_LOCK:
        user_jobs = [job for job in BULK_SCAN_JOBS.values() 
                     if job.get("created_by") == user_login and job.get("status") == "running"]
        if len(user_jobs) >= 3:
            return jsonify({"error": "Maximum 3 concurrent scans allowed per user"}), 429

    payload = request.get_json(silent=True) or request.form
    visibility = (payload.get("visibility") or "both").strip().lower()
    if visibility not in {"public", "private", "both"}:
        return jsonify({"error": "Invalid visibility filter."}), 400

    try:
        repos = get_repos(token)
    except Exception as e:
        logger.error(f"Failed to fetch repositories for {user_login}: {e}")
        return jsonify({"error": "Failed to fetch repositories from GitHub."}), 500

    if visibility != "both":
        repos = [repo for repo in repos if repo.get("visibility") == visibility]
    if not repos:
        return jsonify({"error": "No repositories available to scan."}), 400

    job_id = uuid.uuid4().hex
    with BULK_SCAN_JOBS_LOCK:
        BULK_SCAN_JOBS[job_id] = {
            "job_id": job_id,
            "created_by": user_login,
            "created_at": datetime.utcnow().isoformat() + "Z",
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
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    # Track in session
    bulk_scans = session.get("bulk_scans", [])
    bulk_scans.append(job_id)
    session["bulk_scans"] = bulk_scans
    session.modified = True

    worker = threading.Thread(
        target=run_bulk_scan_job,
        args=(job_id, repos, token, visibility),
        daemon=True,
    )
    worker.start()

    append_bulk_scan_log(job_id, f"Bulk scan job created by {user_login}.")
    return jsonify(
        {
            "job_id": job_id,
            "status": "running",
            "visibility": visibility,
            "total_repositories": len(repos),
        }
    )


# ADD JOB EXPIRATION CLEANUP (call this periodically or on app startup):

def cleanup_expired_jobs():
    """Remove jobs older than 24 hours."""
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    with BULK_SCAN_JOBS_LOCK:
        expired = [
            job_id for job_id, job in BULK_SCAN_JOBS.items()
            if job.get("created_at") and 
            datetime.fromisoformat(job["created_at"].replace("Z", "+00:00")) < cutoff_time
        ]
        for job_id in expired:
            job = BULK_SCAN_JOBS.pop(job_id, None)
            if job:
                logger.info(f"Cleaned up expired job {job_id} for user {job.get('created_by')}")

# Call cleanup on app startup
@app.before_request
def before_request_cleanup():
    """Run cleanup before first request of day."""
    if not hasattr(app, '_cleanup_done'):
        cleanup_expired_jobs()
        app._cleanup_done = True
