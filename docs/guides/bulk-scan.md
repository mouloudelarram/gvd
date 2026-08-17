# GVD — Bulk Scan Guide

> **Canonical reference** — supersedes all root-level `BULK_SCAN_*` and `README_BULK_SCAN.md`
> files (archived as redirect stubs, Phase 9 C-28, 2026-08-17).

## Overview

Bulk Scan lets an authenticated user launch a single job that scans **every repository** they
can access on GitHub. Results stream to the dashboard in real time and are saved as a
downloadable JSON/PDF report.

---

## User Journey

1. Log in with GitHub OAuth.
2. On the dashboard, click **Scan All** (top-right area of the repository grid).
3. The bulk-scan modal opens.  Enter an optional label, then click **Start Bulk Scan**.
4. The modal shows:
   - Live progress bar (% complete)
   - Counts of Critical / High / Medium / Low findings so far
   - A scrolling log of repositories being processed
5. When the job finishes a **Download Report (JSON)** and **Download Report (PDF)** button appear.
6. The job is also listed in **Scan History** for 24 hours.

The user can click **Cancel** at any time; cancellation is honoured between repositories.

---

## Architecture

```
Browser
  │  POST /scan-all               (start job, returns job_id)
  │  GET  /scan-all/<job_id>      (poll status, 1-second interval)
  │  POST /scan-all/<job_id>/cancel
  ▼
Flask (saas/app.py)
  │  Validates session + CSRF
  │  Rate-limits: max 3 concurrent jobs per user
  │  Creates entry in BULK_SCAN_JOBS dict (threadsafe)
  ▼
bulk_scan_service.py            (background thread)
  │  Fetches all repos via GitHub API (paginated)
  │  For each repo: clones → runs scanner_lib.run_scan()
  │  Writes progress + logs into BULK_SCAN_JOBS[job_id]
  │  On completion: writes saas/scan_reports/bulk/<job_id>/bulk-report.json
  │                  generates PDF via pdf_service.py
  ▼
saas/static/js/bulk-scan-and-notifications.js   (frontend polling + UI)
```

> **Note:** `BULK_SCAN_JOBS` is an in-process dict protected by `BULK_SCAN_JOBS_LOCK`. It does
> not survive service restarts (tracked as F-01, deferred to Phase 5 durable worker).

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/scan-all` | session | Create a bulk-scan job |
| `GET`  | `/scan-all/<job_id>` | session | Poll job status |
| `POST` | `/scan-all/<job_id>/cancel` | session (owner) | Cancel running job |
| `GET`  | `/bulk-scan-stats` | session | Aggregate finding counts |
| `GET`  | `/bulk-scan-history` | session | List this user's recent jobs |
| `GET`  | `/download-bulk-report/<job_id>` | session (owner) | Download JSON report |
| `GET`  | `/download-bulk-report-pdf/<job_id>` | session (owner) | Download PDF report |

### POST /scan-all — Request body

```json
{ "visibility": "both" }
```

`visibility` may be `"public"`, `"private"`, or `"both"` (default).

### POST /scan-all — Response

```json
{
  "job_id": "abc123...",
  "status": "running",
  "total_repos": 42
}
```

### GET /scan-all/<job_id> — Response

```json
{
  "job_id": "abc123...",
  "status": "running",
  "progress": 14,
  "total": 42,
  "current_repo": "my-org/my-repo",
  "logs": ["Scanning my-org/my-repo ...", "..."],
  "stats": { "critical": 0, "high": 2, "medium": 5, "low": 12 },
  "error": null
}
```

`status` values: `running` | `completed` | `cancelled` | `failed`.

---

## Configuration

All values are set via environment variables (no new vars required):

| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_BULK_SCAN` | `true` | Set to `false` to disable the feature entirely |
| `MAX_CONCURRENT_BULK_SCANS` | `3` | Max concurrent jobs per user (rate limit) |
| `SCAN_TIMEOUT_SECONDS` | `300` | Per-repository scan timeout |
| `MAX_REPOS_FETCH` | `1000` | GitHub API page cap |

