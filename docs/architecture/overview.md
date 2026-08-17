# GVD — Architecture Overview

> **Canonical reference** — supersedes root-level `ARCHITECTURE.md`
> (archived as redirect stub, Phase 9 C-28, 2026-08-17).
> For the full target-architecture document see [architecture/TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md).

---

## Product Summary

GVD (GitHub Vulnerability Detector) helps developers find secrets and security issues in their
GitHub repositories. Users log in with GitHub OAuth, select repositories from a dashboard, and
trigger scans that analyse Git history and file content for leaked credentials, sensitive files,
and misconfiguration.

---

## Current Architecture (Phase 5 baseline)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│  HTML/CSS/JS (no framework)                                         │
│  base.js · dashboard.js · bulk-scan-and-notifications.js           │
└────────────────────┬────────────────────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼────────────────────────────────────────────────┐
│  Flask SaaS App  (saas/)                                            │
│  app.py · auth.py · github.py · clone.py                           │
│  bulk_scan_service.py · scan_service.py · scanner_lib.py           │
│  pdf_service.py · jobs_repo.py · stats_repo.py                     │
│  Session: Redis (server-side)                                       │
│  DB: PostgreSQL + SQLAlchemy + Alembic                              │
└────────┬───────────────────────┬────────────────────────────────────┘
         │                       │
┌────────▼──────┐      ┌─────────▼──────────────────────────────────┐
│  PostgreSQL   │      │  Redis                                      │
│  (gvd-db)     │      │  Job queue + session storage               │
└───────────────┘      └─────────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────────────────┐
│  scanner_lib.py  (in-process)                                       │
│  git clone → pattern engine → risk engine → report builder         │
│  saas/scan_reports/  (volume: gvd_scan_reports)                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### `saas/app.py` — Flask application entry point

- Defines all HTTP routes
- OAuth state validation and session rotation
- CSRF protection on state-changing requests
- Per-resource authorization (`@login_required`, owner checks)
- Health and readiness endpoints

### `saas/auth.py` — GitHub OAuth helpers

- Builds authorization URL with `state` parameter
- Exchanges code for access token
- Validates `state` on callback
- Token lifecycle (stored server-side, redacted from logs)

### `saas/github.py` — GitHub API client

- Paginated repository listing
- Rate-limit handling
- Error mapping (timeout, 403, 404 → domain errors)

### `saas/scanner_lib.py` — In-process scanner

- Clones the repository into an isolated temp directory
- Runs pattern engine (regex-based secret detection)
- Runs risk engine (sensitive file detection)
- Generates JSON report
- Cleans up temp directory on completion or failure

### `saas/bulk_scan_service.py` — Bulk scan orchestration

- Manages in-process `BULK_SCAN_JOBS` dict (thread-safe)
- Spawns background threads
- Rate limits concurrent jobs per user
- Expiry and cleanup
- See [bulk-scan.md](../guides/bulk-scan.md) for full details

### `saas/pdf_service.py` — PDF report generation

- Converts JSON report to styled PDF via `reportlab`

### `saas/jobs_repo.py` / `saas/stats_repo.py` — Repository layer

- Database access for scan jobs and aggregate statistics
- SQLAlchemy models, transaction boundaries

### `cli/` — Command-line scanner

- Standalone Python package (`pip install -e ./cli`)
- `gvd scan [--path] [--output] [--format]`
- Shares scanner logic with the SaaS app (`saas/scanner_lib.py` wraps `cli/scanner/`)
- Generates JSON, Markdown, and summary reports

---

## Request Flow — Single Repository Scan

