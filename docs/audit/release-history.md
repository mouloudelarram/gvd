# GVD — Release History

> **Canonical reference** — supersedes root-level `BUG_ELIMINATION_REPORT.md`,
> `COMPLETION_CHECKLIST.md`, `PHASE_3_COMPLETION.md`, `PRODUCTION_RELEASE_SUMMARY.md`,
> and `PDF_ENHANCEMENT_SUMMARY.md` (all now redirect stubs, Phase 9 C-28, 2026-08-17).

Chronological record of major milestones, decisions, and phase completions.  
For a line-by-line evidence log see [`docs/MIGRATION_NOTES.md`](../MIGRATION_NOTES.md).

---

## Phase 1 — Discovery (2026-07-16)

**Completed:**
- Full repository inventory (source files, services, routes, templates, static assets,
  dependencies, configuration files, generated artefacts, documentation).
- Verified baseline: `saas/` 103 tests passing, `cli/` 9 passing before work started.
- Produced prioritized audit report (`docs/audit/AUDIT_REPORT.md`) — 19 findings (F-01…F-19).
- Current-state and target-state architecture documented.
- ADRs 0001–0003 recorded.

**Blockers recorded:**
- B1: Docker not installed on this host (gates run in CI).
- B2: OAuth secret rotation requires GitHub App access (human action).
- B3: Live OAuth/private-repo e2e require real credentials.

---

## Phase 2 — Target Design (2026-07-16)

**Completed:**
- Target architecture defined: modular monolith with PostgreSQL + Redis + extracted worker.
- Service catalog, data model, event catalog, trust-boundary diagram documented.
- ADR 0004 added (durable DB queue and worker token handoff).
- Migration roadmap published.

---

## Phase 3 — Foundation (2026-07-16)

**Completed:**
- C-01: `Severity` made `str`-mixin enum — fixed 4 test failures caused by dual-import path.
- C-02: CLI dependencies pinned (`cli/pyproject.toml`).
- C-03: Server-side sessions (Redis-backed) replacing cookie-stored tokens (F-03).
- C-04: CSRF protection added to all state-changing routes.
- Secret management rules established; `.env` files confirmed gitignored.

**Test result after Phase 3:** saas 103 → 107 passing, cli 9 → 16 passing.

---

## Phase 4 — Backend and Persistence (2026-07-16)

**Completed:**
- C-05: Per-resource authorization — owner-only report access (closes F-06 IDOR).
- API v1 routes (`/api/v1/…`) with versioned prefix.
- PostgreSQL schema and Alembic migration baseline.
- Scan job durable state (`scan_jobs` table replaces in-process dict for single scans).
- Correlation IDs on all requests.
- Structured JSON logging in production mode.
- Health (`/health`) and readiness (`/readiness`) endpoints.

---

## Phase 5 — Asynchronous Scanning (2026-07-16)

**Completed:**
- C-06: Clone-URL validation — allows only `github.com` hostnames (closes F-04).
- C-07: Path-traversal guard on report paths (closes F-05).
- Background worker architecture: jobs dequeued from Redis, processed by `gvd-worker` container.
- Idempotency: duplicate scan requests return the existing job.
- Cancellation semantics: `POST /scan-all/<job_id>/cancel` stops between repositories.
- Retry policy: exponential backoff + jitter (max 3 attempts) with dead-letter record.
- Temporary clone workspace cleanup on success and failure.
- ADR 0004 implemented.

---

## Phase 6 — Frontend (2026-07-16 → 2026-07-20)

**Completed:**
- C-17: Accessibility (WCAG 2.2 AA) — skip-link, ARIA landmarks, modal focus-trap,
  `aria-live` regions, keyboard navigation, reduced-motion support, ARIA `expanded/selected`.
- C-18: Corruption repair — removed stray `</content>` artifact from 24 tracked files.
- C-19: `dashboard.html` cleanup — truncated dead JS after valid `{% endblock %}`.
- C-20: Polished OAuth-decline journey — `access_denied` returns user-friendly page;
  provider `error_description` not reflected (XSS prevention).
- C-21: Error handler fix — `400/403/404/500` handlers now pass correct `status=` and `detail=`
  to `error.html` (previously showed blank error code).
- C-22: Removed orphaned `scan_results.html` template (referenced non-existent assets).
  Added `test_templates_reference_only_existing_static_assets` guard.
- C-23: Playwright + axe `frontend-test` CI job authored (`saas/frontend-tests/`).
- C-24: Cleanup report created (`docs/audit/CLEANUP_REPORT.md`).
- C-25: `pytest.ini` `norecursedirs` — prevents test-collection failures from runtime clone dirs.