---

## Rate Limiting

- A user may have at most **3** active bulk scan jobs simultaneously.
- Attempting a 4th returns HTTP `429 Too Many Requests` with:
  ```json
  { "error": "rate_limit", "message": "Too many concurrent scans (max 3)" }
  ```

---

## Job Lifecycle and Expiry

Jobs expire after **24 hours**. An hourly background sweep calls
`bulk_scan_service.cleanup_expired_jobs()` which:
1. Terminates any live subprocess tree via `terminate_process_tree()`.
2. Removes the job from `BULK_SCAN_JOBS`.
3. Leaves the report artifact on disk (if completed).

On user **logout** all jobs owned by that user are terminated and removed immediately.

---

## Report Format

Reports are stored at `saas/scan_reports/bulk/<job_id>/`:

```
bulk-report.json    — canonical JSON report
bulk-report.pdf     — generated PDF
```

### bulk-report.json schema (abbreviated)

```json
{
  "job_id": "abc123",
  "owner_login": "octocat",
  "started_at": "2026-08-17T10:00:00Z",
  "completed_at": "2026-08-17T10:12:34Z",
  "total_repos": 42,
  "scanned_repos": 42,
  "stats": { "critical": 1, "high": 4, "medium": 9, "low": 23 },
  "findings": [
    {
      "repo": "octocat/Hello-World",
      "severity": "high",
      "type": "secret",
      "file": ".env",
      "line": 3,
      "detail": "AWS_SECRET_ACCESS_KEY pattern detected",
      "recommendation": "Rotate the credential and remove from history"
    }
  ]
}
```

---

## Security

| Control | Implementation |
|---------|---------------|
| Authentication | All endpoints require an active session (`@login_required`) |
| Authorization | Job polling and downloads are owner-only (HTTP 403 on mismatch) |
| CSRF | All state-changing requests (`POST`, `POST /cancel`) require the CSRF token |
| XSS | Frontend uses `escapeHtml()` before inserting dynamic content |
| Path traversal | `job_id` is validated against `^[a-f0-9]{32}$` before filesystem access |
| Token redaction | GitHub token is never written to logs or included in job state |
| Report access | Missing `owner_login` marker → denied (privacy by default) |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Modal opens but never starts | CSRF token missing or expired | Hard-refresh the page and retry |
| Progress stuck at 0% | Worker thread died early | Check server logs; restart the service |
| 429 on start | 3 concurrent jobs already running | Wait for a job to complete or cancel one |
| Reports not found after restart | `BULK_SCAN_JOBS` is in-memory | Completed report files on disk are still accessible via `/bulk-scan-history` |
| PDF download fails | `reportlab` not installed | `pip install reportlab` or rebuild the Docker image |

---

## Testing

```bash
# Unit + integration (backend)
cd saas && python -m pytest test_worker.py test_jobs.py test_scanner_lib.py -v

# All backend tests
cd saas && python -m pytest -q

# Frontend component test (requires Node + Playwright)
cd saas/frontend-tests && npm ci && npx playwright test
```

Key test files:

- `saas/test_worker.py` — worker thread + job lifecycle
- `saas/test_jobs.py` — job creation, status transitions, expiry
- `saas/test_scanner_lib.py` — per-repo scanning

---

## Known Limitations and Accepted Risks

| Risk | Severity | Status |
|------|----------|--------|
| `BULK_SCAN_JOBS` lost on restart (in-process dict) | Medium | Accepted; durable queue planned for Phase 5 |
| Mid-repository cancellation not instant | Low | Accepted; cancellation applies between repos |
| No dead-letter queue for failed jobs | Low | Accepted; failure recorded in report JSON |
| Large repos may exceed `SCAN_TIMEOUT_SECONDS` | Medium | Increase via env var; logged as `timed_out` |

---

*See also: [docker.md](docker.md) · [deployment.md](deployment.md) · [quick-reference.md](quick-reference.md)*

