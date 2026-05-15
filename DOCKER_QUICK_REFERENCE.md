# DOCKER DEPLOYMENT CHECKLIST & QUICK REFERENCE

> Pre-deployment verification and quick command reference

## Pre-Deployment Verification Checklist

### Environment Setup

- [ ] Docker Engine 20.10+ installed (`docker --version`)
- [ ] Docker Compose 2.0+ installed (`docker-compose --version`)
- [ ] Git installed (`git --version`)
- [ ] Python 3.10+ available on host (optional, for local development)
- [ ] At least 100GB free disk space (`df -h`)
- [ ] At least 4GB RAM available (`free -h`)

### Configuration Files

- [ ] `.env.production` created from `.env.production.template`
- [ ] All required variables in `.env.production`:
  - `GITHUB_CLIENT_ID` ✓
  - `GITHUB_CLIENT_SECRET` ✓
  - `FLASK_SECRET_KEY` ✓
  - `OAUTH_REDIRECT_URI` ✓
- [ ] `.env.production` is NOT in git (verify .gitignore)
- [ ] SSL certificates ready or Let's Encrypt configured

### Directory Structure

- [ ] `data/scan_reports/` exists
- [ ] `data/repos/` exists
- [ ] `data/uploads/` exists
- [ ] `data/temp/` exists
- [ ] `data/ssl/` exists
- [ ] `logs/nginx/` exists
- [ ] `logs/app/` exists
- [ ] `logs/scanner/` exists
- [ ] All directories have correct permissions (755)

### GitHub OAuth

- [ ] GitHub OAuth App created at https://github.com/settings/developers
- [ ] Authorization callback URL matches `OAUTH_REDIRECT_URI`
- [ ] Client ID and Client Secret copied to `.env.production`

### Security

- [ ] `FLASK_SECRET_KEY` is strong (32+ characters, random)
- [ ] GitHub Client Secret is secure and NOT shared
- [ ] `.env.production` file permissions are 600 (`chmod 600 .env.production`)
- [ ] No secrets committed to Git history

### Network & DNS

- [ ] Domain name points to server IP (DNS A record configured)
- [ ] Domain name resolves correctly (`nslookup your-domain.com`)
- [ ] Port 80 is accessible (`curl http://localhost`)
- [ ] Port 443 will be accessible after SSL setup

### Firewall & Security Groups

- [ ] Port 22 (SSH) accessible from authorized IPs only
- [ ] Port 80 (HTTP) accessible from anywhere
- [ ] Port 443 (HTTPS) accessible from anywhere
- [ ] All other ports blocked (if applicable)

---

## Quick Command Reference

### Build & Start

```bash
# Build all images
docker-compose -f docker-compose.production.yml build

# Start all services
docker-compose -f docker-compose.production.yml up -d

# Start and view logs
docker-compose -f docker-compose.production.yml up

# Restart services
docker-compose -f docker-compose.production.yml restart

# Stop services
docker-compose -f docker-compose.production.yml down

# Stop and remove volumes (full cleanup)
docker-compose -f docker-compose.production.yml down -v
```

### Status & Monitoring

```bash
# Check service status
docker-compose -f docker-compose.production.yml ps

# View all logs
docker-compose -f docker-compose.production.yml logs

# Follow logs (real-time)
docker-compose -f docker-compose.production.yml logs -f

# View specific service logs
docker-compose -f docker-compose.production.yml logs gvd-saas
docker-compose -f docker-compose.production.yml logs nginx
docker-compose -f docker-compose.production.yml logs gvd-scanner

# View last 100 lines
docker-compose -f docker-compose.production.yml logs --tail=100

# Monitor real-time stats
docker stats

# Inspect specific container
docker-compose -f docker-compose.production.yml exec gvd-saas env
```

### Troubleshooting

```bash
# SSH into container
docker-compose -f docker-compose.production.yml exec gvd-saas bash
docker-compose -f docker-compose.production.yml exec nginx sh

# Run one-off command
docker-compose -f docker-compose.production.yml exec gvd-saas python -c "import sys; print(sys.version)"

# View container details
docker inspect $(docker-compose -f docker-compose.production.yml ps -q gvd-saas)

# Check network connectivity
docker-compose -f docker-compose.production.yml exec gvd-saas ping nginx
docker-compose -f docker-compose.production.yml exec gvd-saas curl http://nginx/health

# Check volume mounts
docker-compose -f docker-compose.production.yml exec gvd-saas ls -la /app/scan_reports

# Rebuild specific service (no cache)
docker-compose -f docker-compose.production.yml build --no-cache gvd-saas
```

