# GVD â€” Phase 1 Audit Report

Status: **Discovery complete.** This report is evidence-based; every finding cites a file and,
where possible, a line and a reproduction. See `BASELINE.md` for measured build/test state.

Severity scale: **Critical** (exploitable now / data loss), **High**, **Medium**, **Low**.
Complexity: S (hours), M (1â€“3 days), L (>3 days).

---

## Executive summary

GVD is a working Flask monolith + a Python CLI scanner. Core journeys (GitHub OAuth, repo
listing, clone, single/bulk scan, report download) are implemented and largely functional.
However, it is **not production-grade** in its current form. The dominant risks are:

1. **All operational state is in process memory** (`BULK_SCAN_JOBS`, `SESSION_SCAN_RESULTS`,
   `SESSION_NOTIFICATIONS`, `SCAN_STATISTICS`). A restart or a second Gunicorn worker loses jobs,
   breaks progress polling, and corrupts statistics. This is the single biggest blocker to the
   stated goal of a "portable, observable, service-oriented application."
2. **The GitHub access token is stored in a client-side signed cookie** (Flask default session),
   readable by the client and replayable if the cookie leaks.
3. **Clone-URL host validation is a substring check** (`"github.com" in url.lower()`), which is
   bypassable, and the **token is embedded in the `git clone` argv**, exposing it to process
   listings.
4. **The test baseline is red** and the toolchain is unpinned/inconsistent (dual import paths,
   `pytest-flask` incompatible with Flask 3).
5. **Heavy documentation drift**: ~30 top-level Markdown files with overlapping/contradictory
   "production ready" claims and no single source of truth.

None of these require a big-bang rewrite. They map cleanly onto the phased plan in
`../architecture/TARGET_ARCHITECTURE.md` (modular monolith first, extract workers later).

---

## Prioritized findings

### Critical

#### F-01 â€” Durable state is process-local (data loss + multi-worker incorrectness)
- **Evidence:** `saas/app.py:97-99,143,265-266` (`SESSION_SCAN_RESULTS`, `SESSION_NOTIFICATIONS`,
  `SCAN_STATISTICS`, `BULK_SCAN_JOBS` are module-level dicts); `saas/bulk_scan_service.py`
  `BulkScanManager.__init__` keeps `self.sessions` in memory.
- **Impact:** Any process restart, deploy, or crash loses all in-flight and completed job state.
  With `GUNICORN_WORKERS=4` (see `.env.production`), a progress poll can hit a worker that never
  saw the job â†’ intermittent 404s and wrong statistics. Violates "durable scan state rather than
  process-local dictionaries."
- **Resolution:** Introduce a persistence layer (SQLite for dev / Postgres for prod via
  SQLAlchemy + Alembic). Move jobs, findings, reports, notifications, audit events to tables.
  Move async work to a durable queue/worker (see F-02).
- **Complexity:** L.

#### F-02 â€” Long-running clone + scan run inside request threads
- **Evidence:** `saas/app.py:1233-1238` starts a `threading.Thread(run_bulk_scan_job, daemon=True)`;
  `execute_scan_command` (`app.py:562`) and `ensure_repo_cloned` (`clone.py:131`) block up to
  300s each inside that thread within the web process.
- **Impact:** Not restart-safe; no retry/idempotency/dead-letter; a graceful shutdown kills jobs;
  `daemon=True` threads are terminated abruptly. Violates "Do not perform long-running clone or
  scan operations inside synchronous web requests" and the durability requirement.
- **Resolution:** Extract a **scanner worker** consuming from a queue (RQ/Redis or Celery), with
  idempotent job creation, bounded retries (exponential backoff + jitter), per-job timeout,
  cancellation via a control flag/record, and workspace cleanup.
- **Complexity:** L.

#### F-03 â€” GitHub access token stored in client-side signed cookie
- **Evidence:** `saas/app.py:316` `session["access_token"] = token`; Flask default session is a
  **signed but not encrypted** cookie. `app.config` (app.py:71-79) does not configure a
  server-side session backend.
