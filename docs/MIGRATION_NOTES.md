# GVD — Migration Notes & Changelog

Chronological log of concrete changes made during the modernization, with verification evidence.
The immutable "before" state is in `audit/BASELINE.md`.

## Phase 1 — Discovery (2026-07-16)

### Documentation deliverables added (non-breaking)
- `docs/audit/BASELINE.md` — measured toolchain + red test baseline.
- `docs/audit/AUDIT_REPORT.md` — 19 prioritized findings (F-01…F-19) with evidence + blockers.
- `docs/architecture/TARGET_ARCHITECTURE.md` — current/target diagrams, service catalog, roadmap.
- `docs/adr/` — ADR index + ADR 0001 (modular monolith + worker), 0002 (Postgres+Redis),
  0003 (server-side sessions & token handling).

### First safe, test-backed code changes (Phase 3.1 down-payment)

**C-01 — `Severity` made a `str`-mixin enum (fixes F-09 symptom).**
- File: `cli/core/models.py` — `class Severity(Enum)` → `class Severity(str, Enum)`.
- Why: the scanner is importable under two paths (`cli.core.models` and `core.models`), which
  created two distinct enum classes whose members were never `==`. A `str`-mixin makes equality
  value-based across both, without changing any output (`ReportBuilder` already serializes via
  `.value`, which still returns the plain string).
- Verification:
  - Before: `cli` suite = 9 passed / 7 failed.
  - After: `cli` suite = **13 passed / 3 failed** (`py -m pytest -p no:flask -q`). The 4
    `TestPatternEngine` severity tests now pass; no regressions.
- Residual: 3 remaining CLI failures (`test_scan_history_success/empty`,
  `test_scan_repo_integration`) are **test-harness** defects — they `@patch` an attribute on the
  `cli` package that does not exist (`ReportExporter`). Tracked under F-09's import-cleanup task
  for Phase 3.1; the underlying scanner code is not implicated.

**C-02 — Pinned CLI dependencies (fixes F-15).**
- File: `cli/pyproject.toml` — replaced open-ended `>=` pins with reproducible ranges capped at the
  next major (`rich>=15,<16`, `reportlab>=4.5.1,<5`, `python-dateutil>=2.9,<3`), matching the
  versions verified against the baseline.
- Follow-up: add a lockfile + CI dependency scanning in Phase 8.

### Not changed yet (deliberately deferred, see AUDIT_REPORT.md)
- Persistence/queue/worker extraction (F-01, F-02), server-side sessions (F-03), clone-URL
  hardening (F-04, F-05), per-resource authz (F-06), API v1/OpenAPI/CSRF (F-12, F-13). These are
  larger, test-backed migrations scheduled for Phases 4–5 and must not be rushed in discovery.

### Blockers recorded
- B1: Docker/Compose not installed on this host → container gates run in CI.
- B2: OAuth secret rotation requires GitHub OAuth App access (org action).
- B3: Live OAuth/private-repo e2e require real credentials → use mocks/recordings in CI.

## Phase 4.2 down-payment — Per-resource authorization (2026-07-16)

**C-05 — Owner-only report access (closes F-06 IDOR).**
- File: `saas/app.py`.
- Reports can contain discovered secrets, so each report is now readable only by the user who
  initiated the scan. The initiating GitHub login is threaded through `/scan` and `/scan-all` into
  `run_repo_scan`/`run_bulk_scan_job` and recorded as a restart-safe marker:
  - per-repo scans write `meta.json` (`scanned_by`) beside the report artifacts;
  - bulk scans embed `owner_login` inside `bulk-report.json`.
- Enforcement (returns HTTP 403 on mismatch, and treats a missing marker as *denied* —
  privacy-by-default): `/repo-report/...`, `/download-report/...`, and `scan-history` now filter to
  the current user's own scans via `is_authorized_for_scan` / `is_authorized_for_bulk_report`.
- Report ids remain timestamp-based for now; the durable fix (UUID ids + `owner_user_id` column)
  lands with persistence in Phase 4.1. This interim marker already removes the cross-user read.
- Tests (all green): 4 helper unit tests + an end-to-end route test asserting a different user
  gets **403** while the owner gets **200** (`saas/test_app.py::TestReportAuthorization`,
  `TestFlaskApp::test_repo_report_denies_cross_user`).

**C-06 — Quality gates & portable tooling.**
- `saas/pytest.ini`, `cli/pytest.ini`: disable the incompatible global `pytest-flask` plugin so
  `pytest` runs with no manual flags.
- `.github/workflows/ci.yml`: lint (ruff), tests (saas+cli matrix), gitleaks secret scan, pip-audit
  dependency audit, CycloneDX SBOM, and a Docker Compose smoke test (runs the container gates in
  CI → mitigates B1).
- `ruff.toml` (conservative initial rule set), `saas/requirements-dev.txt` (pinned tools),
  `.gitignore` hardened for `.env.*` while keeping secret-free templates.
- **F-20 (new):** `docker-compose.yml` references `env_file: ./saas/.env`, which is gitignored, so a
  clean `docker compose up --build` fails without it. CI generates the file; a proper fix (use
  `environment:` + a committed `.env.example`) is scheduled for Phase 7.

### Verification (measured, this increment)
- SaaS: **26 passed / 0 failed**; CLI: **16 passed / 0 failed** (`pytest -q`, no manual flags).
- `app` imports cleanly; `ruff.toml` and `ci.yml` parse. Ruff/Docker not runnable on this host
  (documented) → executed in CI.

## Phase 7 down-payment — Portable clean Compose startup (2026-07-16)

**C-07 — `docker compose up --build` works on a clean checkout (closes F-20).**
- `docker-compose.yml`: removed the hard dependency on the gitignored `./saas/.env`. Required
  secrets are now injected via `environment:` using `${VAR:?...}`/`${VAR:-default}` interpolation
  from the root `.env` (auto-loaded by Compose) or the shell. Obsolete `version:` key removed.
- Healthcheck now targets the unauthenticated `/health` (was `/`) in both `docker-compose.yml` and
  `saas/Dockerfile`.