### Health Checks

```bash
# Manual health check
curl http://localhost/health -v
curl https://your-domain.com/health -k

# Check container health status
docker-compose -f docker-compose.production.yml ps

# Detailed health check from Flask
docker-compose -f docker-compose.production.yml exec gvd-saas curl http://localhost:5000/health

# Check Nginx configuration
docker-compose -f docker-compose.production.yml exec nginx nginx -t
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload

# Check SSL certificate
openssl x509 -in data/ssl/cert.pem -text -noout
openssl x509 -in data/ssl/cert.pem -noout -dates
```

### Scaling

```bash
# Scale Flask service to 3 instances
docker-compose -f docker-compose.production.yml up -d --scale gvd-saas=3

# Scale scanner to 5 instances
docker-compose -f docker-compose.production.yml up -d --scale gvd-scanner=5

# Return to single instance
docker-compose -f docker-compose.production.yml up -d --scale gvd-saas=1
```

### Volume Management

```bash
# List all volumes
docker volume ls

# Inspect volume
docker volume inspect gvd-scan-reports

# Backup volume
docker run --rm -v gvd-scan-reports:/data -v $(pwd):/backup \
  alpine tar czf /backup/scan-reports-$(date +%s).tar.gz -C /data .

# Restore volume
docker run --rm -v gvd-scan-reports:/data -v $(pwd):/backup \
  alpine tar xzf /backup/scan-reports-XXXXX.tar.gz -C /data

# Remove unused volumes
docker volume prune
```

### Updates & Maintenance

```bash
# Pull latest images
docker-compose -f docker-compose.production.yml pull

# Rebuild images after code changes
docker-compose -f docker-compose.production.yml build

# Restart services after updates
docker-compose -f docker-compose.production.yml restart

# Renew Let's Encrypt certificate
sudo certbot renew --quiet
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload
```

### Cleanup

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused networks
docker network prune

# Remove unused volumes
docker volume prune

# Full cleanup (CAREFUL - removes everything not in use)
docker system prune -a

# Check disk usage
docker system df
```

---

## Deployment Workflows

### First-Time Production Deployment

```bash
# 1. Prepare environment
mkdir -p data/{scan_reports,repos,uploads,temp,ssl} logs/{nginx,app,scanner}
chmod 755 data logs

# 2. Configure
cp .env.production.template .env.production
nano .env.production

# 3. Setup SSL
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem
chmod 644 data/ssl/cert.pem
chmod 600 data/ssl/key.pem

# 4. Build & start
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# 5. Verify
docker-compose -f docker-compose.production.yml ps
curl https://your-domain.com/health -k

# 6. Enable auto-start
sudo systemctl enable docker
# Create /etc/systemd/system/gvd.service (see PRODUCTION_DEPLOYMENT_GUIDE.md)
```

### Update Deployment

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild images (if code changed)
docker-compose -f docker-compose.production.yml build

# 3. Gracefully restart
docker-compose -f docker-compose.production.yml up -d

# 4. Verify
docker-compose -f docker-compose.production.yml ps
docker-compose -f docker-compose.production.yml logs -f gvd-saas | head -20

# 5. Rollback if needed
git checkout previous-commit
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml restart
```

### Disaster Recovery

```bash
# 1. Backup current state
for vol in gvd-scan-reports gvd-repos gvd-uploads; do
  docker run --rm -v $vol:/data -v $(pwd)/backups:/backup \
    alpine tar czf /backup/${vol}-$(date +%s).tar.gz -C /data .
done

# 2. Stop services
docker-compose -f docker-compose.production.yml down

# 3. Restore from backup
docker run --rm -v gvd-scan-reports:/data -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/scan-reports-LATEST.tar.gz -C /data

# 4. Start services
docker-compose -f docker-compose.production.yml up -d

# 5. Verify
docker-compose -f docker-compose.production.yml ps
```

### Local Development Workflow

