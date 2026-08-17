# GVD — Quick Reference and Operations Guide

> **Canonical reference** — supersedes root-level `QUICK_REFERENCE.md`, `SCRIPTS_GUIDE.md`,
> `IMPLEMENTATION_GUIDE.md`, `INTEGRATION_GUIDE.md`, and `ENTERPRISE_UPGRADE.md`
> (all now redirect stubs, Phase 9 C-28, 2026-08-17).

---

## Essential Commands

### Run tests

```bash
# SaaS backend tests (127 tests)
cd saas && python -m pytest -q

# CLI tests
cd cli && python -m pytest -q

# Both (from repo root)
python -m pytest saas/ cli/ -q

# Frontend / accessibility (requires Node)
cd saas/frontend-tests && npm ci && npx playwright test
```

### Start the app locally (without Docker)

```bash
# SaaS
cd saas
python -m venv .venv && .venv\Scripts\activate   # Windows
# source .venv/bin/activate                      # macOS/Linux
pip install -r requirements.txt
cp .env.example .env  # fill in values
python app.py         # http://localhost:5000

# CLI
cd cli
pip install -e .
gvd scan --path /path/to/repo
```

### Start with Docker Compose

```bash
cp .env.example .env   # fill in values
docker compose up --build
# open http://localhost:5000
docker compose down    # stop
docker compose down -v # full reset
```

### Database migrations

```bash
docker compose exec gvd-saas flask db upgrade   # apply pending
docker compose exec gvd-saas flask db current   # check state
docker compose exec gvd-saas flask db history   # show history
```

### Linting and static analysis

```bash
cd saas && python -m ruff check .           # lint
cd saas && python -m ruff format --check .  # format check
cd cli  && python -m ruff check .
```

---

## Environment Variables — Complete Catalog

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_CLIENT_ID` | ✅ | — | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | ✅ | — | GitHub OAuth App Client Secret (never commit) |
| `OAUTH_REDIRECT_URI` | ✅ | — | Must match GitHub App setting exactly |
| `FLASK_SECRET_KEY` | ✅ | — | Session encryption key (≥32 random bytes) |
| `FLASK_ENV` | — | `development` | `production` enables gunicorn, JSON logs, strict cookies |
| `DATABASE_URL` | ✅ | — | PostgreSQL DSN e.g. `postgresql://gvd:pass@localhost:5432/gvd` |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Redis DSN (job queue + sessions) |
| `SCANNER_MODE` | — | `inprocess` | `inprocess` or `subprocess` |
| `ENABLE_BULK_SCAN` | — | `true` | Disable bulk-scan UI with `false` |
| `MAX_CONCURRENT_BULK_SCANS` | — | `3` | Max active bulk jobs per user |
| `SCAN_TIMEOUT_SECONDS` | — | `300` | Per-repository scan timeout |
| `MAX_REPOS_FETCH` | — | `1000` | GitHub API page cap |
| `ENABLE_METRICS` | — | `false` | Expose `/metrics` in Prometheus format |
| `LOG_LEVEL` | — | `INFO` | Python logging level |
| `HTTPS_PROXY` | — | — | Corporate proxy URL |
| `HTTP_PROXY` | — | — | Corporate proxy URL (HTTP) |
| `NO_PROXY` | — | — | Comma-separated hosts to bypass |
| `REQUESTS_CA_BUNDLE` | — | — | Path to custom CA bundle |
| `GITHUB_FOLLOW_WINDOWS_PAC` | — | `false` | Use Windows PAC file for GitHub routing |
| `CORS_ORIGINS` | — | — | Allowed CORS origins (comma-separated) |
| `SESSION_COOKIE_SECURE` | — | `true` in prod | Enforce `Secure` flag on session cookie |
| `POSTGRES_PASSWORD` | — | — | Postgres password (Compose only) |

---

## API Routes Reference

### Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | — | Login page |
| `GET` | `/login` | — | Redirect to GitHub OAuth |
| `GET` | `/callback` | — | OAuth callback; creates session |
| `POST` | `/logout` | session | Destroy session |

### Dashboard and Repositories

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/dashboard` | session | Main dashboard |
| `GET` | `/repos` | session | Paginated repository list (JSON) |
| `GET` | `/repos/search` | session | Search repositories |

### Scanning

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/scan` | session | Start single-repo scan |
| `GET` | `/scan/<job_id>` | session (owner) | Poll single scan status |
| `POST` | `/scan-all` | session | Start bulk scan |
| `GET` | `/scan-all/<job_id>` | session (owner) | Poll bulk scan status |
| `POST` | `/scan-all/<job_id>/cancel` | session (owner) | Cancel bulk scan |
| `GET` | `/bulk-scan-stats` | session | Aggregate finding counts |
| `GET` | `/bulk-scan-history` | session | List this user's bulk jobs |
| `GET` | `/scan-history` | session | List this user's single scans |