- **Impact:** The OAuth token (scope `repo read:user`) is transmitted to and stored in the
  browser; anyone able to read the cookie (XSS residual, shared machine, cookie theft) obtains a
  token with private-repo access. Violates "Never expose access tokens" / weak session handling.
- **Resolution:** Server-side sessions (Flask-Session on Redis) storing only a session id in the
  cookie; store the token server-side, encrypted at rest; rotate session id after login; add
  idle+absolute session timeout.
- **Complexity:** M.

### High

#### F-04 â€” Clone-URL host validation is a bypassable substring check
- **Evidence:** `saas/clone.py:40` `if "github.com" not in clone_url.lower()`.
- **Impact:** `https://github.com.attacker.tld/x.git` and `https://attacker.tld/?github.com`
  pass. Combined with token embedding (F-05), a malicious `clone_url` could exfiltrate the token
  to an attacker host. Violates "Restrict clone URLs to approved GitHub hosts using parsed
  hostnames."
- **Resolution:** Parse with `urllib.parse.urlsplit`, require `scheme == "https"` and
  `hostname in {"github.com","www.github.com", <configured GHE host>}` (exact match). Reject
  userinfo in the input URL.
- **Complexity:** S.

#### F-05 â€” OAuth token embedded in `git clone` argv (process-listing exposure)
- **Evidence:** `saas/clone.py:43` builds `https://x-access-token:<token>@github.com/...` and
  passes it as an argument at `clone.py:79,132`.
- **Impact:** Token visible in `ps`/Task Manager and potentially in child-process env dumps or
  crash logs. Violates "Avoid credentials in command arguments where possible."
- **Resolution:** Use `GIT_ASKPASS`/credential helper or
  `git -c http.extraHeader="Authorization: Basic <b64>"` fed via stdin/env, keeping the token out
  of argv. Keep existing `.replace(token, "[redacted]")` redaction as defense in depth.
- **Complexity:** M.

#### F-06 â€” No per-resource authorization (IDOR) on reports/jobs
- **Evidence:** `saas/app.py:1364` `/download-report/<id>` and `app.py:1383` `/repo-report/...`
  and `app.py:1260` `/scan-all/<job_id>` only check `session.get("access_token")` truthiness; any
  logged-in user can read any other user's report or job by guessing the timestamp-based id.
  Report ids are `datetime.strftime("%Y%m%d%H%M%S")` (`app.py:881`) â€” **guessable**.
- **Impact:** Cross-tenant data disclosure of scan findings (which contain secrets). Violates
  "Enforce authorization on every report/job resource; prevent IDOR; reports remain private."
- **Resolution:** Persist `owner_user_id` on jobs/reports; check ownership on every read/download;
  use unguessable ids (UUID4).
- **Complexity:** M.

#### F-07 â€” `sanitize_path_component` is weaker than its tests assert
- **Evidence:** `saas/clone.py:14-27` strips `..` and `~` then regex-replaces other chars with `_`
  (never raising for e.g. `../../etc`). `saas/test_app.py::test_sanitize_path_component` expects a
  `ValueError` and fails ("DID NOT RAISE").
- **Impact:** Silent normalization can collide distinct names; the security intent is unclear and
  untested. Path traversal is *mostly* contained because components are re-joined under
  `REPOS_DIR`, but the contract is ambiguous.
- **Resolution:** Decide the contract (reject vs. normalize), then align implementation **and**
  test. Prefer allow-list validation that rejects invalid input explicitly.
- **Complexity:** S.

#### F-08 â€” `build_clone_url` accepts non-GitHub HTTPS URLs the test rejects
- **Evidence:** `saas/clone.py:30-43`; `saas/test_app.py::test_build_clone_url` expects a raise
  that does not happen ("DID NOT RAISE"). Same class as F-04.
- **Resolution:** Fold into F-04's parsed-hostname validation; then unskip/fix the test.
- **Complexity:** S.

