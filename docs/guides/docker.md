# GVD — Docker Guide

> **Canonical reference** — supersedes root-level `DOCKER_SETUP.md`,
> `DOCKER_ARCHITECTURE_GUIDE.md`, `DOCKER_QUICK_REFERENCE.md`, and the earlier
> `docs/guides/docker-compose.md` (all now redirect stubs, Phase 9 C-28, 2026-08-17).

---

## Quick Start (clean checkout)

```bash
# 1. Copy and fill in the environment template
cp .env.example .env
# Required: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, FLASK_SECRET_KEY, OAUTH_REDIRECT_URI

# 2. Build and start all services
docker compose up --build

# 3. Open the app
open http://localhost:5000
```

That is the complete developer workflow. Docker Compose loads `.env` automatically; secrets are
injected as environment variables and are **never** baked into the image.

---

## Services

| Service | Image | Role | Published port |
|---------|-------|------|---------------|
| `gvd-saas` | `./saas/Dockerfile` | Flask web app + in-process scanner | `5000` (dev only) |
| `gvd-worker` | `./saas/Dockerfile.prod` | Background scan worker | none |
| `gvd-db` | `postgres:16-alpine` | PostgreSQL persistence | none (internal) |
| `gvd-redis` | `redis:7-alpine` | Job queue / session cache | none (internal) |
| `nginx` | `nginx:1.27-alpine` | Reverse proxy (prod only) | `80`, `443` |

> **Development compose** (`docker-compose.yml`): `gvd-saas` + `gvd-db` + `gvd-redis`.
> **Production compose** (`docker-compose.production.yml`): adds `nginx`, read-only filesystems,
> resource limits, and a migration init-container.

---

## Environment Variables

See `.env.example` for the full annotated list. Key variables:

| Variable | Required | Example | Notes |
|----------|----------|---------|-------|
| `GITHUB_CLIENT_ID` | ✅ | `Iv1.abc123` | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | ✅ | `secret` | **Never commit.** Inject via env/secrets manager |
| `FLASK_SECRET_KEY` | ✅ | `$(python -c "import secrets; print(secrets.token_urlsafe(32))")` | Min 32 random bytes |
| `OAUTH_REDIRECT_URI` | ✅ | `http://localhost:5000/callback` | Must match GitHub App setting exactly |
| `DATABASE_URL` | ✅ | `postgresql://gvd:pass@gvd-db:5432/gvd` | Set automatically in Compose |
| `REDIS_URL` | ✅ | `redis://gvd-redis:6379/0` | Set automatically in Compose |
| `FLASK_ENV` | — | `production` | Enables gunicorn, JSON logs, strict cookies |
| `SCANNER_MODE` | — | `inprocess` | `inprocess` (default) or `subprocess` |
| `HTTPS_PROXY` | — | `http://proxy:8080` | Corporate proxy (optional) |
| `REQUESTS_CA_BUNDLE` | — | `/etc/ssl/certs/ca-certificates.crt` | Custom CA bundle path |
| `GITHUB_FOLLOW_WINDOWS_PAC` | — | `true` | Use Windows PAC file for GitHub routing |

---

## Health, Status, Reset

```bash
# Check service health
docker compose ps                          # STATUS column: "healthy" / "unhealthy"
curl -fsS http://localhost:5000/health    # {"status":"healthy","db":"ok","redis":"ok"}

# Live logs
docker compose logs -f gvd-saas

# Stop everything (keep volumes)
docker compose down

# Full reset (removes volumes / persisted data)
docker compose down -v

# Rebuild one service
docker compose up --build gvd-saas
```

---

## Persistence (Named Volumes)

No host-absolute paths are required. All runtime data lives in named volumes:

| Volume | Mount in container | Contains |
|--------|--------------------|----------|
| `gvd_postgres_data` | `/var/lib/postgresql/data` | PostgreSQL database |
| `gvd_scan_reports` | `/app/scan_reports` | Scan artefacts (JSON/PDF) |
| `gvd_repos` | `/app/repos` | Transient clone workspace (cleaned after scan) |

### Backup

```bash
# Backup scan reports
docker run --rm \
  -v gvd_scan_reports:/data \
  -v "$PWD:/backup" \
  busybox tar czf /backup/scan_reports_$(date +%Y%m%d).tgz -C /data .

# Backup database
docker compose exec gvd-db pg_dump -U gvd gvd > backup_$(date +%Y%m%d).sql
```

### Restore

