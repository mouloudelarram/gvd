# DOCKER ARCHITECTURE & DEPLOYMENT GUIDE

> Complete reference for GVD containerization strategy

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Container Design](#container-design)
3. [File Structure](#file-structure)
4. [Build Process](#build-process)
5. [Runtime Configuration](#runtime-configuration)
6. [Networking](#networking)
7. [Storage & Volumes](#storage--volumes)
8. [Security Implementation](#security-implementation)
9. [Performance Considerations](#performance-considerations)
10. [Scaling Strategy](#scaling-strategy)

---

## Architecture Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        INTERNET (HTTPS)                      │
└────────────────────────────┬────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  AWS EC2 / VPS   │
                    │  Public IP:Port  │
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐
     │   Nginx     │  │  (Internal) │  │ Certbot    │
     │  :80, :443  │  │    gvd-     │  │ (Optional) │
     │             │  │   saas      │  │            │
     │ - Reverse   │  │  :5000      │  │ - Cert     │
     │   Proxy     │  │             │  │   renewal  │
     │ - SSL/TLS   │  │ - Flask     │  │            │
     │ - Static    │  │ - Gunicorn  │  │            │
     │   Serving   │  │ - App       │  │            │
     │ - Security  │  │   Logic     │  │            │
     │   Headers   │  │             │  │            │
     │ - Rate      │  └──────┬──────┘  └────────────┘
     │   Limiting  │         │
     └─────────────┘         │
                             │
                    ┌────────▼────────┐
                    │ gvd-scanner     │
                    │ (Background)    │
                    │                 │
                    │ - CLI Scanner   │
                    │ - Report Gen    │
                    │ - Git Ops       │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐    ┌─────────▼────────┐  ┌────▼────┐
    │ Volumes │    │   Internal       │  │  Logs   │
    │         │    │   Network:       │  │ Volumes │
    │ - Repos │    │   172.23.0.0/16  │  │         │
    │ - Scans │    │                  │  │ - Nginx │
    │ - Upload│    │ Bridge Driver    │  │ - Flask │
    │ - Temp  │    │ Isolated         │  │ - Scanner
    │ - Certs │    │ Secure           │  │         │
    └─────────┘    └──────────────────┘  └─────────┘
```

### Container Stack Summary

| Layer | Component | Port | Purpose |
|-------|-----------|------|---------|
| **Edge** | Nginx | 80/443 | Public interface, SSL/TLS, security headers |
| **Application** | Gunicorn + Flask | 5000 | Business logic, API endpoints (internal only) |
| **Background** | CLI Scanner | N/A | Async scanning, report generation |
| **Infrastructure** | Docker Compose | N/A | Orchestration, networking, volume management |

---

## Container Design

### Nginx Container

**Purpose**: Production reverse proxy, SSL/TLS termination, static file serving

**Image**: `nginx:1.25-alpine`

**Features**:
- Reverse proxy to Flask backend
- SSL/TLS termination (Let's Encrypt ready)
- Security headers (CSP, X-Frame-Options, HSTS, etc.)
- Gzip compression
- Rate limiting per endpoint
- Static asset caching
- Access/error logging

**Configuration**: 
- File: `nginx/nginx-production.conf`
- Mount: Read-only configuration
- Volumes: SSL certs, static files, logs

### Flask Backend Container

**Purpose**: Main web application with production WSGI server

**Base Image**: `python:3.11-slim`

**Build Strategy**: Multi-stage build (builder + runtime)

**Features**:
- Non-root user execution (security)
- Multi-stage build for minimal size
- Gunicorn WSGI server
- Worker pool with tuned concurrency
- Health checks
- Graceful shutdown handling
- Comprehensive logging

**Key Optimizations**:
```dockerfile
# Multi-stage: Reduces image size
# Non-root: Improves security (USER gvd)
# Minimal base: Uses slim image variant
# Proper layering: Improves caching
# Read-only root: Further hardens security
```

**Environment Handling**:
- `.env.production` loaded via docker-compose
- Validated at startup
- Overrideable per deployment

### CLI Scanner Container

**Purpose**: Background scanning, report generation, async tasks

**Base Image**: `python:3.11-slim`

**Build Strategy**: Multi-stage (same as Flask)

**Features**:
- Shares volumes with Flask (repos, reports)
- Can be scaled horizontally
- Git support for cloning
- PDF/JSON report generation
- Isolated execution environment

**Capabilities**:
- Run scheduled scans
- Process scan queues
- Generate reports
- Maintain repository cache

---

## File Structure

```
gvd/
├── saas/                           # Flask backend
│   ├── Dockerfile.prod             # Production multi-stage build
│   ├── Dockerfile                  # Legacy/development (if needed)
│   ├── docker-entrypoint.sh        # Initialization script
│   ├── gunicorn_config.py          # Gunicorn production config
│   ├── requirements.txt            # Production dependencies
│   ├── app.py                      # Flask application
│   ├── config.py                   # Configuration
│   ├── auth.py                     # Authentication logic
│   ├── *.py                        # Other modules
│   ├── static/                     # Static assets (CSS, JS, images)
│   ├── templates/                  # HTML templates
│   ├── scan_reports/               # Reports (volume mount)
│   ├── repos/                      # Cloned repos (volume mount)
│   ├── uploads/                    # Uploads (volume mount)
│   ├── .dockerignore               # Build context optimization
│   └── .env.example                # Example configuration
│
├── cli/                            # CLI scanner
│   ├── Dockerfile.prod             # Production multi-stage build
│   ├── Dockerfile                  # Legacy/development (if needed)
│   ├── pyproject.toml              # Python project metadata
│   ├── requirements-dev.txt        # Development dependencies
│   ├── cli.py                      # CLI entry point
│   ├── core/                       # Core utilities
│   ├── scanner/                    # Scanning logic
│   ├── report/                     # Report generation
│   ├── utils/                      # Utilities
│   ├── reports/                    # Reports (volume mount)
│   ├── repos/                      # Repositories (volume mount)
│   ├── .dockerignore               # Build context optimization
│   └── test_cli.py                 # Tests
│
├── nginx/                          # Nginx configuration
│   ├── nginx-production.conf       # Production config
│   ├── nginx.conf                  # Legacy/default (if needed)
│   └── ssl/                        # Certificates (volume mount)
│
├── docker-compose.yml              # Development compose file
├── docker-compose.production.yml   # Production compose file
│
├── .env.production.template        # Production env template
├── .env.development                # Development env (not committed)
│
├── data/                           # Persistent data (created at deployment)
│   ├── scan_reports/               # Scan results
│   ├── repos/                      # Repository cache
│   ├── uploads/                    # User uploads
│   ├── temp/                       # Temporary files
│   ├── ssl/                        # SSL certificates
│   └── logs/                       # Container logs
│
├── logs/                           # Logs directory structure
│   ├── nginx/                      # Nginx logs
│   ├── app/                        # Flask logs
│   └── scanner/                    # Scanner logs
│
├── scripts/                        # Deployment scripts
│   ├── ec2-setup.sh               # AWS EC2 setup script
│   ├── backup.sh                  # Backup script
│   └── renew-certs.sh             # Certificate renewal
│
├── PRODUCTION_DEPLOYMENT_GUIDE.md  # Main deployment doc
├── AWS_EC2_QUICK_START.md          # AWS quick start
└── DOCKER_ARCHITECTURE_GUIDE.md    # This file
```

---

## Build Process

### Flask Backend Build

```bash
# Build for production
docker build -f saas/Dockerfile.prod -t gvd-saas:1.0.0 saas/

# Build with multiple tags
docker build -f saas/Dockerfile.prod \
  -t gvd-saas:1.0.0 \
  -t gvd-saas:latest \
  saas/

# Build with custom Python version
docker build -f saas/Dockerfile.prod \
  --build-arg PYTHON_VERSION=3.11 \
  -t gvd-saas:1.0.0 \
  saas/
```

### Multi-Stage Build Explanation

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder
# - Installs build tools
# - Creates wheel files (faster installation in stage 2)
# - Larger image, but discarded in final output

# Stage 2: Runtime
FROM python:3.11-slim
# - Copies only wheels from builder
# - Installs runtime-only dependencies
# - Final image is much smaller
# - No build tools or header files included
```

**Size Optimization**:
- With multi-stage: ~350MB
- Without multi-stage: ~850MB

### Docker Compose Build

```bash
# Build all services
docker-compose -f docker-compose.production.yml build

# Build specific service
docker-compose -f docker-compose.production.yml build gvd-saas

# Build with no cache (clean build)
docker-compose -f docker-compose.production.yml build --no-cache

# Build and push to registry
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml push
```

---

## Runtime Configuration

### Environment Variables

#### Required

```bash
FLASK_ENV=production
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
FLASK_SECRET_KEY=your_secret_key
OAUTH_REDIRECT_URI=https://your-domain.com/callback
```

#### Optional

```bash
LOG_LEVEL=INFO
GUNICORN_WORKERS=9
REQUEST_TIMEOUT=300
ENABLE_BULK_SCAN=true
SCAN_TIMEOUT_SECONDS=300
```

### Configuration Precedence

1. Environment variables (highest priority)
2. `.env.production` file
3. Defaults in code (lowest priority)

### Startup Sequence

```
1. Docker Compose reads docker-compose.production.yml
2. Loads variables from .env.production
3. Checks required variables (fails if missing)
4. Creates/starts containers
5. Runs healthchecks
6. Waits for dependencies
```

### Healthchecks

Each container has healthchecks:

```yaml
# Nginx healthcheck
test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
interval: 30s
timeout: 10s
retries: 3
start_period: 10s

# Flask healthcheck
test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
interval: 30s
timeout: 10s
retries: 3
start_period: 15s
```

Status: `healthy`, `unhealthy`, or `starting`

---

## Networking

### Network Configuration

```yaml
networks:
  gvd-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.23.0.0/16
```

### Service Communication

```
Client (Internet)
  ↓ :80, :443 (public)
Nginx Container (172.23.0.2:80/443)
  ↓ :5000 (internal network only)
Flask Container (172.23.0.3:5000)

Scanner Container (172.23.0.4)
  ↓ shared volumes with Flask
Flask Container & Scanner Container (synchronized data)
```

### Port Mapping

| Container | Internal Port | Host Port | Access |
|-----------|---------------|-----------|--------|
| Nginx | 80 | 80 | Public HTTP |
| Nginx | 443 | 443 | Public HTTPS |
| Flask | 5000 | Not exposed | Internal only |
| Scanner | N/A | N/A | Internal only |

### DNS Resolution

Within Docker network:
- `nginx` → resolves to Nginx container
- `gvd-saas` → resolves to Flask container
- `gvd-scanner` → resolves to Scanner container

---

## Storage & Volumes

### Volume Types

#### Named Volumes (Managed by Docker)

```yaml
gvd-scan-reports:
  driver: local
  # Docker manages location (typically /var/lib/docker/volumes/...)
  # Good for: Data that doesn't need to be on host filesystem
```

#### Bind Mounts (Host Directory)

```yaml
gvd-scan-reports:
  driver: local
  driver_opts:
    type: none
    o: bind
    device: ./data/scan_reports
  # Maps to host directory ./data/scan_reports
  # Good for: Easy access from host, backups, development
```

### Volume Lifecycle

```
docker-compose up
  ↓
Create volumes if not exist
  ↓
Mount volumes into containers
  ↓
Containers read/write data
  ↓
docker-compose down
  ↓
Volumes persist (data not deleted)
  ↓
docker-compose up
  ↓
Previous data available in containers
```

### Backup Strategy

```bash
# Backup volume while container running
docker run --rm -v gvd-scan-reports:/data -v $(pwd):/backup \
  alpine tar czf /backup/scan-reports.tar.gz -C /data .

# Backup volume while container stopped
docker-compose -f docker-compose.production.yml down
docker run --rm -v gvd-scan-reports:/data -v $(pwd):/backup \
  alpine tar czf /backup/scan-reports.tar.gz -C /data .
docker-compose -f docker-compose.production.yml up -d
```

---

## Security Implementation

### 1. Container Security

**Non-root User**
```dockerfile
RUN groupadd -r gvd && useradd -r -g gvd gvd
USER gvd
```

**Read-only Filesystem** (optional)
```yaml
services:
  gvd-saas:
    read_only: true
    tmpfs:
      - /tmp
      - /run
```

**Dropped Capabilities** (optional)
```yaml
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```

### 2. Network Security

**No Ports Exposed**
- Flask container NOT exposed to host
- Only Nginx public-facing
- Internal network only communication

**Firewall Rules**
```bash
# UFW - Ubuntu Firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 3. Secrets Management

**Never in Git**
```bash
# Add to .gitignore
.env
.env.production
.env.*.local
*.key
*.pem
secrets/
```

**Environment Variables**
```bash
# Use env files (not committed)
# Or cloud secret manager (AWS Secrets Manager, HashiCorp Vault)
```

### 4. Image Security

**Minimal Base Images**
- `python:3.11-slim` (60MB vs 300MB for full image)
- `nginx:1.25-alpine` (40MB vs 100MB for debian)

**No Unnecessary Packages**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*
    # Only install what's needed
```

### 5. Supply Chain Security

**Image Scanning**
```bash
trivy image gvd-saas:latest
trivy image nginx:1.25-alpine
```

**Sign Images**
```bash
cosign sign your-registry/gvd-saas:latest
```

---

## Performance Considerations

### 1. Layer Caching

Dockerfile layer order matters:

```dockerfile
# Bad: Changes to code invalidate dependency cache
COPY . .
RUN pip install requirements.txt

# Good: Only rebuild if requirements.txt changes
COPY requirements.txt .
RUN pip install requirements.txt
COPY . .
```

### 2. Image Size Optimization

| Technique | Impact |
|-----------|--------|
| Multi-stage build | -50% |
| Minimal base image | -40% |
| .dockerignore | -30% |
| Remove build tools | -20% |
| Combined RUN commands | -5% |

### 3. Gunicorn Tuning

```python
# In gunicorn_config.py
workers = (2 * cpu_count) + 1  # Calculate based on CPUs
timeout = 300                   # For long scans
max_requests = 10000            # Prevent memory leaks
```

### 4. Nginx Optimization

```nginx
# In nginx-production.conf
sendfile on;           # Use kernel-level copy
tcp_nopush on;         # Combine packets
tcp_nodelay on;        # Disable Nagle's algorithm
keepalive_timeout 65;  # Reuse connections
```

### 5. Resource Limits

```yaml
services:
  gvd-saas:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 2G
        reservations:
          cpus: '2'
          memory: 1G
```

---

## Scaling Strategy

### Horizontal Scaling

```bash
# Scale Flask application
docker-compose -f docker-compose.production.yml up -d --scale gvd-saas=3

# Scale scanner
docker-compose -f docker-compose.production.yml up -d --scale gvd-scanner=5

# Manual scaling in compose file
services:
  gvd-saas:
    deploy:
      replicas: 3  # Run 3 instances
```

### Load Balancing

Nginx automatically load-balances between multiple Flask instances:

```nginx
upstream gvd_backend {
    least_conn;  # Load balance algorithm
    
    server gvd-saas:5000;      # Instance 1
    server gvd-saas:5001;      # Instance 2 (different port)
    server gvd-saas:5002;      # Instance 3 (different port)
}
```

### Kubernetes Migration

When ready for Kubernetes:

```bash
# Convert docker-compose to Kubernetes manifests
kompose convert -f docker-compose.production.yml

# Or use Helm charts
helm install gvd ./gvd-helm-chart
```

### Auto-Scaling (AWS ECS Example)

```bash
# Create ECS task definition from docker-compose
# Configure auto-scaling policy:
#  - Scale up: CPU > 70% for 2 minutes
#  - Scale down: CPU < 30% for 5 minutes
#  - Min tasks: 1
#  - Max tasks: 5
```

---

## Monitoring & Debugging

### View Logs

```bash
# All services
docker-compose -f docker-compose.production.yml logs

# Specific service
docker-compose -f docker-compose.production.yml logs gvd-saas

# Follow logs
docker-compose -f docker-compose.production.yml logs -f nginx

# Last 100 lines
docker-compose -f docker-compose.production.yml logs --tail=100
```

### Container Stats

```bash
# Real-time stats
docker stats

# Format output
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### Enter Container

```bash
# Execute command in running container
docker-compose -f docker-compose.production.yml exec gvd-saas bash

# Run one-off command
docker-compose -f docker-compose.production.yml exec gvd-saas python -c "print('test')"
```

### Port Mapping Verification

```bash
# Check port mapping
docker port gvd-nginx
# 443/tcp -> 0.0.0.0:443
# 80/tcp -> 0.0.0.0:80

# Check listening ports on host
sudo netstat -tlnp | grep -E ':80|:443'
```

---

## Troubleshooting Guide

### Images won't build

```bash
# Check Docker version
docker --version  # Should be 20.10+

# Check available disk space
df -h

# Build with verbose output
docker build --verbose -f Dockerfile.prod .

# Check Dockerfile syntax
docker build -f Dockerfile.prod --dry-run .
```

### Container won't start

```bash
# Check logs immediately
docker logs <container-id>

# Check environment variables
docker inspect <container-id> | grep -A 50 Env

# Check volumes
docker inspect <container-id> | grep -A 20 Mounts

# Try running manually
docker run -it gvd-saas:latest /bin/bash
```

### Network issues

```bash
# Check container network
docker network inspect gvd-network

# Test DNS resolution within container
docker-compose exec gvd-saas ping nginx
docker-compose exec gvd-saas curl http://gvd-saas:5000/health

# Check firewall
sudo ufw status
sudo iptables -L -n | head -20
```

---

## Conclusion

This architecture provides:

✅ **Production-Grade**: Enterprise security, performance, reliability
✅ **Scalable**: Horizontal scaling ready
✅ **Portable**: Works anywhere Docker runs
✅ **Maintainable**: Clear structure, good documentation
✅ **Efficient**: Optimized images, caching, resource usage
✅ **Observable**: Logging, health checks, metrics

For detailed deployment steps, see PRODUCTION_DEPLOYMENT_GUIDE.md
For AWS-specific steps, see AWS_EC2_QUICK_START.md

---

**Version**: 1.0.0
**Last Updated**: 2024
**Maintained By**: GVD Team
