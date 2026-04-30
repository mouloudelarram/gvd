# GVD Production Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the GVD (GitHub Vulnerability Detector) SaaS application to production environments.

## Prerequisites

### System Requirements
- **CPU**: Minimum 2 cores, recommended 4+ cores
- **Memory**: Minimum 4GB RAM, recommended 8GB+
- **Storage**: Minimum 20GB, recommended 100GB+ for repositories
- **OS**: Linux (Ubuntu 20.04+, CentOS 8+) or macOS/Windows for development
- **Docker**: Version 20.10+ and Docker Compose 2.0+
- **Git**: Version 2.25+

### External Services
- **GitHub OAuth Application**: Create at https://github.com/settings/developers
- **Domain Name**: For production deployment (optional)
- **SSL Certificate**: For HTTPS (recommended for production)

---

## Step 1: Environment Configuration

### 1.1 Clone Repository
```bash
git clone <your-repository-url>
cd gvd
```

### 1.2 Configure Environment Variables
```bash
# Copy example environment file
cp saas/.env.example saas/.env

# Edit the environment file
nano saas/.env
```

### 1.3 Required Environment Variables
```bash
# GitHub OAuth Configuration (Required)
GITHUB_CLIENT_ID=your_github_client_id_here
GITHUB_CLIENT_SECRET=your_github_client_secret_here
OAUTH_REDIRECT_URI=https://yourdomain.com/callback

# Flask Configuration (Required)
FLASK_SECRET_KEY=your_random_secret_key_here_change_in_production
FLASK_ENV=production

# Optional Configuration
ENABLE_BULK_SCAN=true
SCAN_TIMEOUT_SECONDS=300
MAX_REPOS_FETCH=1000
```

### 1.4 Generate Secure Keys
```bash
# Generate Flask secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate OAuth redirect URI example
# For development: http://localhost:5000/callback
# For production: https://yourdomain.com/callback
```

---

## Step 2: Development Setup & Testing

### 2.1 Local Development Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Flask app dependencies
cd saas
pip install -r requirements.txt

# Install CLI dependencies
cd ../cli
pip install -e .
cd ..

# Test CLI functionality
cd cli
python cli.py help
python cli.py init
python cli.py scan --path .. --output ./test-report

# Test Flask app imports
cd ../saas
python -c "import app; print('Flask app imports successfully')"
```

### 2.2 Verify CLI Reports
```bash
# Check generated reports
ls -la cli/test-report/
cat cli/test-report/report.json | jq '.total_findings'
```

### 2.3 Test GitHub OAuth Setup
1. Visit http://localhost:5000
2. Click "Login with GitHub"
3. Verify OAuth redirect works
4. Check dashboard loads correctly

---

## Step 3: Docker Deployment

### 3.1 Build Docker Images
```bash
# Build all services
docker-compose build

# Or build specific services
docker-compose build gvd-saas
docker-compose build gvd-cli
```

### 3.2 Development Deployment
```bash
# Start development stack
docker-compose up -d

# Check services status
docker-compose ps

# View logs
docker-compose logs -f gvd-saas
```

### 3.3 Production Deployment
```bash
# Use production configuration
docker-compose -f docker-compose.prod.yml up -d

# Verify all services are running
docker-compose -f docker-compose.prod.yml ps
```

---

## Step 4: Production Configuration

### 4.1 Nginx Configuration (Optional)
Create `nginx/nginx.conf`:
```nginx
events {
    worker_connections 1024;
}