```
Browser  POST /scan {repo_url, repo_name}
           │
           ▼
app.py   validate session, CSRF, ownership
           │
           ▼
scan_service.py  create ScanJob record in DB
           │
           ▼
scanner_lib.py (background thread)
  1. git clone <repo_url> → /tmp/<uuid>/
  2. pattern_engine.scan()
  3. risk_engine.classify()
  4. report_builder.write_json() → scan_reports/<user>/<ts>/report.json
  5. pdf_service.generate() → report.pdf
  6. update ScanJob status = completed
  7. rm -rf /tmp/<uuid>/
           │
           ▼
Browser  GET /scan/<job_id>  (polling every 2s)
           │
           ▼
app.py   return ScanJob status from DB
```

---

## Data Model (abbreviated)

```sql
users            (id, github_login, github_id, created_at, last_login)
repositories     (id, owner_user_id, full_name, private, last_scanned_at)
scan_jobs        (id, owner_user_id, repo_id, status, started_at, completed_at, report_path)
findings         (id, scan_job_id, severity, category, file_path, line, detail, recommendation)
audit_events     (id, user_id, action, resource_type, resource_id, ip, created_at)
```

Full schema: see `saas/migrations/` (Alembic).

---

## Security Boundaries

```
┌─────────────────────────────────────────────────────────┐  PUBLIC
│  nginx (TLS termination, rate limiting)                 │  ZONE
└─────────────────────┬───────────────────────────────────┘
                      │ internal HTTP
┌─────────────────────▼───────────────────────────────────┐  APP
│  gvd-saas                                               │  ZONE
│  – Authenticated routes only (session cookie)           │
│  – CSRF on state-changing requests                      │
│  – Owner-only access on reports/jobs                    │
│  – Token redacted from all logs                         │
└─────────────────────┬───────────────────────────────────┘
                      │ internal network only
┌─────────────────────▼───────────────────────────────────┐  DATA
│  gvd-db (PostgreSQL)   gvd-redis (Redis)                │  ZONE
│  No public ports        No public ports                 │
└─────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Web framework | Flask | 3.x |
| WSGI server | gunicorn | 21.x |
| Database | PostgreSQL | 16 |
| ORM / migrations | SQLAlchemy + Alembic | 2.x / 1.x |
| Job queue / sessions | Redis | 7 |
| PDF generation | reportlab | 4.x |
| HTTP client | requests + truststore | — |
| Scanner patterns | regex (stdlib) | — |
| Frontend | HTML/CSS/vanilla JS | — |
| Containerization | Docker + Compose v2 | — |
| CI | GitHub Actions | — |
| Testing | pytest | 8.x |
| Linting | ruff | 0.x |

---

## ADR Index

| ADR | Decision |
|-----|---------|
| [0001](../adr/0001-modular-monolith-with-extracted-worker.md) | Modular monolith with extracted worker |
| [0002](../adr/0002-durable-state-postgres-redis.md) | Durable state with PostgreSQL + Redis |
| [0003](../adr/0003-server-side-sessions-and-token-handling.md) | Server-side sessions and token handling |
| [0004](../adr/0004-durable-db-queue-and-worker-token-handoff.md) | Durable DB queue and worker token handoff |

---

## Migration Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 — Discovery | Inventory, audit, baselines | ✅ Complete |
| 2 — Target design | Architecture, ADRs, contracts | ✅ Complete |
| 3 — Foundation | Config, logging, security baseline | ✅ Complete |
| 4 — Backend + persistence | API v1, migrations, authorization | ✅ Complete |
| 5 — Async scanning | Durable worker, queue, retries | ✅ Complete |
| 6 — Frontend | Production-quality UI | ✅ Complete |
| 7 — Containerization | Docker Compose validation | 🔲 CI gate (B1) |
| 8 — Quality + security | Security scan, e2e tests | 🔲 CI gate (B5) |
| 9 — Cleanup + docs | Archive stubs, catalog | 🔄 In progress |
| 10 — Release validation | All gates, evidence, readiness report | 🔲 Pending |

---

*See also: [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md) · [../adr/README.md](../adr/README.md) · [../audit/AUDIT_REPORT.md](../audit/AUDIT_REPORT.md)*