```bash
# 1. Use development compose file
docker-compose up -d  # Uses docker-compose.yml (development)

# 2. View logs
docker-compose logs -f

# 3. Make code changes (files reflected live if using volumes)

# 4. Restart services if needed
docker-compose restart gvd-saas

# 5. Test changes
curl http://localhost

# 6. Stop when done
docker-compose down
```

---

## Environment Variable Reference

### Required

```bash
GITHUB_CLIENT_ID=                    # From GitHub OAuth App
GITHUB_CLIENT_SECRET=                # From GitHub OAuth App  
FLASK_SECRET_KEY=                    # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
OAUTH_REDIRECT_URI=https://your-domain.com/callback
```

### Optional Performance

```bash
GUNICORN_WORKERS=9                   # Default: (2 * CPU_COUNT) + 1
REQUEST_TIMEOUT=300                  # Seconds
SCAN_TIMEOUT_SECONDS=300             # Seconds
```

### Optional Features

```bash
ENABLE_BULK_SCAN=true                # Enable bulk scanning
ENABLE_PDF_REPORTS=true              # Enable PDF report generation
MAX_REPOS_FETCH=1000                 # Max repos to fetch per user
```

### Optional Logging

```bash
LOG_LEVEL=INFO                       # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json                      # json or text
```

### Optional Security

```bash
SESSION_COOKIE_SECURE=true           # HTTPS only (set automatically)
SESSION_COOKIE_HTTPONLY=true         # No JavaScript access
CORS_ORIGINS=https://your-domain.com # CORS allowed origins
```

---

## Useful Docker Compose Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
alias dc="docker-compose -f docker-compose.production.yml"
alias dc-up="docker-compose -f docker-compose.production.yml up -d"
alias dc-down="docker-compose -f docker-compose.production.yml down"
alias dc-logs="docker-compose -f docker-compose.production.yml logs -f"
alias dc-ps="docker-compose -f docker-compose.production.yml ps"
alias dc-restart="docker-compose -f docker-compose.production.yml restart"
alias dc-shell="docker-compose -f docker-compose.production.yml exec"
```

Usage:
```bash
dc up                    # Start
dc ps                    # Check status
dc logs -f gvd-saas     # View Flask logs
dc shell gvd-saas bash  # Enter Flask container
dc restart gvd-saas     # Restart Flask
```

---

## Common Issues & Quick Fixes

### 502 Bad Gateway

```bash
# Check if Flask is running
docker-compose -f docker-compose.production.yml ps

# Check Flask logs
docker-compose -f docker-compose.production.yml logs gvd-saas

# Restart
docker-compose -f docker-compose.production.yml restart gvd-saas
```

### High Memory Usage

```bash
# Check stats
docker stats

# Reduce workers
# Edit .env.production: GUNICORN_WORKERS=4
docker-compose -f docker-compose.production.yml restart gvd-saas
```

### Slow Scans

```bash
# Check if scanner is running
docker-compose -f docker-compose.production.yml ps gvd-scanner

# View scanner logs
docker-compose -f docker-compose.production.yml logs gvd-scanner

# Scale scanner
docker-compose -f docker-compose.production.yml up -d --scale gvd-scanner=3
```

### SSL Certificate Errors

```bash
# Check certificate
openssl x509 -in data/ssl/cert.pem -text -noout | grep -E "Issuer|Subject"

# Renew
sudo certbot renew
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload
```

---

## Performance Benchmarking

### Load Testing

```bash
# Simple load test (requires Apache Bench)
ab -n 1000 -c 10 https://your-domain.com/

# More comprehensive (requires Locust)
pip install locust
locust -f locustfile.py --host=https://your-domain.com

# Check response times
curl -w "@curl-format.txt" -o /dev/null -s https://your-domain.com/
```

### Container Stats During Load

```bash
# Terminal 1: Monitor
docker stats

# Terminal 2: Generate load
for i in {1..100}; do curl https://your-domain.com/health -k & done; wait
```

---

## Documentation Links

- Full Deployment Guide: [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)
- AWS EC2 Quick Start: [AWS_EC2_QUICK_START.md](AWS_EC2_QUICK_START.md)
- Docker Architecture: [DOCKER_ARCHITECTURE_GUIDE.md](DOCKER_ARCHITECTURE_GUIDE.md)
- Original README: [README.md](README.md)

---

**Version**: 1.0.0
**Last Updated**: 2024
**Quick Reference for**: Docker deployment, scaling, troubleshooting