### Reports

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/repo-report/<path>` | session (owner) | View single-repo report |
| `GET` | `/download-report/<path>` | session (owner) | Download single-repo JSON/PDF |
| `GET` | `/download-bulk-report/<job_id>` | session (owner) | Download bulk JSON report |
| `GET` | `/download-bulk-report-pdf/<job_id>` | session (owner) | Download bulk PDF report |

### Health and Observability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | — | Liveness check |
| `GET` | `/readiness` | — | Readiness (DB + Redis) |
| `GET` | `/metrics` | — | Prometheus metrics (if enabled) |

---

## GitHub OAuth Integration

### Create an OAuth App

1. Go to <https://github.com/settings/developers> → **OAuth Apps** → **New OAuth App**.
2. Set **Authorization callback URL** to your `/callback` endpoint.
3. Copy Client ID and Client Secret to `.env`.

### OAuth flow

```
Browser                         GVD                        GitHub
  │  GET /login                   │                            │
  ├──────────────────────────────►│                            │
  │                               │  redirect to github.com   │
  │◄──────────────────────────────┤  ?client_id=...&state=...  │
  │                               │                            │
  │  GET /callback?code=...&state=...                          │
  ├──────────────────────────────►│                            │
  │                               │  POST /login/oauth/access_token
  │                               ├───────────────────────────►│
  │                               │◄───────────────────────────┤
  │                               │  access_token=...          │
  │                               │  GET /user                 │
  │                               ├───────────────────────────►│
  │                               │◄───────────────────────────┤
  │  redirect /dashboard          │  {login, avatar_url, ...}  │
  │◄──────────────────────────────┤                            │
```

Security controls applied:
- `state` parameter validated on callback (CSRF protection)
- Token stored server-side only (never exposed to browser)
- Session rotated after successful auth
- `HttpOnly`, `Secure`, `SameSite=Lax` cookies

---

## Scanner Rule Catalog

The scanner (`saas/scanner_lib.py` / `cli/scanner/`) applies these rule categories:

| Category | Examples | Severity |
|----------|----------|----------|
| Hard-coded secrets | AWS keys, GitHub PATs, private keys | Critical |
| Generic API tokens | `api_key = "..."`, `token = "..."` patterns | High |
| Sensitive files | `.env`, `id_rsa`, `credentials.json` | High |
| Credential patterns in history | Password in a commit message | High |
| Misconfiguration | Debug mode on, insecure cookie flags | Medium |
| Informational | `TODO: fix hardcoded pass` comments | Low |

### Severity model

| Level | CVSS equivalent | Recommended action |
|-------|-----------------|--------------------|
| Critical | 9.0–10.0 | Rotate immediately; treat as compromised |
| High | 7.0–8.9 | Rotate within 24 h |
| Medium | 4.0–6.9 | Remediate within 1 sprint |
| Low | 0.1–3.9 | Remediate in backlog |
| Info | — | Review; no immediate action required |

---

## Integration Guide

### GitHub Actions CI (`.github/workflows/ci.yml`)

The workflow runs:
1. `backend-test` — `pytest` for `saas/` and `cli/`
2. `lint` — `ruff check`
3. `security-scan` — `pip-audit` + `trivy`
4. `frontend-test` — Playwright + axe (Node 20)
5. `compose-smoke` — `docker compose up --build` + health check
6. `sbom` — `syft` SBOM generation

Trigger: every push and pull request to `main`.

### Adding a new scan rule

1. Add a regex or file-glob pattern to `cli/scanner/pattern_engine.py`.
2. Assign a `Severity` via the rule's `severity` field.
3. Add a unit test in `cli/test_cli.py` covering a positive and negative match.
4. Update the **Scanner rule catalog** above.

### Adding a new API endpoint

1. Define the route in `saas/app.py` (or a Blueprint for grouping).
2. Decorate with `@login_required` unless explicitly public.
3. Add schema validation via `marshmallow` or `pydantic`.
4. Add correlation-ID logging.
5. Document in the **API Routes Reference** above.
6. Write API tests in `saas/test_api_v1.py`.

---

## Contribution Guide

1. Fork the repository and create a feature branch (`git checkout -b feat/my-change`).
2. Write focused changes — one logical concern per PR.
3. Ensure all tests pass locally (`python -m pytest saas/ cli/ -q`).
4. Lint (`ruff check .`).
5. Open a PR with a clear description of what, why, and how to test.
6. The CI pipeline must be green before merge.

Good areas to contribute:
- Scanner rule accuracy improvements
- Frontend accessibility enhancements
- Test coverage for edge cases
- Documentation corrections

---

## Known Limitations and Accepted Risks

| Risk | Severity | Status | Tracking |
|------|----------|--------|----------|
| `BULK_SCAN_JOBS` lost on restart (in-process dict) | Medium | Accepted — durable queue planned Phase 5 | F-01 |
| GitHub token stored in server-side session (Redis) | Low | Accepted — rotated on logout; short-lived | F-03 |
| Scanner runs in-process (no sandbox) | Medium | Accepted — no arbitrary code execution; worker isolation planned | F-02 |
| axe/Playwright tests need CI runner with Node | Low | Wired in CI; blocked locally by B5 | B5 |
| Docker Compose smoke test needs CI | Low | Wired in CI; blocked locally by B1 | B1 |
| Secret rotation (B2) requires GitHub App access | Low | Human action required | B2 |

---

*See also: [docker.md](docker.md) · [deployment.md](deployment.md) · [bulk-scan.md](bulk-scan.md)*

