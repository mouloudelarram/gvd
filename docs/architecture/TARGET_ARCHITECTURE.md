# GVD â€” Target Architecture

This document proposes a **justified** target architecture and a **nonâ€“big-bang** migration path.
It follows the operating principles: start as a **modular monolith** with clean internal
boundaries, and extract the scanner worker into a separate process/service only where an
operational justification exists (isolation of untrusted repo content, independent scaling).

---

## 1. Current-state architecture

```
                       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
   Browser â”€â”€â”€HTTPâ”€â”€â”€â”€â–¶â”‚  Flask monolith (saas/app.py)              â”‚
                       â”‚  - OAuth login/callback (auth.py)          â”‚
                       â”‚  - Repo listing/search (github.py)         â”‚
                       â”‚  - Clone (clone.py)  â”€â”€ subprocess git â”€â”€â”€â–¶ GitHub
                       â”‚  - Scan  â”€â”€ subprocess python cli/cli.py â”€â–¶ Scanner CLI
                       â”‚  - Jobs/notifications/stats = in-memory     â”‚
   session cookie â—€â”€â”€â”€â”€â”‚    dicts (LOST ON RESTART)                  â”‚
   (contains token!)   â”‚  - Reports written to ./scan_reports (fs)  â”‚
                       â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

Problems (see `../audit/AUDIT_REPORT.md`): token in cookie (F-03), in-memory state (F-01),
blocking work in web threads (F-02), no DB, no queue, no per-resource authz (F-06), subprocess
coupling to CLI file path (F-19), two conflicting bulk-scan implementations (F-10).

---

## 2. Target-state architecture (modular monolith â†’ extractable worker)

```
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                 â”‚                    gvd-web (Flask/Gunicorn)               â”‚
   Browser â”€â”€â”€â”€â”€â–¶â”‚  delivery/            application/           domain/      â”‚
                 â”‚   web (Jinja/UI)  â†’   use-cases          â†’   entities     â”‚
                 â”‚   api  (/api/v1)  â†’   services           â†’   rules        â”‚
                 â”‚   auth (OAuth+PKCE-N/A, server session)                   â”‚
                 â”‚                          â”‚ infrastructure/                â”‚
                 â”‚                          â–¼                                â”‚
                 â”‚   github client Â· repo/job/report repositories Â· session â”‚
                 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                         â”‚ SQL                    â”‚ enqueue       â”‚ read
                         â–¼                        â–¼               â”‚
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”‚
                 â”‚  PostgreSQL   â”‚        â”‚  Redis (queue â”‚      â”‚
                 â”‚  (Alembic)    â”‚â—€â”€â”€â”€â”€â”€â”€â”€â”‚  + sessions)  â”‚      â”‚
                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜        â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â”‚
                         â–²                        â”‚ dequeue       â”‚
                         â”‚ SQL                    â–¼               â”‚
                 â”Œâ”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                 â”‚                gvd-worker (no inbound network)            â”‚
                 â”‚   clone (token via GIT_ASKPASS, host allow-list) â”€â–¶GitHub â”‚
                 â”‚   scan (in-process scanner library, resource limits)      â”‚
                 â”‚   write findings/reports â†’ DB + artifact volume           â”‚
                 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

Named volume `gvd-artifacts` holds generated JSON/PDF reports; DB holds canonical data.

---

## 3. Service / module catalog

| Capability | Phase-1 form | Extract to service whenâ€¦ | Owns |
|-----------|--------------|--------------------------|------|
| Web/UI | module `delivery/web` | UI iteration outpaces API (rare) | templates, static |
| API/BFF | module `delivery/api` (`/api/v1`) | multiple clients need it | request/response contracts |
| Identity/GitHub | module `infrastructure/github` | GH rate-limit isolation needed | OAuth, GH client, token lifecycle |
| Scan orchestration | module `application/orchestration` | throughput demands isolation | job lifecycle, idempotency, retries |
| **Scanner worker** | **separate process `gvd-worker`** | **from day one** (untrusted repo isolation) | clone workspace, scan exec |
| Reporting | module `application/reporting` | heavy PDF load | canonical report model, renderers |
| Persistence | Postgres + Alembic | â€” | users, repos, jobs, findings, reports, audit |
| Queue | Redis (RQ) | durable async justified (F-02) | job messages, retries, DLQ |