#### F-09 â€” CLI dual import path breaks enum identity (test-visible correctness smell)
- **Evidence:** `cli/scanner/pattern_engine.py:3-6`, `cli/report/builder.py:5-7`, `cli/cli.py:11-30`
  all use `try: from cli.X import ... except ImportError: from X import ...`. Under pytest both
  `cli.core.models` and `core.models` load â†’ two `Severity` enums â†’ `==` fails (see BASELINE F-09).
- **Impact:** Fragile packaging; identity comparisons silently break depending on entrypoint;
  4 CLI tests red. Any future code comparing enum members across the boundary is unsafe.
- **Resolution:** Standardize on a single absolute import root (make `cli` the package, run via
  `python -m cli.cli`), add `pyproject`/`__main__`, drop the `try/except` fallbacks, add a
  `conftest.py` fixing `sys.path`. Then the 4 pattern tests pass unchanged.
- **Complexity:** M.

#### F-10 â€” Broken/duplicated business logic for bulk scan (two managers)
- **Evidence:** `saas/app.py` implements bulk scan via `BULK_SCAN_JOBS` + `/scan-all`, while
  `saas/bulk_scan_service.py` implements a **second**, unrelated `BulkScanManager` used by
  `/api/bulk-scan/*` (`app.py:1653-1732`). The API path reads `session.get("github_token")`
  (app.py:1669) but login stores `session["access_token"]` (app.py:316) â†’ the API bulk scan can
  never authenticate.
- **Impact:** Dead/contradictory code path; the `/api/bulk-scan/start` endpoint is broken by a key
  mismatch; maintenance hazard and confusion.
- **Resolution:** Choose one orchestration path (the durable one from F-02), delete the other
  after confirming no template/JS references (see Cleanup phase), fix the session-key mismatch.
- **Complexity:** M.

### Medium

#### F-11 â€” Statistics are global, not per-user, and non-durable
- **Evidence:** `saas/app.py:143` `SCAN_STATISTICS` keyed only by date; `session_stats` (app.py:1621)
  returns global counts to every user.
- **Impact:** Information leak (activity volume) across users + lost on restart.
- **Resolution:** Derive stats from the DB filtered by `owner_user_id`.
- **Complexity:** S.

#### F-12 â€” No CSRF token enforced on state-changing JSON endpoints
- **Evidence:** `config.generate_csrf_token` runs in `before_request` (app.py:85-88) and a token is
  passed to templates, but POST routes (`/scan`, `/scan-all`, `/clone`, `/api/*`) never **verify**
  it. `SameSite=Lax` is the only mitigation.
- **Impact:** CSRF on state-changing browser requests (Lax blocks cross-site top-level POST but not
  all vectors). Violates "Add CSRF protection to state-changing browser requests."
- **Resolution:** Enforce CSRF (Flask-WTF or explicit token check) on browser POSTs; exempt pure
  API+bearer paths once an API auth scheme exists.
- **Complexity:** M.

#### F-13 â€” No API versioning, schema validation, OpenAPI, or consistent error envelope
- **Evidence:** Routes return ad-hoc `jsonify({"error": ...})` shapes with varying keys
  (`error`, `details`) across `app.py`. No `/api/v1`, no request schema validation, no OpenAPI.
- **Resolution:** Introduce `/api/v1`, pydantic (or marshmallow) request/response models, a single
  error envelope with correlation id, and generated OpenAPI 3.
- **Complexity:** L.

#### F-14 â€” Homegrown PDF writer instead of the CLI's reportlab builder
- **Evidence:** `saas/app.py:757-895` hand-builds PDF bytes; `cli/report/pdf_builder.py` already
  uses `reportlab`. Two report renderers â†’ drift.