```bash
# Restore scan reports
docker run --rm \
  -v gvd_scan_reports:/data \
  -v "$PWD:/backup" \
  busybox tar xzf /backup/scan_reports_YYYYMMDD.tgz -C /data

# Restore database
docker compose exec -T gvd-db psql -U gvd gvd < backup_YYYYMMDD.sql
```

---

## Database Migrations

Migrations run automatically via an init-container in the production Compose file.
In development they run on app startup:

```bash
# Run migrations manually
docker compose exec gvd-saas flask db upgrade

# Check migration status
docker compose exec gvd-saas flask db current
```

---

## Architecture

```
                ┌──────────────────────────────────────────────────────┐
                │  Docker internal network (gvd-net)                   │
                │                                                      │
  Browser ──► nginx:443/80 ──► gvd-saas:5000 ──► gvd-db:5432         │
                │                    │                                 │
                │                    └──────────► gvd-redis:6379       │
                │                    │                                 │
                │               gvd-worker ──────► gvd-db:5432        │
                │                                ► gvd-redis:6379      │
                └──────────────────────────────────────────────────────┘
```

- **`gvd-saas`** handles HTTP, serves HTML, calls GitHub API, enqueues scan jobs.
- **`gvd-worker`** dequeues jobs, clones repositories, runs the scanner, saves reports.
- **`gvd-db`** (Postgres) stores users, scan jobs, findings, audit events.
- **`gvd-redis`** brokers the job queue and backs server-side sessions.
- **`nginx`** terminates TLS, enforces HTTPS, and applies rate limits (production only).

The worker has **no inbound network exposure** — it only reads from the queue and writes to the
database and volume, which means untrusted repository code cannot reach the web surface.

---

## Security Hardening Applied

| Control | Implementation |
|---------|---------------|
| Non-root user | `USER gvd` (UID 1001) in every Dockerfile |
| Read-only filesystem | `read_only: true` + `tmpfs` for `/tmp` (production Compose) |
| No unnecessary capabilities | `cap_drop: [ALL]` in production Compose |
| Resource limits | CPU/memory limits on every service (production Compose) |
| Internal network | Only `nginx` publishes ports; all other services are internal |
| Secrets via env | No secrets baked into images; `.env` is gitignored |
| TLS enabled | `REQUESTS_CA_BUNDLE` / `truststore` — TLS verification is never disabled |

---

## Enterprise Proxy / Custom CA

```bash
# .env
HTTPS_PROXY=http://proxy.corp.example.com:8080
HTTP_PROXY=http://proxy.corp.example.com:8080
NO_PROXY=localhost,127.0.0.1,gvd-db,gvd-redis

# If your proxy performs TLS inspection, mount your corporate CA bundle:
# docker-compose.yml — add to gvd-saas volumes:
#   - /etc/ssl/certs/corp-ca.crt:/etc/ssl/certs/corp-ca.crt:ro
# Then set:
REQUESTS_CA_BUNDLE=/etc/ssl/certs/corp-ca.crt
```

GVD uses `truststore` to pick up the OS certificate store automatically on all platforms.
TLS verification is **never** disabled.

---

## Multi-Platform Builds

The provided Dockerfiles use standard Python and Alpine base images that support `linux/amd64`
and `linux/arm64`. For CI or registry pushes:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/your-org/gvd-saas:latest .
```

---

## Development vs Production Compose

| Feature | `docker-compose.yml` | `docker-compose.production.yml` |
|---------|---------------------|--------------------------------|
| Hot-reload | ✅ (volume mount of source) | ❌ |
| nginx | ❌ | ✅ |
| Read-only filesystem | ❌ | ✅ |
| Resource limits | ❌ | ✅ |
| Migration init-container | ❌ | ✅ |
| `FLASK_ENV` | `development` | `production` |
| Debug mode | ✅ | ❌ |

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---------|-------------|------------|
| `gvd-saas` stays unhealthy | Missing env var | `docker compose logs gvd-saas` — look for `KeyError` or missing config |
| `Connection refused` on `5000` | Service not started | `docker compose ps`; `docker compose up` |
| Database migration fails | Postgres not ready | Compose's `depends_on: condition: service_healthy` handles ordering; if still failing, `docker compose down -v && docker compose up --build` |
| GitHub OAuth callback mismatch | `OAUTH_REDIRECT_URI` wrong | Set it to the exact URL including protocol and port registered in the GitHub OAuth App |
| `certificate verify failed` | Corporate proxy TLS inspection | Set `REQUESTS_CA_BUNDLE` to your CA bundle path |

---

*See also: [deployment.md](deployment.md) · [bulk-scan.md](bulk-scan.md) · [quick-reference.md](quick-reference.md)*