**Why the worker is a separate process now (justified, not cosmetic):** it executes `git clone`
and analyzes **untrusted third-party repository content**; isolating it (its own container, no
inbound ports, dropped Linux capabilities, read-only FS except a temp workspace, CPU/mem/pids
limits) contains a compromised-clone blast radius. Everything else stays in one deployable to
avoid a distributed monolith.

For each component's responsibility, API, events, data ownership, dependencies, auth, scaling,
failure behavior, health checks, resource limits, and deployment config, see the per-component
sections in `../adr/` and the forthcoming `docs/services/` catalog (created during Phase 4â€“5).

---

## 4. Data model (initial)

- `users(id, github_id, login, created_at, ...)`
- `repositories(id, owner_login, name, clone_url, visibility, github_repo_id)`
- `scan_jobs(id uuid, owner_user_id, type[single|bulk], status, idempotency_key, created_at,
  updated_at, cancel_requested, retry_count)`
- `scan_targets(id, job_id, repo_id, status, error)`
- `findings(id, job_id, repo_id, severity, secret_type, file_path, commit_hash, redacted_snippet)`
- `reports(id uuid, job_id, owner_user_id, format, artifact_path, sha256, created_at)`
- `notifications(id, owner_user_id, type, title, message, read, created_at)`
- `audit_events(id, actor_user_id, action, resource, ip, at)`

Migrations via Alembic; every id that is externally referenceable is UUID4 (fixes F-06 guessable ids).

---

## 5. Key sequences

**OAuth login:** Browser â†’ `/login` â†’ GH authorize (state) â†’ `/callback` (validate state, exact
redirect-uri) â†’ exchange code (server-side) â†’ create/rotate **server-side** session â†’ store token
server-side (encrypted) â†’ redirect dashboard.

**Bulk scan:** `POST /api/v1/scans` (idempotency-key) â†’ persist `scan_job(queued)` â†’ enqueue â†’
worker dequeues â†’ per repo: validate host â†’ clone (token via GIT_ASKPASS) â†’ scan (in-process) â†’
persist findings + report â†’ update job â†’ notification. Client polls
`GET /api/v1/scans/{id}` (owner-checked) or receives SSE progress.

**Cancellation:** `POST /api/v1/scans/{id}/cancel` sets `cancel_requested`; worker checks the flag
between repos and terminates the current clone/scan; job â†’ `cancelled`; workspace cleaned.

---

## 6. Trust boundaries

1. Browser â†” gvd-web (authn/z, CSRF, session).
2. gvd-web â†” Postgres/Redis (internal network only).
3. gvd-worker â†” GitHub (egress only; token never in argv/logs).
4. **Untrusted repo content** is confined to the worker's disposable workspace.

---

## 7. Migration roadmap (incremental, test-backed)

| Step | Deliverable | Closes |
|------|-------------|--------|
| 3.1 | Pin deps, unify CLI imports, make tests runnable & green | F-09, F-15 |
| 3.2 | Structured config module, `.env` hygiene, secret rules | B2 |
| 4.1 | DB + Alembic; move jobs/reports/notifications/stats to tables | F-01, F-11 |
| 4.2 | Server-side sessions; per-resource authz; UUID ids | F-03, F-06 |
| 4.3 | `/api/v1` + schema validation + OpenAPI + error envelope + CSRF | F-12, F-13 |
| 5.1 | Redis queue + gvd-worker; idempotency/retry/cancel/cleanup | F-02, F-17 |
| 5.2 | Parsed-hostname clone allow-list; token out of argv; in-process scanner | F-04, F-05, F-19 |
| 5.3 | Delete redundant bulk-scan manager after reference check | F-10 |
| 6.x | Frontend states, a11y, XSS review, e2e | â€” |
| 7.x | Dockerfiles per service, compose dev+prod, health, non-root | B1 |
| 8.x | Security scans, SBOM, perf, failure injection | â€” |
| 9.x | Consolidate docs, archive superseded files | F-18 |

Trade-offs: adding Postgres + Redis raises the local footprint, but both run in Compose and are
required to meet the durability/observability goals; SQLite is offered for the lightest local dev.
