# Docker Setup for GVD

This guide explains how to run GVD (GitHub Vulnerability Detector) using Docker and Docker Compose.

## Overview

GVD consists of two main components:
- **SaaS Web App**: Flask-based web interface for GitHub OAuth and repository management
- **CLI Scanner**: Python package for scanning Git repositories for vulnerabilities

The Docker setup provides:
- Containerized development environment
- Production-ready deployment
- Easy portability across systems
- Volume persistence for reports and repositories

## Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- Docker Compose (included with Docker Desktop)
- GitHub OAuth application credentials

## Quick Start

### 1. Environment Setup

Create a `.env` file in the `saas/` directory:

```bash
# saas/.env
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
FLASK_SECRET_KEY=your_flask_secret_key
```

### 2. Development Setup

Run the full application stack:

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d --build
```

### 3. Access the Application

- **Web Interface**: http://localhost:5000
- **CLI Scanner**: Use the CLI container directly

## Docker Compose Services

### gvd-saas (Web Application)

- **Port**: 5000
- **Environment**: Production Flask app
- **Volumes**: 
  - `./saas/scan_reports:/app/scan_reports` - Scan reports
  - `./saas/repos:/app/repos` - Cloned repositories
  - `gvd_cli:/app/cli/dist` - CLI executable shared volume

### gvd-cli (Scanner Service)

- **Purpose**: Provides CLI scanner functionality
- **Volumes**:
  - `gvd_cli:/app/dist` - CLI executable output
  - `gvd_reports:/app/reports` - Report storage
- **Profile**: `cli` (optional, only built when needed)

### nginx (Reverse Proxy) - Optional

- **Purpose**: Production-grade reverse proxy
- **Ports**: 80, 443
- **Profile**: `production` (only included in production profile)

## Usage Examples

### Development Workflow

```bash
# Start development environment
docker-compose up --build

# View logs
docker-compose logs -f gvd-saas

# Stop services
docker-compose down
```

### CLI Scanner Usage

```bash
# Run CLI commands directly
docker-compose run --rm gvd-cli gvd scan --path /path/to/repo

# Or access the CLI container
docker-compose exec gvd-cli gvd help
```

### Production Deployment

```bash
# Deploy with nginx reverse proxy
docker-compose --profile production up -d --build

# Scale web application (if needed)
docker-compose up -d --scale gvd-saas=2
```

## Volume Management

### Persistent Data

- **Scan Reports**: Stored in `./saas/scan_reports/`
- **Repositories**: Stored in `./saas/repos/`
- **CLI Executable**: Shared via Docker volume `gvd_cli`
- **Report Storage**: Managed via Docker volume `gvd_reports`

### Backup Important Data

```bash
# Backup scan reports
docker run --rm -v gvd_reports:/data -v $(pwd):/backup alpine tar czf /backup/reports-backup.tar.gz -C /data .

# Restore scan reports
docker run --rm -v gvd_reports:/data -v $(pwd):/backup alpine tar xzf /backup/reports-backup.tar.gz -C /data
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GITHUB_CLIENT_ID` | GitHub OAuth App Client ID | Yes |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App Client Secret | Yes |
| `FLASK_SECRET_KEY` | Flask session secret key | Yes |
| `FLASK_ENV` | Flask environment (production/development) | No |
| `PYTHONPATH` | Python path configuration | No |

### Custom Configuration

For custom nginx configuration:

```bash
# Create nginx config
mkdir -p nginx
# Add your nginx.conf to nginx/
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Check what's using port 5000
   netstat -tulpn | grep :5000
   # Or use different port
   docker-compose up --scale gvd-saas=1 -p 5001:5000
   ```

2. **Permission Issues**
   ```bash
   # Fix volume permissions on Linux
   sudo chown -R $USER:$USER ./saas/
   ```

3. **Build Failures**
   ```bash
   # Clean build
   docker-compose down
   docker system prune -f
   docker-compose build --no-cache
   ```

### Debug Mode

```bash
# Run with debug logging
docker-compose up --build --force-recreate

# Access container shell
docker-compose exec gvd-saas bash
docker-compose exec gvd-cli bash
```

### Health Checks

Monitor service health:

```bash
# Check service status
docker-compose ps

# View health check logs
docker inspect gvd-saas | grep Health -A 10
```

## Performance Optimization

### Build Optimization

- Use `.dockerignore` files to reduce build context
- Multi-stage builds for smaller images
- Layer caching with proper COPY order

### Runtime Optimization

```bash
# Limit resource usage
docker-compose up -d --build --memory=2g --cpus=1.0

# Use production-ready images
docker-compose -f docker-compose.prod.yml up -d
```

## Security Considerations

### Best Practices

1. **Environment Variables**: Never commit `.env` files
2. **Base Images**: Use official, minimal base images
3. **Network Isolation**: Services run in isolated network
4. **Volume Security**: Restrict volume permissions
5. **Regular Updates**: Keep base images updated

### Production Hardening

```bash
# Run with non-root user (modify Dockerfiles)
# Add security scanning
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image gvd-saas
```

## Advanced Usage

### Custom Networks

```yaml
# docker-compose.override.yml
version: '3.8'
services:
  gvd-saas:
    networks:
      - gvd-network
      - external-network

networks:
  external-network:
    external: true
```

### Service Dependencies

```bash
# Wait for services to be ready
docker-compose run --rm gvd-cli gvd scan --path /app/test-repo
```

### Monitoring

```bash
# Add monitoring (optional)
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

## Migration from Local Setup

If you're migrating from a local Python setup:

1. **Export Existing Data**:
   ```bash
   # Backup scan reports
   cp -r ~/gvd-reports ./saas/scan_reports/
   ```

2. **Update Configuration**:
   - Move environment variables to `.env` file
   - Update paths in configuration files

3. **Test Migration**:
   ```bash
   docker-compose up --build
   # Verify all functionality works
   ```

## Support

For Docker-specific issues:

1. Check Docker logs: `docker-compose logs`
2. Verify container status: `docker-compose ps`
3. Test individual services: `docker-compose run --rm <service>`

For application issues, refer to the main README.md file.
