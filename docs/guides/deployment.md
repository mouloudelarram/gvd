# GVD — Deployment Guide

> **Canonical reference** — supersedes root-level `DEPLOYMENT_GUIDE.md`,
> `PRODUCTION_DEPLOYMENT_GUIDE.md`, and `AWS_EC2_QUICK_START.md`
> (all now redirect stubs, Phase 9 C-28, 2026-08-17).

---

## Deployment Options

| Option | Best for | Guide section |
|--------|----------|---------------|
| Docker Compose (dev) | Local development | [Docker guide](docker.md) |
| Docker Compose (production) | Single server | [Single-server deployment](#single-server-deployment) |
| AWS EC2 | Cloud single-server | [AWS EC2](#aws-ec2) |
| Kubernetes | Future scaling | Out of scope for v1 |

---

## Prerequisites

### System requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8 GB+ |
| Storage | 20 GB | 100 GB+ (for repository clones) |
| OS | Ubuntu 22.04 LTS / Debian 12 / RHEL 9 | Ubuntu 24.04 LTS |
| Docker | 24.0+ | Latest stable |
| Docker Compose | v2.20+ | Latest stable |
| Git | 2.25+ | Latest stable |

### External dependencies

- **GitHub OAuth Application** — create at <https://github.com/settings/developers>.
  - Set **Authorization callback URL** to `https://<your-domain>/callback`.
- **Domain name** — required for production TLS.
- **TLS certificate** — Let's Encrypt (free) or corporate PKI.

---

## Single-Server Deployment

### Step 1 — Provision the server

```bash
# Ubuntu 22.04 — install Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker version
docker compose version
```

### Step 2 — Clone the repository

```bash
git clone https://github.com/your-org/gvd.git
cd gvd
```

### Step 3 — Configure environment

```bash
cp .env.example .env
# Edit .env — fill in ALL required values:
```

Required variables (`.env`):

```dotenv
# GitHub OAuth
GITHUB_CLIENT_ID=Iv1.your_client_id
GITHUB_CLIENT_SECRET=your_client_secret          # never commit this value
OAUTH_REDIRECT_URI=https://yourdomain.com/callback

# Flask
FLASK_SECRET_KEY=<output of: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
FLASK_ENV=production

# Database (Compose sets this automatically)
DATABASE_URL=postgresql://gvd:change_me@gvd-db:5432/gvd
POSTGRES_PASSWORD=change_me                      # change to a strong random password

# Redis (Compose sets this automatically)
REDIS_URL=redis://gvd-redis:6379/0
```

### Step 4 — Configure nginx and TLS

```bash
# Install Certbot (Let's Encrypt)
sudo apt install certbot python3-certbot-nginx

# Obtain a certificate (before starting nginx in Docker)
sudo certbot certonly --standalone -d yourdomain.com

# Copy certs to the project (or bind-mount from /etc/letsencrypt)
cp -r /etc/letsencrypt/live/yourdomain.com nginx/certs/
```

Update `nginx/nginx-production.conf` — replace `yourdomain.com` with your actual domain.

### Step 5 — Start the stack

```bash
docker compose -f docker-compose.production.yml up -d --build

# Follow startup logs
docker compose -f docker-compose.production.yml logs -f

# Check health
curl -fsS https://yourdomain.com/health
```

### Step 6 — Verify

```bash
docker compose -f docker-compose.production.yml ps
# All services should show STATUS: healthy
```

---

## AWS EC2

### Recommended instance type

| Use | Instance |
|-----|----------|
| Development / small team | `t3.medium` (2 vCPU, 4 GB) |
| Production (50 users) | `t3.large` (2 vCPU, 8 GB) |
| Production (heavy scanning) | `c6i.xlarge` (4 vCPU, 8 GB) |

### Quick start

```bash
# 1. Launch an Ubuntu 22.04 EC2 instance
#    - Open ports: 22 (SSH), 80 (HTTP), 443 (HTTPS) in the security group
#    - Attach an IAM role only if you need AWS-specific integrations

# 2. SSH into the instance
ssh -i your-key.pem ubuntu@<ec2-public-ip>

# 3. Install Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker ubuntu
newgrp docker

# 4. Clone and configure
git clone https://github.com/your-org/gvd.git && cd gvd
cp .env.example .env
# Edit .env as above

# 5. Configure TLS (with Let's Encrypt)
sudo snap install --classic certbot
sudo certbot certonly --standalone -d yourdomain.com

# 6. Start
docker compose -f docker-compose.production.yml up -d --build
```

### EC2 cost estimate (us-east-1, 2026)

| Instance | On-demand / month | Savings plan / month |
|----------|------------------|---------------------|
| `t3.medium` | ~$30 | ~$18 |
| `t3.large` | ~$60 | ~$36 |

Add ~$10/month for a 100 GB EBS volume.

---

## Upgrade Procedure

```bash
# 1. Pull latest code
git pull origin main

# 2. Review MIGRATION_NOTES.md for any manual steps

# 3. Rebuild and restart (rolling: Compose recreates one container at a time)
docker compose -f docker-compose.production.yml up -d --build

# 4. Verify health
curl -fsS https://yourdomain.com/health
docker compose -f docker-compose.production.yml ps
```

If migrations are needed they run automatically via the init-container.

---

## Rollback Procedure

```bash
# 1. Identify the previous image tag or commit
git log --oneline -5

# 2. Check out the previous tag
git checkout v1.2.3

# 3. Restart
docker compose -f docker-compose.production.yml up -d --build

# 4. If the database schema changed, restore from backup FIRST:
docker compose exec -T gvd-db psql -U gvd gvd < backup_YYYYMMDD.sql
```

> **Rule:** Always take a database backup before upgrading (see [docker.md — Backup](docker.md)).

---

## TLS Certificate Renewal

Let's Encrypt certificates expire in 90 days. Automate renewal:

```bash
# Add to root crontab
0 3 * * * certbot renew --quiet && docker compose -f /opt/gvd/docker-compose.production.yml \
  exec nginx nginx -s reload
```

---

## Monitoring and Alerting

GVD exposes:

- `GET /health` — liveness (returns `200` when the app is running)
- `GET /readiness` — readiness (returns `200` when DB + Redis are reachable)
- `GET /metrics` — Prometheus-format metrics (if `ENABLE_METRICS=true`)

### Recommended alerts

| Metric / check | Threshold | Action |
|----------------|-----------|--------|
| `/health` returns non-200 | 2 consecutive failures | Page on-call |
| `/readiness` DB check fails | Any failure | Page DBA |
| Disk usage `gvd_scan_reports` | > 80 % | Alert + archive old reports |
| Worker queue depth | > 50 jobs | Scale worker or investigate |
| Error rate (5xx/min) | > 5 | Investigate logs |

---

## Security Checklist

Before going live:

- [ ] `FLASK_SECRET_KEY` is a strong random value (≥ 32 bytes), not the example default
- [ ] `GITHUB_CLIENT_SECRET` is rotated and not stored in version control
- [ ] `POSTGRES_PASSWORD` is a strong random value
- [ ] `OAUTH_REDIRECT_URI` exactly matches the GitHub OAuth App setting
- [ ] HTTPS enforced — HTTP redirects to HTTPS in nginx config
- [ ] `FLASK_ENV=production` is set
- [ ] `.env` is not committed (verify with `git status`)
- [ ] Containers run as non-root (`USER gvd`)
- [ ] Read-only filesystem enabled in production Compose
- [ ] Dependency scan clean (`pip-audit`, `trivy`)

---

## Operations Runbook

### Restart a single service

```bash
docker compose -f docker-compose.production.yml restart gvd-saas
```

### View recent error logs

```bash
docker compose -f docker-compose.production.yml logs --since 1h gvd-saas | grep -i error
```

### Clear stuck bulk-scan jobs

```bash
# Via the admin endpoint (requires admin session)
curl -X POST https://yourdomain.com/admin/cleanup-jobs \
  -H "X-CSRF-Token: <token>"
```

### Disk space — archive old reports

```bash
# List large report directories
docker compose exec gvd-saas du -sh /app/scan_reports/bulk/*

# Remove reports older than 30 days
docker compose exec gvd-saas find /app/scan_reports -mtime +30 -type f -delete
```

---

## Backup and Restore

See [Docker guide — Backup](docker.md#backup).

---

## Data Retention Policy

| Data | Default retention | How to change |
|------|------------------|---------------|
| Scan report files | Indefinite | Delete files in `gvd_scan_reports` volume |
| Database scan records | Indefinite | Run `DELETE FROM scan_jobs WHERE created_at < NOW() - INTERVAL '90 days'` |
| Audit events | Indefinite | Same SQL |
| Session data (Redis) | 24 h (TTL) | Automatic |

> **GDPR / data subject requests:** a user's data can be deleted by removing their row from the
> `users` table (cascades to `scan_jobs`, `findings`, `reports` via foreign key constraints) and
> removing their scan report files from the volume.

---

*See also: [docker.md](docker.md) · [bulk-scan.md](bulk-scan.md) · [quick-reference.md](quick-reference.md)*

