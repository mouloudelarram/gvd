# GVD PRODUCTION DEPLOYMENT GUIDE

> Enterprise-Grade Containerization for Git Vulnerability Detector
> 
> AWS EC2 Ready | VPS Ready | Cloud-Native | Production-Grade

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Local Development Setup](#local-development-setup)
4. [Staging Environment](#staging-environment)
5. [AWS EC2 Deployment](#aws-ec2-deployment)
6. [VPS Deployment](#vps-deployment)
7. [Configuration Management](#configuration-management)
8. [SSL/TLS Setup](#ssltls-setup)
9. [Monitoring & Logging](#monitoring--logging)
10. [Troubleshooting](#troubleshooting)
11. [Security Hardening](#security-hardening)
12. [Performance Tuning](#performance-tuning)
13. [Scaling & Load Balancing](#scaling--load-balancing)
14. [Backup & Disaster Recovery](#backup--disaster-recovery)

---

## Architecture Overview

### Production Stack

```
Internet (Client)
     ↓
[Nginx Reverse Proxy] (Port 80/443)
     ↓ (Internal Network)
[Gunicorn + Flask] (Port 5000)
     ↓
[Named Volumes - Persistent Storage]
```

### Container Services

| Service | Purpose | Image | Replicas |
|---------|---------|-------|----------|
| **nginx** | Reverse proxy, SSL/TLS termination, static serving | `nginx:1.25-alpine` | 1 |
| **gvd-saas** | Flask backend with Gunicorn WSGI server | `python:3.11-slim` (custom build) | 1-N (scalable) |
| **gvd-scanner** | Background CLI scanner for vulnerability analysis | `python:3.11-slim` (custom build) | 1-N (scalable) |
| **certbot** (optional) | Automatic SSL certificate management | `certbot/certbot` | 1 |

### Network Architecture

- **Internal Network**: `172.23.0.0/16` (isolated bridge network)
- **Exposed Ports**: 80 (HTTP), 443 (HTTPS)
- **Internal Ports**: 5000 (Flask/Gunicorn)

### Storage Strategy

| Volume | Purpose | Mount Path | Persistence |
|--------|---------|------------|-------------|
| `gvd-scan-reports` | Scan results and reports | `/app/scan_reports` | Persistent |
| `gvd-repos` | Cloned GitHub repositories | `/app/repos` | Persistent |
| `gvd-uploads` | User uploads | `/app/uploads` | Persistent |
| `gvd-temp` | Temporary files | `/app/temp` | Persistent |
| `gvd-app-logs` | Application logs | `/app/logs` | Persistent |
| `gvd-scanner-logs` | Scanner logs | `/app/logs` | Persistent |
| `gvd-nginx-logs` | Nginx logs | `/var/log/nginx` | Persistent |
| `gvd-ssl-certs` | SSL certificates | `/etc/nginx/ssl` | Persistent |

---

## Pre-Deployment Checklist

### Prerequisites

- [ ] Docker Engine 20.10+ installed
- [ ] Docker Compose 2.0+ installed
- [ ] Git installed
- [ ] GitHub OAuth App created (https://github.com/settings/developers)
- [ ] Domain name (for production)
- [ ] SSL certificate or Let's Encrypt account
- [ ] AWS EC2 instance or VPS (for production)
- [ ] Sufficient disk space (recommend 100GB+ for repos)
- [ ] Sufficient memory (recommend 4GB+ for production)

### Required Information

Collect these before deployment:

```
GitHub OAuth:
- Client ID: ___________________
- Client Secret: ___________________

Production Domain:
- Domain name: ___________________
- Subdomain: ___________________

AWS/VPS Details:
- Instance/Server IP: ___________________
- SSH Key: ___________________
- Region/Location: ___________________

Security:
- Flask Secret Key: ___________________
  (Generate: python -c "import secrets; print(secrets.token_urlsafe(32))")
```

---

## Local Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-org/gvd.git
cd gvd
```

### 2. Create Development Environment File

```bash
cp .env.example .env.development

# Edit with your GitHub OAuth credentials
nano .env.development
```

### 3. Build Development Images

```bash
docker-compose build
```

### 4. Start Development Environment

```bash
# Development mode (with live reload)
docker-compose up -d

# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f gvd-saas
docker-compose logs -f nginx
```

### 5. Verify Services

```bash
# Health check
curl http://localhost/health

# Access web interface
open http://localhost

# Check Flask app directly
curl -i http://localhost:5000/

# Check Nginx status
docker-compose exec nginx nginx -s reload
```

### 6. Running CLI Scans (Local Development)

```bash
# Execute CLI in running container
docker-compose exec gvd-scanner python cli.py scan --path /app/repos --output /app/reports

# Or build and run scanner standalone
docker build -f cli/Dockerfile.prod -t gvd-scanner:local ./cli
docker run -v $(pwd)/data/repos:/app/repos -v $(pwd)/data/reports:/app/reports gvd-scanner:local python cli.py scan --path /app/repos --output /app/reports
```

### 7. Database Initialization (if needed)

```bash
# Run migrations
docker-compose exec gvd-saas python -c "from app import create_app; app = create_app(); app.app_context().push()"

# Or with Flask CLI
docker-compose exec gvd-saas flask db upgrade
```

### 8. Stop Development Environment

```bash
docker-compose down

# Stop and remove volumes (full cleanup)
docker-compose down -v
```

---

## Staging Environment

### 1. Create Staging Directory

```bash
mkdir gvd-staging
cd gvd-staging
git clone https://github.com/your-org/gvd.git .
```

### 2. Create Staging Configuration

```bash
cp .env.production.template .env.staging

# Edit staging environment
nano .env.staging

# Update with:
FLASK_ENV=staging
OAUTH_REDIRECT_URI=https://staging.your-domain.com/callback
DEBUG=false
```

### 3. Create Staging Directory Structure

```bash
mkdir -p data/{scan_reports,repos,uploads,temp,ssl} logs/{nginx,app,scanner}
chmod 755 data logs
```

### 4. Build Staging Images

```bash
docker-compose -f docker-compose.production.yml build
```

### 5. Start Staging Environment

```bash
docker-compose -f docker-compose.production.yml up -d
```

### 6. Monitor Staging Deployment

```bash
# Check all services
docker-compose -f docker-compose.production.yml ps

# Check health
curl https://staging.your-domain.com/health

# View logs
docker-compose -f docker-compose.production.yml logs -f
```

---

## AWS EC2 Deployment

### 1. Launch EC2 Instance

#### Recommended Configuration

```
Instance Type: t3.medium or t3.large (2-4 vCPU, 4-8GB RAM)
OS: Ubuntu 22.04 LTS (Canonical)
Root Volume: gp3, 100GB (faster, more IOPS than gp2)
Security Groups:
  - Inbound: HTTP (80), HTTPS (443), SSH (22) from your IP
  - Outbound: All
VPC: Default VPC is fine
Public IP: Auto-assign enabled
```

#### Via AWS Console

1. Go to EC2 → Launch Instance
2. Select "Ubuntu 22.04 LTS"
3. Select `t3.medium` instance type
4. Configure security group:
   - HTTP (80): 0.0.0.0/0
   - HTTPS (443): 0.0.0.0/0
   - SSH (22): Your IP/0.0.0.0/0
5. Create/select key pair
6. Launch

### 2. Connect to EC2 Instance

```bash
ssh -i /path/to/key.pem ubuntu@your-ec2-ip

# Update system
sudo apt update && sudo apt upgrade -y
```

### 3. Install Docker & Docker Compose

```bash
# Remove old Docker versions
sudo apt remove docker docker-engine docker.io containerd runc -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker
docker --version

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify Docker Compose
docker-compose --version
```

### 4. Clone Repository

```bash
cd /opt
sudo git clone https://github.com/your-org/gvd.git
sudo chown -R $USER:$USER gvd
cd gvd
```

### 5. Create Directory Structure

```bash
mkdir -p data/{scan_reports,repos,uploads,temp,ssl} logs/{nginx,app,scanner}
chmod 755 data logs
```

### 6. Configure Environment

```bash
# Copy production template
cp .env.production.template .env.production

# Edit with production values
nano .env.production

# Secure the file
chmod 600 .env.production
```

### 7. Configure SSL Certificate

#### Option A: Let's Encrypt (Automated - Recommended)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Create SSL directory
sudo mkdir -p /opt/gvd/data/ssl

# Generate certificate
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Copy certificate to Docker volume
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem
sudo chown 1000:1000 data/ssl/cert.pem data/ssl/key.pem
```

#### Option B: Self-Signed Certificate (Testing Only)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes -out data/ssl/cert.pem -keyout data/ssl/key.pem -days 365
chmod 644 data/ssl/cert.pem
chmod 600 data/ssl/key.pem
```

### 8. Start Production Deployment

```bash
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# Verify services
docker-compose -f docker-compose.production.yml ps
```

### 9. Verify Deployment

```bash
# Check health
curl https://your-domain.com/health -k

# Check services
curl https://your-domain.com/ -k

# View logs
docker-compose -f docker-compose.production.yml logs -f gvd-saas
```

### 10. Enable Automatic Startup

```bash
# Make Docker start on boot
sudo systemctl enable docker

# Create a systemd service for GVD
sudo tee /etc/systemd/system/gvd.service > /dev/null <<EOF
[Unit]
Description=GVD Docker Compose Application
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/gvd
ExecStart=/usr/local/bin/docker-compose -f docker-compose.production.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.production.yml down
User=$USER

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
sudo systemctl daemon-reload
sudo systemctl enable gvd.service
```

### 11. Setup Automatic Certificate Renewal

```bash
# Create renewal hook
sudo mkdir -p /opt/gvd/scripts
sudo tee /opt/gvd/scripts/renew-certs.sh > /dev/null <<'EOF'
#!/bin/bash
certbot renew --quiet
if [ -f /etc/letsencrypt/live/your-domain.com/fullchain.pem ]; then
    cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/gvd/data/ssl/cert.pem
    cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/gvd/data/ssl/key.pem
    docker-compose -f /opt/gvd/docker-compose.production.yml exec nginx nginx -s reload || true
fi
EOF

sudo chmod +x /opt/gvd/scripts/renew-certs.sh

# Add to crontab
sudo tee /etc/cron.d/gvd-certbot > /dev/null <<'EOF'
0 2 * * * /opt/gvd/scripts/renew-certs.sh >> /var/log/gvd-certbot.log 2>&1
EOF
```

---

## VPS Deployment

VPS deployment is similar to AWS EC2. Key differences:

### 1. VPS Provider Setup

Choose a provider:
- Linode
- DigitalOcean
- Hetzner
- Vultr
- OVH

### 2. Create VPS Instance

```
Specs:
- RAM: 4GB minimum (8GB recommended)
- vCPU: 2-4
- Storage: 100GB SSD
- Bandwidth: Unlimited or 5TB+
- OS: Ubuntu 22.04 LTS
```

### 3. Follow EC2 Instructions

The Docker installation and GVD deployment steps are identical to AWS EC2.

### 4. VPS-Specific Considerations

```bash
# Monitor resources more closely on limited VPS
docker stats

# Set memory limits
docker-compose -f docker-compose.production.yml update --memory=2g gvd-saas

# Enable swap if needed (only as last resort)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Configuration Management

### Environment Variables

#### Required Variables

```bash
# GitHub OAuth (mandatory)
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# Flask Security (mandatory)
FLASK_SECRET_KEY=your_secret_key

# Application Environment
FLASK_ENV=production|staging|development

# OAuth Redirect
OAUTH_REDIRECT_URI=https://your-domain.com/callback
```

#### Optional Variables

```bash
# Feature Flags
ENABLE_BULK_SCAN=true
ENABLE_PDF_REPORTS=true

# Limits
SCAN_TIMEOUT_SECONDS=300
MAX_REPOS_FETCH=1000

# Performance
GUNICORN_WORKERS=9
REQUEST_TIMEOUT=300

# Logging
LOG_LEVEL=INFO|DEBUG
LOG_FORMAT=json|text

# Security
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_HTTPONLY=true
```

### Configuration Best Practices

1. **Never commit secrets to Git**
   ```bash
   # Add to .gitignore
   .env
   .env.production
   .env.*.local
   *.key
   *.pem
   ```

2. **Use environment-specific files**
   ```bash
   .env.development  # Development local
   .env.staging      # Staging environment
   .env.production   # Production (never commit)
   ```

3. **Rotate secrets regularly**
   ```bash
   # Generate new secret
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   
   # Update in environment
   # Restart services
   docker-compose -f docker-compose.production.yml restart gvd-saas
   ```

4. **Use secrets management (for production)**
   - AWS Secrets Manager
   - HashiCorp Vault
   - Azure Key Vault
   - Docker Secrets (for Swarm)

---

## SSL/TLS Setup

### Automatic Setup with Let's Encrypt

```bash
# Install Certbot
sudo apt install certbot -y

# Generate certificate
sudo certbot certonly --standalone -d your-domain.com

# Copy to Docker volume
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem
```

### Manual Renewal

```bash
# Renew certificate
sudo certbot renew

# Update Docker volumes
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem

# Reload Nginx
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload
```

### Certificate Pinning

For enhanced security, enable certificate pinning in Nginx:

```nginx
# In nginx-production.conf, uncomment and update:
add_header Public-Key-Pins 'pin-sha256="..."; pin-sha256="..."; max-age=31536000' always;
```

---

## Monitoring & Logging

### Container Logs

```bash
# All services
docker-compose -f docker-compose.production.yml logs -f

# Specific service
docker-compose -f docker-compose.production.yml logs -f gvd-saas

# Last 100 lines
docker-compose -f docker-compose.production.yml logs --tail=100

# Follow Nginx
docker-compose -f docker-compose.production.yml logs -f nginx
```

### Log Files

```bash
# Flask application logs
tail -f logs/app/gvd.log

# Nginx logs
tail -f logs/nginx/access.log
tail -f logs/nginx/error.log

# Scanner logs
tail -f logs/scanner/scanner.log
```

### Container Monitoring

```bash
# Real-time stats
docker stats

# Inspect container
docker inspect gvd-saas

# Container info
docker ps -a
docker images
```

### Health Checks

```bash
# Manual health checks
curl https://your-domain.com/health -k

# Detailed health check
docker-compose -f docker-compose.production.yml exec gvd-saas curl http://localhost:5000/health
```

### Prometheus Monitoring (Optional)

```bash
# Add Prometheus service to docker-compose.yml
# Configure Nginx to expose metrics
# Enable application metrics export
```

---

## Troubleshooting

### Common Issues

#### 1. Nginx Returns 502 Bad Gateway

**Symptoms**: `502 Bad Gateway` errors

**Solutions**:
```bash
# Check if Flask is running
docker-compose -f docker-compose.production.yml ps

# Check Flask logs
docker-compose -f docker-compose.production.yml logs gvd-saas

# Restart Flask service
docker-compose -f docker-compose.production.yml restart gvd-saas

# Check Nginx configuration
docker-compose -f docker-compose.production.yml exec nginx nginx -t

# Check network connectivity
docker-compose -f docker-compose.production.yml exec nginx ping gvd-saas
```

#### 2. SSL Certificate Errors

**Symptoms**: `SSL_ERROR_UNKNOWN_CA` or certificate warnings

**Solutions**:
```bash
# Verify certificate paths
ls -la data/ssl/

# Check certificate validity
openssl x509 -in data/ssl/cert.pem -text -noout | grep -E "Issuer|Subject|Valid"

# Regenerate self-signed (testing only)
openssl req -x509 -newkey rsa:4096 -nodes -out data/ssl/cert.pem -keyout data/ssl/key.pem -days 365

# Update Let's Encrypt certificate
sudo certbot renew --force-renewal
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem data/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem data/ssl/key.pem

# Reload Nginx
docker-compose -f docker-compose.production.yml exec nginx nginx -s reload
```

#### 3. Out of Memory

**Symptoms**: Services crash, Docker complains about memory

**Solutions**:
```bash
# Check memory usage
docker stats

# Reduce worker count
# Edit .env or docker-compose.yml
GUNICORN_WORKERS=4

# Reduce container memory limits
# Update deploy.resources.limits in docker-compose.yml

# Restart services
docker-compose -f docker-compose.production.yml restart

# Clean up old images
docker system prune -a
```

#### 4. Slow Response Times

**Symptoms**: Pages take long to load

**Solutions**:
```bash
# Check server resources
docker stats

# Increase workers
GUNICORN_WORKERS=9

# Enable Gzip compression (already enabled in Nginx)

# Check database queries (if applicable)
docker-compose -f docker-compose.production.yml logs gvd-saas | grep slow

# Optimize Nginx caching
# Already configured in nginx-production.conf

# Scale horizontally
# Add more gvd-saas instances to docker-compose.yml
```

#### 5. Container Won't Start

**Symptoms**: Container exits immediately

**Solutions**:
```bash
# Check logs
docker-compose -f docker-compose.production.yml logs gvd-saas

# Check environment variables
docker-compose -f docker-compose.production.yml exec gvd-saas env

# Verify required directories exist
ls -la data/

# Check file permissions
ls -la saas/ cli/

# Try rebuilding
docker-compose -f docker-compose.production.yml build --no-cache
```

#### 6. Git Clone Fails in Containers

**Symptoms**: Scanning fails due to git errors

**Solutions**:
```bash
# Verify git is installed
docker-compose -f docker-compose.production.yml exec gvd-scanner which git

# Check git configuration in container
docker-compose -f docker-compose.production.yml exec gvd-scanner git --version

# Test git clone manually
docker-compose -f docker-compose.production.yml exec gvd-scanner git clone https://github.com/test/repo.git /tmp/test

# Check SSH keys (if using SSH URLs)
docker-compose -f docker-compose.production.yml exec gvd-scanner ls ~/.ssh/
```

---

## Security Hardening

### 1. Network Security

```bash
# Restrict Nginx to internal network only (if behind ALB/load balancer)
# Edit docker-compose.yml
expose:
  - "5000"  # Don't expose 5000 to host

# Only expose Nginx ports
ports:
  - "80:80"
  - "443:443"
```

### 2. Container Security

```bash
# Run containers as non-root (already configured)
USER gvd

# Use read-only root filesystem (if possible)
# Add to docker-compose.yml services:
read_only: true
tmpfs:
  - /tmp
  - /run

# Drop unnecessary Linux capabilities
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE
```

### 3. Secrets Management

```bash
# Never use environment variables for sensitive data
# Use Docker secrets or external secret manager

# For AWS:
# Use AWS Secrets Manager
# Update compose file to mount secrets from AWS

# For HashiCorp Vault:
# Configure Vault integration
# Auto-rotate credentials
```

### 4. Image Security

```bash
# Use signed images
docker pull --disable-content-trust=false nginx:1.25-alpine

# Scan images for vulnerabilities
trivy image nginx:1.25-alpine
trivy image gvd-saas:latest

# Sign your own images
cosign sign your-registry/gvd-saas:latest
```

### 5. Access Control

```bash
# Restrict SSH access
sudo ufw allow 22/tcp  # Only from your IP
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Use SSH key pairs (no password authentication)
# Disable password authentication in sshd

# Enable sudo password prompts
sudo visudo  # Review sudo rules

# Monitor access
sudo tail -f /var/log/auth.log
```

### 6. Regular Updates

```bash
# Update OS packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml build --no-cache

# Update Python dependencies
# Rebuild Docker images with latest requirements
```

---

## Performance Tuning

### Gunicorn Optimization

```python
# In gunicorn_config.py - already optimized for:

# Worker count: (2 * CPU_CORES) + 1
workers = (2 * multiprocessing.cpu_count()) + 1

# Connection limits
worker_connections = 1000

# Timeouts
timeout = 300  # For long scans

# Memory management
max_requests = 10000  # Restart workers
max_requests_jitter = 1000

# Socket settings
backlog = 2048
```

### Nginx Optimization

```nginx
# Already configured in nginx-production.conf for:

# Buffer optimization
proxy_buffer_size 128k
proxy_buffers 4 256k

# Connection reuse
keepalive_requests 100
keepalive_timeout 65

# Compression
gzip on
gzip_comp_level 6

# Caching
expires 30d
add_header Cache-Control "public, immutable"
```

### Linux Kernel Tuning

```bash
# For high-traffic production:
sudo tee /etc/sysctl.d/99-gvd.conf > /dev/null <<EOF
# TCP tuning
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_tw_reuse = 1

# File limits
fs.file-max = 2097152
EOF

# Apply settings
sudo sysctl -p /etc/sysctl.d/99-gvd.conf

# Check limits
ulimit -n  # Should show 65535 or higher
```

### Database Query Optimization (if applicable)

```bash
# Enable query logging
# Review slow queries
# Add database indexes
# Monitor with:
docker-compose -f docker-compose.production.yml logs gvd-saas | grep "slow query"
```

---

## Scaling & Load Balancing

### Horizontal Scaling

```bash
# Scale to multiple Flask instances:
docker-compose -f docker-compose.production.yml up -d --scale gvd-saas=3

# Scale to multiple scanner instances:
docker-compose -f docker-compose.production.yml up -d --scale gvd-scanner=5
```

### AWS Load Balancing (ALB/NLB)

```bash
# 1. Create Application Load Balancer in AWS
# 2. Create target group pointing to EC2 instance on port 80/443
# 3. Update security group to allow ALB traffic
# 4. Update Nginx to accept traffic from ALB

# In Nginx config:
# Trust X-Forwarded-For headers from ALB
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for
```

### Auto-Scaling (Kubernetes Alternative)

```bash
# For AWS ECS:
# 1. Create ECS task definition from docker-compose
# 2. Set up auto-scaling based on CPU/Memory
# 3. Use ECS Service with load balancer

# For local Kubernetes:
kubectl apply -f k8s/gvd-deployment.yaml
kubectl autoscale deployment gvd-saas --min=1 --max=5
```

---

## Backup & Disaster Recovery

### Backup Strategy

```bash
# Backup application data
docker run --rm \
  -v gvd-scan-reports:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/scan-reports-$(date +%s).tar.gz -C /data .

# Backup all volumes
for volume in gvd-scan-reports gvd-repos gvd-uploads gvd-temp; do
  docker run --rm \
    -v $volume:/data \
    -v $(pwd)/backups:/backup \
    alpine tar czf /backup/${volume}-$(date +%s).tar.gz -C /data .
done
```

### Automated Backups

```bash
# Create backup script
sudo tee /opt/gvd/scripts/backup.sh > /dev/null <<'EOF'
#!/bin/bash
BACKUP_DIR=/opt/gvd/backups
mkdir -p $BACKUP_DIR

for volume in gvd-scan-reports gvd-repos gvd-uploads; do
  docker run --rm \
    -v $volume:/data \
    -v $BACKUP_DIR:/backup \
    alpine tar czf /backup/${volume}-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
done

# Keep only last 30 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF

# Schedule with cron
sudo crontab -e
# Add: 0 2 * * * /opt/gvd/scripts/backup.sh
```

### Restore from Backup

```bash
# Restore volume from backup
docker volume create gvd-scan-reports-restored

docker run --rm \
  -v gvd-scan-reports-restored:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/scan-reports-XXXXX.tar.gz -C /data

# Verify restoration
docker run --rm \
  -v gvd-scan-reports-restored:/data \
  alpine ls /data
```

---

## Maintenance & Operations

### Regular Maintenance

```bash
# Weekly
- Review logs for errors
- Check disk space
- Verify backups completed
- Test health checks

# Monthly
- Update OS packages
- Update Docker images
- Review security updates
- Test disaster recovery

# Quarterly
- Review performance metrics
- Update documentation
- Capacity planning
- Security audit
```

### Monitoring Checklist

```bash
# Create monitoring dashboard with:
- CPU usage (target < 70%)
- Memory usage (target < 80%)
- Disk usage (alert at 85%)
- Network I/O
- Request latency
- Error rates
- SSL certificate expiry
```

### Emergency Procedures

```bash
# Service crash
docker-compose -f docker-compose.production.yml restart

# Database corruption (if applicable)
# Restore from backup
docker volume rm gvd-scan-reports
docker run --rm -v gvd-scan-reports:/data -v $(pwd)/backups:/backup alpine tar xzf /backup/latest.tar.gz -C /data

# Data loss
# Restore from backup to secondary system
# Verify data integrity
# Switch to secondary

# Security breach
# 1. Isolate affected system
# 2. Rotate all credentials
# 3. Review logs for access patterns
# 4. Scan for malware
# 5. Deploy new instances
```

---

## Conclusion

You now have a production-ready containerized deployment of GVD that is:

✅ **Production-Grade**: Enterprise-level security, performance, and reliability
✅ **Portable**: Works on AWS EC2, VPS, local machines, and future Kubernetes
✅ **Scalable**: Supports horizontal scaling of services
✅ **Secure**: Non-root containers, security headers, rate limiting
✅ **Observable**: Comprehensive logging and monitoring
✅ **Maintainable**: Clear documentation and automation
✅ **Resilient**: Health checks, automatic restarts, backup strategies

For questions or support, refer to the troubleshooting section or review the architecture documentation.

---

**Document Version**: 1.0.0
**Last Updated**: 2024
**Maintained By**: GVD Team