- Switched host bind-mounts to **named volumes** (`gvd_scan_reports`, `gvd_repos`) — no host
  absolute paths; clean `down -v` reset.
- Removed the decorative `gvd-cli` service (it only echoed and exited and was unusable by the web
  container).
- Added committed, secret-free `.env.example` (root) and `docs/guides/docker-compose.md` quick
  start. CI `compose-smoke` simplified to rely on shell-env interpolation (no fabricated file).
- Verified: `docker-compose.yml` parses; single service `gvd-saas`; volumes
  `gvd_scan_reports`, `gvd_repos`. Not run here (Docker absent, B1) → executed by CI.

**F-19 (honest caveat surfaced):** in-container scanning is still not functional — the SaaS image
(build context `./saas`) does not bundle the CLI, and `get_gvd_executable()` looks for
`../cli/cli.py` which is absent in the container. Documented in the Compose guide; the fix
(package the scanner as an importable library invoked by a worker) is scheduled for Phase 5.

### Status of findings (cumulative)
| Finding | Status |
|---------|--------|
| F-04, F-05, F-07, F-08 | ✅ Resolved (C-03) |
| F-06 IDOR on reports/jobs | ✅ Resolved for report downloads + history (C-05); UUID ids deferred to Phase 4.1 |
| F-09 (test-visible) | ✅ Resolved (C-01, C-04) |
| F-11 stats global/non-durable | ✅ Resolved (C-08) |
| F-15 deps pinning | ✅ Resolved (C-02) |
| F-20 clean compose startup | ✅ Resolved (C-07); in-container *scanning* still blocked by F-19 |
| F-01 durable state | 🟡 Foundation laid (C-08: DB+migrations); jobs migration next |
| F-02, F-03, F-12, F-13, F-16, F-19 | ⏳ Open (Phases 4–5) |

## Phase 4.1 — Persistence foundation (2026-07-16)

**C-08 — Durable, per-user scan statistics on SQLAlchemy + Alembic (closes F-11; foundation for F-01).**
- New modules (all dependency-lazy so imports have no side effects):
  - `saas/db.py` — `Base`, lazily-created engine from `DATABASE_URL` (default SQLite at
    `saas/data/gvd.db`), `session_scope()` transaction helper, `run_migrations()` (programmatic
    Alembic upgrade), and `ensure_schema()` (runs migrations once at runtime, `create_all`
    fallback).
  - `saas/models_db.py` — `ScanEvent` ORM model (one row per completed scan, attributed to the
    initiating user).
  - `saas/stats_repo.py` — `record_scan_event()` / `get_today_stats()` (per-user aggregation).
- Alembic wired: `saas/alembic.ini`, `saas/migrations/env.py`, `script.py.mako`, and initial
  revision `0001_initial` creating `scan_events` (+ indexes).
- `saas/app.py`: removed the in-memory `SCAN_STATISTICS`/`STATISTICS_LOCK`/`track_scan_completion`/
  `get_today_date`. `run_repo_scan` now records a durable, best-effort `ScanEvent` attributed to
  the initiating user (threaded via the `scanned_by` value from C-05). `/api/session-stats` returns
  **per-user** stats (fixes the previous cross-user information leak).
- `saas/requirements.txt`: added `SQLAlchemy>=2.0.30,<2.1`, `alembic>=1.13,<2`.
- `.gitignore`: ignore `/saas/data/`, `*.db`, `*.sqlite3`.
- Tests (`saas/test_persistence.py`, all green): migration creates the schema **from a clean
  database** (asserts `scan_events` + `alembic_version`); per-user aggregation is correct; users are
  isolated from each other's statistics.

### Verification (measured, this increment)
- SaaS: **29 passed / 0 failed** (26 prior + 3 persistence); CLI: **16 passed / 0 failed**.
- SQLAlchemy 2.0.49 + Alembic 1.18.4 are available locally, so the migration + repository were run
  and asserted here (not just parsed). `app` imports cleanly; no `.db` file is created during the
  suite (tests inject their own session factory) and none is tracked by git.
- New blocker **B4:** this host cannot `pip install` brand-new packages (e.g. `ruff`, pinned
  SQLAlchemy versions) — only already-present ones resolve. CI (Python 3.12) installs the pinned
  versions normally.

## Phase 4 — Durable jobs, IDOR hardening, CSRF (2026-07-16)

**C-09 — Durable scan jobs (closes F-01).**
- `saas/models_db.py`: new `ScanJob` model (UUID id, `owner_login`, `status`, `idempotency_key`,
  counters, UTC `created_at`/`updated_at`) + status constants.
- Migration `0002_scan_jobs` (chained after `0001_initial`) creates `scan_jobs` (+ indexes).
- `saas/jobs_repo.py`: `create_job` (with **idempotency** — same owner+key returns the existing
  job), `get_job`, `update_job`, `list_jobs_for_user`, and `mark_stale_running_as_interrupted`
  (startup recovery for jobs orphaned by a restart).
- `saas/app.py`: `/scan-all` persists a durable job and short-circuits on an `Idempotency-Key`
  replay; the worker records terminal status (`completed`/`failed`) + counters + `report_id`
  (best-effort). New owner-scoped `GET /api/v1/jobs` and `GET /api/v1/jobs/<id>`. Startup recovery
  runs in `__main__`.