http {
    upstream gvd_app {
        server gvd-saas:5000;
    }

    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        location / {
            proxy_pass http://gvd_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### 4.2 SSL Certificate Setup
```bash
# Create SSL directory
mkdir -p nginx/ssl

# Use Let's Encrypt (recommended)
certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/key.pem

# Or use self-signed certificate for testing
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem
```

### 4.3 Production Docker Compose
Update `docker-compose.prod.yml`:
```yaml
version: '3.8'

services:
  gvd-saas:
    build:
      context: ./saas
      dockerfile: Dockerfile
    environment:
      - FLASK_ENV=production
      - PYTHONPATH=/app
    env_file:
      - ./saas/.env
    volumes:
      - gvd_scan_reports:/app/scan_reports
      - gvd_repos:/app/repos
    depends_on:
      - gvd-cli
    restart: unless-stopped
    networks:
      - gvd-network

  gvd-cli:
    build:
      context: ./cli
      dockerfile: Dockerfile
    volumes:
      - gvd_cli:/app/dist
      - gvd_reports:/app/reports
    restart: unless-stopped
    networks:
      - gvd-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - gvd-saas
    restart: unless-stopped
    networks:
      - gvd-network

volumes:
  gvd_cli:
  gvd_reports:
  gvd_scan_reports:
  gvd_repos:

networks:
  gvd-network:
    driver: bridge
```

---

## Step 5: Monitoring & Maintenance

### 5.1 Health Checks
```bash
# Check application health
curl -f https://yourdomain.com/

# Check Docker service health
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml exec gvd-saas python -c "import app; print('OK')"
```

### 5.2 Log Monitoring
```bash
# View application logs
docker-compose -f docker-compose.prod.yml logs -f gvd-saas

# View CLI service logs
docker-compose -f docker-compose.prod.yml logs -f gvd-cli

# View Nginx logs
docker-compose -f docker-compose.prod.yml logs -f nginx
```

### 5.3 Performance Monitoring
```bash
# Monitor resource usage
docker stats

# Check disk space usage
df -h

# Monitor scan reports directory
du -sh saas/scan_reports/
```

---

## Step 6: Backup & Recovery

### 6.1 Data Backup Strategy
```bash
# Create backup script
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/gvd"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup scan reports
docker run --rm -v gvd_scan_reports:/data -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/scan_reports_$DATE.tar.gz -C /data .

# Backup repositories
docker run --rm -v gvd_repos:/data -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/repos_$DATE.tar.gz -C /data .

# Backup configuration
cp saas/.env $BACKUP_DIR/env_$DATE.backup

echo "Backup completed: $DATE"
EOF

chmod +x backup.sh
```

### 6.2 Automated Backups
```bash
# Add to crontab for daily backups
crontab -e

# Add line for daily backup at 2 AM
0 2 * * * /path/to/gvd/backup.sh
```

### 6.3 Recovery Procedure
```bash
# Restore scan reports
docker run --rm -v gvd_scan_reports:/data -v /backup/gvd:/backup \
  alpine tar xzf /backup/scan_reports_YYYYMMDD_HHMMSS.tar.gz -C /data

# Restore repositories
docker run --rm -v gvd_repos:/data -v /backup/gvd:/backup \
  alpine tar xzf /backup/repos_YYYYMMDD_HHMMSS.tar.gz -C /data

# Restore configuration
cp /backup/gvd/env_YYYYMMDD_HHMMSS.backup saas/.env
```

---

## Step 7: Scaling & Performance

### 7.1 Horizontal Scaling
```yaml
# Update docker-compose.prod.yml for multiple app instances
services:
  gvd-saas:
    build:
      context: ./saas
      dockerfile: Dockerfile
    deploy:
      replicas: 3
    # ... rest of configuration
```

### 7.2 Resource Optimization
```yaml
# Add resource limits
services:
  gvd-saas:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

### 7.3 Database Scaling (Future Enhancement)
Consider adding Redis for session storage and PostgreSQL for persistent data in high-traffic scenarios.

---

## Step 8: Security Hardening

### 8.1 Firewall Configuration
```bash
# Configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5000/tcp  # Block direct Flask access
```

### 8.2 Security Headers
Add to Flask app or Nginx configuration:
```nginx
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
```

### 8.3 Rate Limiting
Consider implementing rate limiting for API endpoints using Flask-Limiter or Nginx rate limiting.

---

## Troubleshooting

### Common Issues

#### 1. OAuth Callback Fails
```bash
# Check OAuth configuration
echo "Client ID: $GITHUB_CLIENT_ID"
echo "Redirect URI: $OAUTH_REDIRECT_URI"

# Verify GitHub OAuth app settings
# Ensure callback URL matches exactly
```

#### 2. Scanner Not Working
```bash
# Check CLI executable
docker-compose -f docker-compose.prod.yml exec gvd-saas ls -la /app/cli/dist/

# Test CLI manually
docker-compose -f docker-compose.prod.yml exec gvd-saas python /app/cli/cli.py help
```

#### 3. High Memory Usage
```bash
# Monitor memory usage
docker stats

# Clean up old scan reports
find saas/scan_reports -type d -mtime +7 -exec rm -rf {} +
```

#### 4. Repository Cloning Issues
```bash
# Check Git installation
docker-compose -f docker-compose.prod.yml exec gvd-saas git --version

# Verify GitHub token permissions
curl -H "Authorization: token $GITHUB_CLIENT_SECRET" https://api.github.com/user
```

### Log Analysis
```bash
# Filter error logs
docker-compose -f docker-compose.prod.yml logs gvd-saas | grep ERROR

# Monitor scan progress
docker-compose -f docker-compose.prod.yml logs gvd-saas | grep "scan"
```

---

## Performance Optimization

### Database Optimization
- Implement Redis for session storage
- Add PostgreSQL for persistent data
- Configure connection pooling

### Caching Strategy
- Cache GitHub API responses
- Implement CDN for static assets
- Use browser caching headers

### Monitoring Setup
- Set up Prometheus + Grafana
- Configure alerting for critical errors
- Monitor response times and throughput

---

## Conclusion

Following this deployment guide will result in a production-ready GVD SaaS application with:

- ✅ Secure OAuth authentication
- ✅ Scalable architecture
- ✅ Proper monitoring and logging
- ✅ Backup and recovery procedures
- ✅ Security hardening
- ✅ Performance optimization

The application is now ready for production use and can handle enterprise-level security scanning workloads.

For ongoing maintenance:
1. Regularly update dependencies
2. Monitor security advisories
3. Backup data regularly
4. Monitor performance metrics
5. Test disaster recovery procedures

For support and issues, refer to the troubleshooting section or check the application logs for detailed error information.