- **Resolution:** Single canonical report model + one renderer (reuse CLI's) in a reporting module.
- **Complexity:** M.

#### F-15 â€” CLI dependencies unpinned
- **Evidence:** `cli/pyproject.toml` `dependencies = ["rich>=13.0.0","reportlab>=4.0.0","python-dateutil>=2.8.0"]`.
- **Impact:** Non-reproducible builds; supply-chain drift. (SaaS `requirements.txt` **is** pinned.)
- **Resolution:** Pin exact versions + add a lockfile; add dependency scanning in CI.
- **Complexity:** S.

#### F-16 â€” Logging is unstructured; no correlation ids, metrics, or readiness/liveness split
- **Evidence:** `saas/app.py:60-63` `logging.basicConfig(format="%(asctime)s ...")`; only `/health`
  exists (app.py:281). No JSON logs, no request/GitHub/queue metrics, no `/ready` vs `/live`.
- **Resolution:** Structured JSON logging in prod with redaction; correlation-id middleware;
  Prometheus metrics; `/livez` + `/readyz`.
- **Complexity:** M.

### Low

#### F-17 â€” `daemon=True` worker threads + no graceful shutdown
- **Evidence:** `saas/app.py:1233-1238`; no signal handling / drain.
- **Resolution:** Superseded by F-02 (external workers) + graceful shutdown hooks.
- **Complexity:** M (with F-02).

#### F-18 â€” Documentation sprawl / drift
- **Evidence:** ~30 root `*.md` files (e.g. `BUG_ELIMINATION_REPORT.md`,
  `PRODUCTION_RELEASE_SUMMARY.md`, multiple `BULK_SCAN_*` and `DOCKER_*` docs) with overlapping,
  sometimes contradictory "production ready / bug-free" claims.
- **Resolution:** Consolidate into `docs/` catalog (this effort); archive superseded files under
  `docs/archive/` rather than deleting, per the "prove before delete" rule.
- **Complexity:** M.

#### F-19 â€” `get_gvd_executable` couples web service to CLI source path / optional `.exe`
- **Evidence:** `saas/app.py:246-263` resolves a sibling `cli/cli.py` or a prebuilt `dist/cli.exe`
  and shells out with `python cli.py ...` (app.py:562-595).
- **Impact:** Host-path coupling; violates "no dependency on host absolute paths or a locally
  prebuilt `.exe`." Works in the current mono-repo container but blocks clean service separation.
- **Resolution:** Package the scanner as an importable library / installed console script invoked
  in-process by the worker (no subprocess to a sibling file).
- **Complexity:** M.

---

## Blockers (cannot be closed in this environment)

| ID | Blocker | Why it blocks | Safest resolution |
|----|---------|---------------|-------------------|
| B1 | Docker/Compose not installed on this host | Container build/health/compose-smoke gates cannot run here | Run these gates in CI (GitHub Actions) or on a Docker host; this repo will ship the compose files + CI workflow to execute them |
| B2 | GitHub OAuth app credentials & secret rotation | Requires access to the GitHub OAuth App settings (org decision) | Rotate `GITHUB_CLIENT_SECRET` + `FLASK_SECRET_KEY`, inject via secret manager; documented in the security model |
| B3 | Live end-to-end OAuth / private-repo tests | Require real GitHub credentials & network | Use recorded/mock GitHub in CI; run a manual live smoke with a throwaway OAuth app |

No credentials, results, or successful runs are fabricated. Gates that could not run here are
explicitly marked as not-run.

---

## Recommended execution order (maps to phases)

1. **Phase 3 (Foundation):** pin deps, fix toolchain/imports (F-09, F-15), structured config,
   `.env` hygiene, make the test baseline runnable and green for legitimate cases.
2. **Phase 4 (Backend & persistence):** DB + migrations, move jobs/reports/notifications/stats to
   tables, per-resource authz (F-01, F-06, F-11), server-side sessions (F-03), API v1 + OpenAPI
   (F-13), CSRF (F-12).
3. **Phase 5 (Async scanning):** durable queue + isolated worker, idempotency/retries/cancellation,
   host validation & token-out-of-argv (F-02, F-04, F-05, F-19, F-10).
4. **Phase 6 (Frontend):** state coverage, a11y, XSS review.
5. **Phase 7â€“10:** containers, observability, security scans, cleanup, docs, release gates.

See `../architecture/TARGET_ARCHITECTURE.md` and `../adr/` for the justified design.