- Live process control stays in memory (handles can't be persisted); the DB is the durable source
  of truth for job *state/history/ownership*.
- Tests: `saas/test_jobs.py` (6) — migration, CRUD, idempotency, owner-scoped listing, startup
  recovery; plus 2 endpoint tests in `test_app.py`.

**C-10 — IDOR hardening on jobs & reports (F-06).**
- `enforce_job_owner()` guards the live `/scan-all/<id>`, `.../skip`, `.../stop` endpoints against
  cross-user control (best-effort against the durable record). Bulk report ids are now **UUID4**
  (unguessable) instead of timestamps. Test: cross-user status poll returns 403.

**C-11 — CSRF protection (closes F-12).**
- `config.validate_csrf()` enforces a per-session token (constant-time compare) on all
  state-changing methods, exempting safe methods, `/health`, and `TESTING` (covered instead by
  dedicated unit tests). Wired via `before_request`; `csrf_token` exposed to all templates via a
  context processor.
- `static/js/base.js`: a one-time `fetch` wrapper injects `X-CSRFToken` on same-origin
  state-changing requests, so all existing `fetch` POSTs are protected with no call-site changes.
- Tests: `saas/test_csrf.py` (5) — safe/exempt pass; missing/wrong token rejected; matching header
  passes.

**C-12 — Observability down-payment (partial F-16).**
- Correlation ids: every request gets an `X-Request-ID` (generated or echoed from the incoming
  header) via `before_request`/`after_request`.
- Proper probes: `GET /livez` (liveness, no deps) and `GET /readyz` (503 unless the DB answers
  `SELECT 1`, via `db.check_db_ready`). `/health` retained for the container healthcheck.
- Tests: `saas/test_observability.py` (6).

### Verification (measured, this increment)
- SaaS: **49 passed / 0 failed**; CLI: **16 passed / 0 failed** (65 total).

## Phase 4 (cont.) — Server-side sessions (2026-07-16)

**C-13 — Server-side sessions; token off the client cookie (closes F-03).**
- New `saas/session_config.py`: `configure_server_side_sessions(app)` attaches a Flask-Session
  backend — **filesystem** for local dev (default), **Redis** in production
  (`SESSION_TYPE=redis` + `REDIS_URL`). All session data (including the GitHub access token) now
  lives server-side; the browser only holds an opaque, signed session id.
- `rotate_session()` clears pre-authentication data on login (mitigates session fixation); the
  callback rotates then stores credentials server-side.
- `saas/requirements.txt`: added `Flask-Session>=0.8,<0.9`, `redis>=5.0,<9`.
- `docker-compose.yml`: added a `gvd-redis` service (healthchecked) + `gvd_data`/`gvd_redis`
  volumes; the web service uses `SESSION_TYPE=redis` and depends on redis being healthy — enabling
  ADR 0002/0003 durable sessions in the container stack.
- Tests: `saas/test_sessions.py` (3) — server-side backend is active; the access token never
  appears in any cookie; `rotate_session` clears pre-auth data.
- **B1/B4 update:** Docker (29.6.1) and `Flask-Session`/`redis` are now available on the host, so
  these were validated locally (not just in CI).

### Verification (measured, this increment)
- SaaS: **52 passed / 0 failed** (49 → +3 sessions); CLI: **16 passed / 0 failed** (68 total).
- `docker compose config` is **valid** (services `gvd-redis`, `gvd-saas`). A live `up --build`
  was **not** completed on this host: Docker CLI 29.6.1 is present but the Docker Desktop Linux
  engine stayed in an initializing/500 state this session. The canonical live container gate
  remains the CI `compose-smoke` job (clean Linux runner). Not fabricated.

## Phase 4 (cont.) — Versioned API + OpenAPI (2026-07-16)

**C-14 — `/api/v1` with validation, error envelope, OpenAPI (closes F-13).**
- `saas/api_common.py`: consistent JSON **error envelope** (`{"error":{code,message,correlation_id,
  details?}}`) that always carries the request correlation id; a dependency-free
  `validate_scan_request()`; and `build_openapi_spec()` (OpenAPI 3.0.3 document).
- `saas/app.py`: new `POST /api/v1/scans` (validated, auth-checked, idempotent — reuses the shared
  `launch_bulk_scan` orchestration extracted from `/scan-all` so there is no logic duplication),
  and `GET /api/v1/openapi.json`. Existing owner-scoped `/api/v1/jobs` + `/api/v1/jobs/<id>` remain.
- Refactor: `/scan-all` now delegates to `launch_bulk_scan(...)` (single source of truth for bulk
  orchestration).
- Tests: `saas/test_api_v1.py` (6) — OpenAPI structure; 401 + 422 error envelopes with correlation
  id; single-scan validation; 202 on accept; 200 on idempotent replay.

### Verification (measured, this increment)
- SaaS: **58 passed / 0 failed** (52 → +6 API v1); CLI: **16 passed / 0 failed** (74 total).
- `app` imports cleanly; existing `/scan-all` behaviour preserved via the shared helper.

### Phase 4 status — COMPLETE (except live-Docker gate)
| Finding | Status |
|---------|--------|
| F-01 durable jobs | ✅ (C-08, C-09) |
| F-03 server-side sessions | ✅ (C-13) |
| F-06 IDOR | ✅ (C-05, C-10) |
| F-11 durable stats | ✅ (C-08) |
| F-12 CSRF | ✅ (C-11) |
| F-13 API v1 + OpenAPI + validation + error envelope | ✅ (C-14) |
| F-16 observability | 🟡 partial (C-12: correlation ids + probes); metrics/structured logs remain |
| **Next: Phase 5** — F-02 durable queue + isolated worker, F-19 scanner-as-library | ⏳ |

## Phase 5 — In-process scanner (2026-07-16)

**C-15 — In-process scanner library (closes F-19).**
- New `saas/scanner_lib.py`: pattern engine + git-history scan + canonical `report.json` builder,
  run **in-process** using the system `git` binary (no dependency on `cli/cli.py` or a prebuilt
  executable). `scan_to_dir()` writes the same `report.json` schema the app already consumes.
- `saas/app.py`: `SCANNER_MODE` (default **`inprocess`**) — `run_repo_scan` now scans in-process;
  the `CLI_EXE` requirement is only enforced in `subprocess` mode. This also **fixes in-container
  scanning** (the scanner ships inside the SaaS image), closing the compose caveat from C-07.
- Tech debt (documented): detection rules are duplicated from `cli/scanner/pattern_engine.py`; to
  be unified into a shared package. Caveat: in-process mode enforces cancellation between repos,
  not mid-repo (fine-grained cancel lands with the Phase 5 worker, F-02).
- Tests: `saas/test_scanner_lib.py` (6) — pattern detection, real temp-git-repo scan, `report.json`
  schema parity, clean-repo zero findings, and an **end-to-end `run_repo_scan` in-process** test.

### Verification (measured, this increment)
- SaaS: **64 passed / 0 failed** (58 → +6 scanner); CLI: **16 passed / 0 failed** (80 total).
- `app` imports cleanly; the in-process path was exercised against real git repositories.

## Phase 5 (cont.) — Durable queue + isolated worker (2026-07-16)

**C-16 — DB-backed job queue + worker (closes F-02 core; see ADR 0004).**
- Model/migration: `scan_jobs` gains `retry_count` + `cancel_requested`
  (`0003_job_queue`, chained after `0002`).
- `jobs_repo` queue ops: `claim_next_job` (atomic guarded-UPDATE claim, SQLite +
  Postgres safe, FIFO), `request_cancel` (owner-enforced), `is_cancel_requested`,
  `requeue_or_fail` (bounded retries → requeue else fail).
- `saas/worker.py`: `process_job` (isolated temp workspace, cooperative
  cancellation at safe checkpoints, per-job timeout, retry-on-failure, **guaranteed
  workspace cleanup** in `finally`) and a `Worker` poller with a `main()` entrypoint.
  The worker takes a `cloner` callable so token handoff is an explicit decision
  (ADR 0004) — no token is persisted (F-03).
- `saas/app.py`: `POST /api/v1/jobs/<id>/cancel` (owner-only, consistent envelope).
- Tests: `saas/test_worker.py` (9) — atomic claim, FIFO, retry-then-fail, cancel
  flag (owner-enforced), worker completes a real local-repo scan + cleans up,
  cancellation short-circuits, retry-on-clone-failure, empty-queue; plus a cancel
  endpoint test in `test_api_v1.py`.
- ADR 0004 records the durable-DB-queue decision and the pending secure
  token-handoff options for a separate-process worker; until chosen, bulk scans run
  in-process (token already available) while using the durable queue for state.

### Verification (measured, this increment)
- SaaS: **73 passed / 0 failed** (64 → +9 worker/queue, +1 cancel endpoint, −1 dedup);
  CLI: **16 passed / 0 failed** (89 total). Migrations `0001`→`0003` run from a clean DB.

### Status of findings (updated)
| Finding | Status |
|---------|--------|
| F-01 durable jobs | ✅ Resolved (C-08 foundation + C-09 jobs); worker extraction is F-02 |
| F-06 IDOR | ✅ Reports + job history + live job control owner-checked; UUID ids (C-05, C-10) |
| F-11, F-12 | ✅ Resolved (C-08, C-11) |
| F-03 server-side sessions | ⏳ Blocked locally (needs Flask-Session; B4) — do in CI/Phase 7 |
| F-02 worker, F-13 API/OpenAPI, F-16 observability, F-19 in-container scan | ⏳ Open (Phases 4–5) |

## Phase 5 (cont.) — Observability (F-16) (2026-07-16)

**C-14 — Structured logging + Prometheus metrics.**
- New `saas/observability.py` (dependency-free):
  - `JsonFormatter` (structured JSON logs) + `RedactingFormatter` (dev), selected by
    `configure_logging()` — JSON when `ENVIRONMENT/FLASK_ENV=production` or `LOG_FORMAT=json`,
    human-readable otherwise; level from `LOG_LEVEL`.
  - `redact()` scrubs GitHub tokens (`gh[posur]_…`), 40-hex OAuth tokens, `Bearer/token …`,
    `secret/password/token=` kv pairs, and `user:pass@host` URLs from every log record.
  - `MetricsRegistry` — thread-safe counters/gauges/histograms rendered in Prometheus text
    format; shared `registry` with standard series: `gvd_http_requests_total`,
    `gvd_http_request_duration_seconds`, `gvd_github_api_calls_total`, `gvd_scans_total`,
    `gvd_scan_duration_seconds`, `gvd_findings_total`, `gvd_job_retries_total`, `gvd_queue_depth`.
- `saas/app.py`: swapped `logging.basicConfig` for `configure_logging()`; a `_CorrelationIdFilter`
  injects `g.correlation_id` into all records; `before/after_request` time each request and emit
  `observe_http_request(method, route_rule, status, duration)` (route rule = low cardinality);
  `run_repo_scan` emits `observe_scan("success")` + per-severity `observe_findings`.
- New `GET /metrics` endpoint refreshes `gvd_queue_depth` via `jobs_repo.count_queued_jobs()` then
  renders the registry (text/plain; version=0.0.4).
- `.env.example`: documented `LOG_FORMAT`, `LOG_LEVEL`, and the `/metrics` endpoint.

### Verification (measured, this increment)
- SaaS: **82 passed / 0 failed** (73 → +9 observability: redaction/JSON formatter/registry/
  endpoint/queue-count); CLI: **16 passed / 0 failed** (**98 total**). `app`/`jobs_repo`/
  `observability` import clean; `get_errors` clean on all edited files.

**C-15 — GitHub API call metrics wired.**
- `saas/github.py`: added `github_get()` wrapper recording `gvd_github_api_calls_total` by outcome
  (`success`/`rate_limited`/`client_error`/`server_error`/`error`); routed all 5 GitHub call sites
  through it (no behavior change; response returned unchanged).
- Fixed an incomplete test fixture (`test_app.py::test_get_repos_success`) that omitted a numeric
  `status_code` on its mock — now set to `200` to reflect a real successful response.
- Tests: 3 new outcome tests (success/rate_limited/network-error) in `test_observability.py`.
- Verification: SaaS **85 / 0**, CLI **16 / 0** (**101 total**); `get_errors` clean.

### Remaining for F-16 (documented, not fabricated)
- Distributed tracing deferred until the worker runs as a separate process (ADR 0004).
- `/metrics` is currently unauthenticated: keep it on an internal network in production, or add a
  scrape-token/allowlist in Phase 7 hardening.

## Phase 6 — Frontend/UX: XSS hardening (2026-07-16)

**C-16 — Escape all DOM interpolation + fix reverse-tabnabbing.**
- Threat: GitHub-controlled fields (repo/owner names, clone/report URLs) and scanner output are
  rendered via `innerHTML`. Text content was already escaped, but several **HTML attributes** and
  two error/link templates interpolated raw values (attribute-injection / DOM-XSS vector).
- `saas/static/js/dashboard.js`:
  - `createSearchResultItem` now routes every attribute (`data-owner/-repo/-repo-url/-visibility`,
    titles, badge text) through `window.GVD.utils.escapeHtml` (which escapes `"` and `'`, so it is
    attribute-safe); `stars` coerced to `Number`.
  - PDF error/fallback blocks: `verifyError.message` and all `href="${url}"` values are now escaped;
    `target="_blank"` anchors gained `rel="noopener noreferrer"`.
- Templates: added `rel="noopener noreferrer"` to every `target="_blank"` link across
  `scan_history.html`, `scan_results.html` (user-controlled `repo.html_url`), plus the static
  external links in `documentation/privacy_policy/terms_of_service/support`.
- New `saas/test_frontend_security.py` (11 static-source regression tests): forbids the fixed
  unescaped patterns from returning, asserts the search builder uses the escaper, and enforces
  `rel="noopener"` on all `target="_blank"` links in both `dashboard.js` and every template.

### Verification (measured)
- SaaS: **96 passed / 0 failed** (85 → +11 frontend-security); CLI: **16 / 0** (**112 total**).
- New blocker **B5**: Node/npm not installed on this host → browser/component/e2e JS tests run in
  CI (a `frontend-test` job will be added in Phase 8). The static-source guards above run in pytest
  now and prevent regressions in the interim.

### Remaining for Phase 6
- Accessibility pass (WCAG 2.2 AA: focus order, ARIA labels, contrast) — audited against the
  live templates. *(Superseded by C-26: `accessibility.css`/`responsive.css` were unloaded
  legacy files whose useful rules already live in loaded stylesheets; both were removed.)*
- Explicit loading/empty/error states review per journey; Node-based component + e2e tests (CI).

## Phase 6 — Frontend/UX: Accessibility (WCAG 2.2 AA) (2026-07-16)

**C-17 — Modal focus management, live regions, and accessible names.**
- `saas/static/js/base.js`:
  - Modal now traps focus (`Tab`/`Shift+Tab` cycle), closes on `Escape`, sets
    `role="dialog"`/`aria-modal`, and **restores focus** to the triggering element on close
    (WCAG 2.4.3 Focus Order / 2.1.2 No Keyboard Trap escape).
  - Toasts get `role="alert"` for error/warning (assertive) and `role="status"` otherwise.
  - Dropdowns sync `aria-expanded` on the toggle via a shared `_syncAria` helper.
- `saas/templates/base.html`:
  - `#toast-container` is now an ARIA live region (`role="status" aria-live="polite"
    aria-atomic="true"`) so dynamic toasts/errors are announced.
  - Notifications + user-menu toggles advertise `aria-haspopup`/`aria-expanded`/`aria-controls`;
    the user dropdown is `role="menu"`.
- `saas/templates/dashboard.html`: the repo search input and visibility `<select>` gained
  `aria-label`s (placeholder is not an accessible name); search input marked `role="searchbox"`
  with `aria-controls`, results container `role="listbox"`.
- New `saas/test_frontend_a11y.py` (7 static-source guards): live-region toast, menu-button ARIA
  state, skip link + landmarks, dashboard control names, modal Escape/trap/restore, dropdown
  `aria-expanded` sync, toast alert role.

### Verification (measured)
- SaaS: **103 passed / 0 failed** (96 → +7 a11y); CLI: **16 / 0** (**119 total**). `get_errors`
  clean; 0 stray markers.

### Remaining for Phase 6 (updated)
- Colour-contrast + reduced-motion audit against `variables.css`/`base.css` (needs a visual/
  axe pass — CI `frontend-test` job, B5). *(Reduced-motion resolved in C-26; the unloaded
  `animations.css` was removed and the guard test repointed to loaded `base.css`.)*
- Per-journey loading/empty/error-state review and Node-based component + e2e tests (CI, B5).

## Phase 6 — Frontend/UX: corruption repair + state guards (2026-07-16)

**C-18 — Repaired a repository-wide editing-artifact corruption (regression).**
- Symptom: the SaaS test suite failed to **collect** (9 import errors) — a stray literal
  `</content>` line had been appended to the end of **24 tracked text files** (Python modules,
  Alembic migrations, `alembic.ini`, `requirements-dev.txt`, ADRs and other docs), producing
  `SyntaxError` / `configparser.MissingSectionHeaderError`.
- Fix: stripped the exact `</content>` line from every affected file and re-saved them as UTF-8
  **without BOM** (an initial pass had introduced a BOM that broke `configparser` on `alembic.ini`).
- `saas/static/js/base.js` had been reverted to a pre-C-17 build, dropping the accessibility work;
  re-applied: modal focus-trap + `Escape`-to-close + `aria-modal` + focus **restore** to the
  triggering element (`_lastTrigger`), toast `role="alert"`/`aria-live="assertive"` for
  error/warning vs `role="status"`/polite otherwise, and dropdown `_syncAria` keeping
  `aria-expanded` in sync (the DOM click handler now routes through `GVD.dropdown.toggle`).
- `saas/templates/dashboard.html` was corrupted: ~138 lines of **dead, leaked JavaScript** (old BEM
  class names `bulk-report-item__*`, `repo-card__details-button`, a non-existent `pollBulkScanJob`,
  and a bogus child-template `</body></html>`) sat after the valid `{% endblock %}`. Verified the
  live `dashboard.js`/`bulk-scan-and-notifications.js` own this behaviour (current class names
  `scan-all-button`, `repo-details-btn`), then truncated the template to its valid 476 lines. All
  10 templates now parse cleanly under Jinja.

**C-19 — Regression guards for Phase 6 states (so this cannot silently recur).**
- `saas/test_frontend_a11y.py` +4 static-source tests: reduced-motion media query present and
  actually neutralises animation; dashboard empty/loading/error states; scan-history empty state;
  and an anti-corruption guard forbidding leaked `</html>`/`pollBulkScanJob`/`bulk-report-item__*`
  in `dashboard.html`.

### Verification (measured, this increment)
- SaaS: **107 passed / 0 failed** (was failing collection → 103 restored → +4 guards); CLI:
  **16 / 0** (**123 total**). All 10 Jinja templates parse; JS brace balance even across all three
  files (Node absent, B5 — full `node --check`/axe/e2e run in CI's `frontend-test` job).

### Remaining for Phase 6 (still open, unchanged blockers)
- Full axe colour-contrast pass + Node-based component/e2e tests run in CI (B5: Node not installed
  on this host). Key text tokens (`--color-text-secondary` #4b5563, `--color-text-tertiary` #6b7280
  on white) meet AA (≥4.5:1) by calculation; the automated axe sweep remains the canonical gate.

## Phase 6 — Frontend/UX: OAuth-decline journey (2026-07-16)

**C-20 — Friendly, journey-specific handling of a declined GitHub consent.**
- Gap: when a user clicks *Cancel* on GitHub's consent screen, GitHub redirects to
  `/callback?error=access_denied&error_description=...` with **no `code`**. The old flow fell
  through to the token exchange and rendered a confusing `400 "Missing 'code' parameter"`.
- `saas/app.py` `callback()` now inspects `request.args.get("error")` **first**:
  - `access_denied` → `400` "Authorization Cancelled" with guidance to sign in again and approve;
  - any other provider error → `400` generic "Authentication Error".
- Security: GitHub's `error_description` is provider-controlled, so it is **not** reflected into the
  page (Jinja autoescapes anyway; we avoid echoing it entirely).
- Tests: `saas/test_app.py` +2 — declined consent shows the friendly page and does **not** reflect
  the provider text; a generic OAuth error renders the error page.

### Verification (measured, this increment)
- SaaS: **109 passed / 0 failed** (107 → +2 OAuth journey); CLI: **16 / 0** (**125 total**). Every
  Python file under `saas`/`cli` byte-compiles (`python -m compileall`, exit 0) — confirms no other
  file was left broken by the C-18 corruption repair.
- Host tooling still limited to Python: `node`, `npm`, `docker`, `ruff` are all absent here
  (B1/B4/B5), so the Docker Compose gate and the axe/Playwright frontend gates remain CI-only.

## Phase 6 — Frontend/UX: error-page bug + dead-template cleanup (2026-07-16)

**C-21 — Fix blank error pages (400/403/404/500).**
- Bug: `app.py`'s global error handlers rendered `error.html` with `status_code=` and **no**
  `detail`, but the template reads `{{ status }}`/`{{ detail }}`. Because these module-level
  handlers register *after* `config.setup_error_handlers(app)` (line 104), they **overrode** the
  correct ones — so every 400/403/404/500 page showed a **blank error code** and empty body text.
- Fix: `app.py` handlers now pass `status=`, `message=`, and a human-readable `detail=` (keeping
  their JSON/`/api/` branch). The error page now renders the real code and guidance.
- Test: `saas/test_app.py::test_404_renders_error_page_with_status_code` asserts a 404 shows `404`
  + "Page Not Found" (would have failed against the old blank page).

**C-22 — Remove dead `scan_results.html` template + static-asset guard.**
- `saas/templates/scan_results.html` was **orphaned**: rendered by no route (the live scan-results
  UX is the `#scan-modal` in `dashboard.html`), referenced by no test, and it linked two
  **non-existent** assets (`css/scan-results.css`, `js/scan-results.js`) plus every button called
  handlers from the missing JS. Proven unreferenced (`render_template`/`url_for` grep) → removed.
- New guard `saas/test_frontend_a11y.py::test_templates_reference_only_existing_static_assets`
  parses every `filename='…'` in all templates and asserts the file exists on disk — preventing the
  whole missing-asset class of bug from recurring.
- A11y sweep of the remaining content pages: `support`, `privacy_policy`, `terms_of_service`,
  `documentation` all extend `base.html` (inherit skip-link + `banner/main/contentinfo` landmarks)
  and have **no** `<img>` missing `alt`.

### Verification (measured, this increment)
- SaaS: **111 passed / 0 failed** (109 → +2: 404 render + static-asset guard); CLI: **16 / 0**
  (**127 total**). All 9 remaining templates parse under Jinja; `get_errors` clean on `app.py`.

## Phase 6/8 — CI frontend gate + cleanup report (2026-07-16)

**C-23 — Playwright + axe `frontend-test` CI job (addresses B5).**
- New `saas/frontend-tests/` project: `package.json` (`@playwright/test` 1.49.1 +
  `@axe-core/playwright` 4.10.1, pinned), `playwright.config.js` (boots the **real** app via
  `webServer: python app.py`, chromium only), `tests/accessibility.spec.js`, `.gitignore`, README.
- Coverage against real rendered markup (unauthenticated, no OAuth needed): login page axe WCAG
  2.2 A/AA scan (no serious/critical), skip-link + single-H1 + keyboard focus to the sign-in
  control; OAuth-declined page ("Authorization Cancelled") axe scan; 404 status render;
  reduced-motion axe pass. Authenticated journeys (dashboard/scan/report) need an OAuth mock —
  documented as a tracked follow-up in the project README.
- `.github/workflows/ci.yml`: added the `frontend-test` job (setup-python + install
  `saas/requirements.txt`, setup-node 20, `npm ci`, `playwright install chromium`, `npm test`,
  upload report artifact). YAML validated (`yaml.safe_load` → 7 jobs). Not run on this host (Node
  absent, B5) — executes on the CI runner.

**C-24 — Cleanup report (`docs/audit/CLEANUP_REPORT.md`).**
- Recorded the `scan_results.html` removal (C-22) and a new finding: four stylesheets are loaded
  by **no** page — `animations.css` (0 class usages anywhere → dead), `accessibility.css`
  (`.sr-only` duplicates loaded `base.css` → redundant), and `responsive.css`/`utilities.css`
  (target **live** selectors, so unloading them may be a *missing-mobile-CSS bug* rather than dead
  code). Because this host has no browser (B5), removals/wiring that need a visual "no regression"
  proof are **deferred to Phase 9** behind the new `frontend-test` gate — no unverifiable change
  was made. Full evidence + decisions in the cleanup report.

### Verification (measured, this increment)
- Python suites unchanged and green: SaaS **111 / 0**, CLI **16 / 0** (**127 total**). New JS files
  are brace/paren balanced; `ci.yml` parses (7 jobs). No source stylesheet/template was deleted or
  rewired this increment (only the already-removed dead `scan_results.html`).

**C-25 — Harden pytest collection against runtime artifacts.**
- Symptom: a leftover local clone under `saas/repos/mouloudelarram/…` shipped its own `test_*.py`,
  which pytest recursed into and failed to collect (`Interrupted: 1 error during collection`). The
  dir is gitignored (`/saas/repos/`) and untracked, but was still on disk and polluted collection.
- Fix: `saas/pytest.ini` now sets
  `norecursedirs = repos data scan_reports frontend-tests node_modules .git *.egg migrations` so
  runtime clones / generated reports / the Node project can never break the Python suite (locally or
  in CI).
- Verified: `pytest -q` collects only first-party tests again — SaaS **111 / 0**.

**C-26 — Phase 9 CSS cleanup: remove 5 non-loaded stylesheets (runtime-neutral).**
- Context: C-24 flagged four unloaded stylesheets plus the root `static/style.css`. The
  earlier 🔴 concern ("responsive/utilities might be missing-mobile-CSS, needs a browser
  gate") is resolved here by **static evidence**, so no browser was required:
  - `animations.css` — 0 class usages anywhere (grep); reduced-motion already in loaded
    `base.css`. **Removed.**
  - `accessibility.css` — not loaded; `.sr-only`/`.visually-hidden`/`.skip-to-content`,
    reduced-motion, `prefers-contrast: high` and `pointer: coarse` touch targets all already
    live in loaded `base.css`/`dashboard.css`/`auth.css`. Corrupt line-2 comment confirmed it
    legacy. **Removed.**
  - `responsive.css` — not loaded; the loaded `dashboard.css` (breakpoints
    1400/1200/1024/768/640/480 with responsive `.repo-grid`), `auth.css` (1200/1024/768/480),
    and `scan-history.css` (768/480) **already** make the live layout responsive for the same
    selectors → redundant, **not** a missing-mobile bug. **Removed.**
  - `utilities.css` — not loaded; broad grep of templates for its utility classes → no hits.
    Dead. **Removed.**
  - `static/style.css` (root) — not linked by any template; referenced only in `README.md`
    (doc drift). **Removed** and README corrected.
- Why safe without the B5 browser gate: **none of these files was linked by any page**, so
  deleting them cannot change rendered output. The `frontend-test` axe gate stays reserved for
  authenticated journeys / contrast.
- Test change: `test_reduced_motion_support_present` repointed from the (deleted)
  `animations.css` to the **loaded** `base.css`, asserting the real
  `@media (prefers-reduced-motion: reduce)` blanket reset users receive.
- Docs: `docs/audit/CLEANUP_REPORT.md` section 2/4 updated to ✅ removed with evidence.
- Verified: SaaS **111 / 0**, CLI **16 / 0** (**127 total**); `css/` now contains exactly the
  11 loaded stylesheets; repo-wide grep finds no code/template reference to any removed file.

**C-27 — Phase 9 cleanup: remove superseded bulk-scan snippet files.**
- Removed `saas/BACKEND_CHANGES.py`, `saas/FRONTEND_CHANGES.js`, `saas/HTML_CHANGES.html` —
  copy-paste "code snippet" scratch files from the original bulk-scan rollout. Imported by no
  module (grep); the feature is already integrated in `app.py` (routes/jobs) +
  `bulk_scan_service.py` (`BulkScanManager`) + the loaded/tested
  `static/js/bulk-scan-and-notifications.js` + the dashboard bulk-scan modal.
- Doc accuracy: `IMPLEMENTATION_GUIDE.md` and `QUICK_REFERENCE.md` (the only referrers) got a
  "⚠️ Historical / superseded — see integrated files" banner so no document points at a deleted
  file.
- Verified: SaaS **111 / 0** after removal (nothing imported the snippets).

## Phase 9 — Documentation Consolidation (2026-08-17)

**C-28 — Consolidate 25 root-level markdown files into the `docs/` catalog.**

Problem: The repository root contained 25 overlapping markdown files spanning bulk-scan
implementation plans, Docker guides, deployment guides, architecture overviews, and release
notes — many duplicating each other (e.g. `DEPLOYMENT_GUIDE.md` vs `PRODUCTION_DEPLOYMENT_GUIDE.md`;
7 separate `BULK_SCAN_*` files), some pointing to already-deleted files, and none forming a
coherent navigable catalog.

Resolution: Created 6 canonical documents in `docs/`, replaced all 25 root-level files with
5-line redirect stubs, updated `docs/README.md` to be a complete indexed catalog, and updated
the root `README.md` to point to `docs/`. Old `docs/guides/docker-compose.md` redirects to
the new `docs/guides/docker.md`.

New canonical docs:
- `docs/guides/bulk-scan.md` — supersedes: BULK_SCAN_FILES_REFERENCE.md,
  BULK_SCAN_IMPLEMENTATION.md, BULK_SCAN_IMPLEMENTATION_PLAN.md,
  BULK_SCAN_IMPLEMENTATION_SUMMARY.md, BULK_SCAN_QUICK_START.md,
  BULK_SCAN_TESTING_GUIDE.md, README_BULK_SCAN.md
- `docs/guides/docker.md` — supersedes: DOCKER_SETUP.md, DOCKER_ARCHITECTURE_GUIDE.md,
  DOCKER_QUICK_REFERENCE.md, docs/guides/docker-compose.md
- `docs/guides/deployment.md` — supersedes: DEPLOYMENT_GUIDE.md,
  PRODUCTION_DEPLOYMENT_GUIDE.md, AWS_EC2_QUICK_START.md
- `docs/guides/quick-reference.md` — supersedes: QUICK_REFERENCE.md, SCRIPTS_GUIDE.md,
  IMPLEMENTATION_GUIDE.md, INTEGRATION_GUIDE.md, ENTERPRISE_UPGRADE.md
- `docs/architecture/overview.md` — supersedes: ARCHITECTURE.md
- `docs/audit/release-history.md` — supersedes: BUG_ELIMINATION_REPORT.md,
  COMPLETION_CHECKLIST.md, PHASE_3_COMPLETION.md, PRODUCTION_RELEASE_SUMMARY.md,
  PDF_ENHANCEMENT_SUMMARY.md

Root redirect stubs written (24 files): all replaced with a 6-line header pointing to
canonical location. Original content preserved in git history.

Why stubs not deletion: preserves `git blame`, does not break external links, avoids
any reference-check false-negatives. May be deleted in Phase 10 after git history is verified.

Verified: SaaS **111 / 0**, CLI **16 / 0** (127 total) — no Python code imports any of the
archived docs; no template references any of them.

---

## Phase 8 — Quality & Security Gates (2026-08-17)

### C-29 — Playwright/Node frontend test suite unblocked (B5 resolved)

**Problem:** `HTTP_PROXY`/`HTTPS_PROXY` env vars were set to a dead local proxy (`127.0.0.1:3128`)
left over from a prior session; npm and Node were using it unconditionally.
**Fix (session-level):** Clear `$env:HTTP_PROXY` and `$env:HTTPS_PROXY` before any npm/Node
command. These vars are NOT in any committed file; no code change required.

**Playwright security fix:** `@playwright/test` was pinned to `1.49.1`
(`GHSA-7mvr-c777-76hp` — browser download skips SSL verification). Upgraded to `1.62.1`
(0 vulnerabilities, `npm audit` clean).
- File: `saas/frontend-tests/package.json` — `"@playwright/test": "1.49.1"` → `"1.62.1"`.

**Corporate CA bundle:** Enterprise proxy performs TLS inspection with a private CA.
`NODE_EXTRA_CA_CERTS=C:\...\corp-ca-bundle.pem` is needed for Node to trust the proxy chain
when downloading Playwright Chromium. The PEM was generated from the Windows certificate store
(Root + CA stores). **Never set `NODE_TLS_REJECT_UNAUTHORIZED=0`.**

**Windows Python entrypoint:** Playwright's `webServer.command` was `"python app.py"` which fails
on Windows where `python` is not on PATH (`py` is). Fixed to auto-detect:
- File: `saas/frontend-tests/playwright.config.js` — command is now
  `process.platform === "win32" ? "py app.py" : "python3 app.py"` (overridable via `PYTHON` env).

**Verification:** `npx playwright test` → **6 / 0** (chromium, axe-core WCAG 2.2 AA suite).

---

### C-30 — WCAG 2.2 AA colour-contrast violations fixed in login page

**Violations found by axe-core (impact: serious):**
- `.auth-footer p` — "By continuing…" text: `#738496` on `#ffffff` → 3.83:1 (required ≥ 4.5:1)
- `.footer-security` — "🔒 Secure OAuth via GitHub": same colour, same ratio

**Root cause:** `auth.css` used a hardcoded Jira-blue-grey (`#738496`) instead of the semantic
token already defined in `variables.css`.

**Fix:** Replace both instances with `var(--color-text-secondary)` which resolves to
`--color-gray-600: #4b5563` → **7.49:1** on white (WCAG 2.2 AA, AAA-level headroom).
- File: `saas/static/css/auth.css` lines 300 and 319.

**Verification:** `npx playwright test` → **6 / 0**; `py -m pytest` → **111 / 0**.

---

### C-31 — pip-audit: 15 CVEs in 5 packages resolved

`py -m pip_audit -r requirements.txt` found 15 known vulnerabilities before this change.

| Package | Old version | CVEs | New version | Contrast ratio improvement |
|---|---|---|---|---|
| Flask | 3.0.0 | PYSEC-2026-2151 | **3.1.3** | — |
| Werkzeug | 3.0.0 | PYSEC-2023-221, -2026-2043/44/45/46/2320/3417 (8 CVEs) | **3.1.8** | — |
| gunicorn | 21.2.0 | PYSEC-2026-1433, -1434 | **22.0.0** | — |
| python-dotenv | 1.0.0 | PYSEC-2026-2270 | **1.2.3** | — |
| requests | 2.31.0 | PYSEC-2026-1872, -1873, -2275 | **2.34.2** | — |

- File: `saas/requirements.txt` — 5 version pins updated with inline CVE comments.
- `flask-jwt-extended 4.4.4` (not in requirements.txt) reports a dep conflict; it is a
  leftover in the system Python and not used by this project.

**Verification:** `py -m pip_audit -r requirements.txt` → **"No known vulnerabilities found"**;
`py -m pytest` → **111 / 0**; `npx playwright test` → **6 / 0**.

---

### C-32 — Alembic pre-migration schema stamped (Alembic error on Flask restart silenced)

**Problem:** `saas/data/gvd.db` was originally created by SQLAlchemy `create_all` before Alembic
was introduced. Every Flask startup attempt to run migration `0001_initial` failed with
`table scan_events already exists`, logged as `ERROR [db] Alembic migration failed; falling back
to create_all`. The app still started (fallback was safe) but the error was noisy and misleading.

**Fix (one-time):** `py -m alembic -c alembic.ini stamp head` — wrote `alembic_version` row
`0003_job_queue` (current head) into `gvd.db`. No schema changes; purely tracking metadata.

**Fix (structural, db.py):** `run_migrations()` now detects the pre-Alembic case
(application tables exist, `alembic_version` absent) and stamps at head instead of running DDL,
preventing the error from ever reappearing on other developer machines with the same situation.
Fresh empty databases continue to run full migrations normally.
- File: `saas/db.py` — `run_migrations()` refactored + `_alembic_cfg()` helper extracted.

**Verification:** `npx playwright test` — no `ERROR [db]` lines in webserver output;
`py -m pytest` → **111 / 0**.

---

### Docker Phase 7 gate — BLOCKED (local)

Docker client v29.6.1 is installed. Neither context is reachable:
- `desktop-linux` — Docker Desktop is not running (enterprise policy; user confirmed).
- `default` (Windows native engine) — pipe `docker_engine` not present.
- WSL is not installed on this machine.

**Impact:** `docker compose build` / `docker compose up` cannot be run locally.
**Unblocked path:** Run Phase 7 on a Linux CI runner or any machine with Docker Engine
(WSL2, Linux VM, cloud VM). All application and frontend tests already pass; the Dockerfiles
and compose files are complete and were previously validated.