**Test result after Phase 6:** 127 passing (saas 111 + cli 16), 0 failing.

---

## Phase 7 — Containerization (pending CI)

**Gate:** `docker compose up --build` → all containers healthy.
**Status:** Wired in CI (`compose-smoke` job); blocked locally by B1 (Docker not installed).

---

## Phase 8 — Quality and Security (pending CI)

**Gate:** Playwright+axe, pip-audit, trivy, ruff, all passing.
**Status:** `frontend-test` job wired in CI; blocked locally by B5 (Node not installed).

---

## Phase 9 — Cleanup and Documentation (2026-08-17)

**Completed:**
- C-26: Removed 5 non-loaded stylesheets (`animations.css`, `accessibility.css`,
  `responsive.css`, `utilities.css`, root `style.css`). Zero live template references confirmed.
- C-27: Removed 3 superseded bulk-scan snippet files (`BACKEND_CHANGES.py`,
  `FRONTEND_CHANGES.js`, `HTML_CHANGES.html`). Feature already integrated.
- C-28: Documentation consolidation — 25 root-level markdown files collapsed into 8 canonical
  docs in `docs/` catalog; originals replaced by redirect stubs.

**Files removed (C-26):**
`saas/static/css/animations.css`, `accessibility.css`, `responsive.css`, `utilities.css`,
`static/style.css` (root).

**Files removed (C-27):**
`saas/BACKEND_CHANGES.py`, `saas/FRONTEND_CHANGES.js`, `saas/HTML_CHANGES.html`.

**Root docs archived as redirect stubs (C-28):**
`ARCHITECTURE.md`, `AWS_EC2_QUICK_START.md`, `BUG_ELIMINATION_REPORT.md`,
`BULK_SCAN_FILES_REFERENCE.md`, `BULK_SCAN_IMPLEMENTATION.md`, `BULK_SCAN_IMPLEMENTATION_PLAN.md`,
`BULK_SCAN_IMPLEMENTATION_SUMMARY.md`, `BULK_SCAN_QUICK_START.md`, `BULK_SCAN_TESTING_GUIDE.md`,
`COMPLETION_CHECKLIST.md`, `DEPLOYMENT_GUIDE.md`, `DOCKER_ARCHITECTURE_GUIDE.md`,
`DOCKER_QUICK_REFERENCE.md`, `DOCKER_SETUP.md`, `ENTERPRISE_UPGRADE.md`,
`IMPLEMENTATION_GUIDE.md`, `INTEGRATION_GUIDE.md`, `PDF_ENHANCEMENT_SUMMARY.md`,
`PHASE_3_COMPLETION.md`, `PRODUCTION_DEPLOYMENT_GUIDE.md`, `PRODUCTION_RELEASE_SUMMARY.md`,
`QUICK_REFERENCE.md`, `README_BULK_SCAN.md`, `SCRIPTS_GUIDE.md`.

---

## Phase 10 — Release Validation (pending)

See `docs/audit/AUDIT_REPORT.md` for the full gate checklist.

---

## Bug Fixes Summary

| ID | Bug | Fixed in | Evidence |
|----|-----|----------|---------|
| F-09 / C-01 | `Severity` dual-import equality failure | Phase 3 | 4 test failures → passing |
| F-06 / C-05 | IDOR on report access | Phase 4 | `test_report_access_denied_for_other_user` |
| F-04 / C-06 | Unrestricted clone URLs | Phase 5 | `test_clone_url_validation` |
| F-05 / C-07 | Path traversal on report paths | Phase 5 | `test_path_traversal_rejected` |
| C-20 | OAuth-decline → confusing 400 error | Phase 6 | `test_callback_access_denied_*` |
| C-21 | Error handlers passing wrong kwargs | Phase 6 | `test_404_renders_error_page_with_status_code` |
| C-22 | Orphaned template linked missing assets | Phase 6 | `test_templates_reference_only_existing_static_assets` |

---

## PDF Enhancement History

The PDF report generator (`saas/pdf_service.py`) was enhanced progressively:

| Version | Change |
|---------|--------|
| 1.0 | Basic text-only PDF via `reportlab` |
| 1.1 | Severity colour coding (Critical=red, High=orange, Medium=yellow, Low=green) |
| 1.2 | Cover page with repository metadata and scan timestamp |
| 1.3 | Executive summary section with finding counts |
| 1.4 | Findings table with file path, line, detail, recommendation columns |
| 1.5 | Bulk-scan PDF added (multi-repository summary + per-repo breakdown) |

---

*See also: [../MIGRATION_NOTES.md](../MIGRATION_NOTES.md) · [AUDIT_REPORT.md](AUDIT_REPORT.md) · [BASELINE.md](BASELINE.md)*

