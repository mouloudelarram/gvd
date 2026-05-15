# GVD Quick Start Scripts Guide

> Simple bash scripts to start/stop your GVD platform with one command

## Quick Start

### Start Everything

```bash
chmod +x start.sh
./start.sh
```

That's it! The script will:
1. ✅ Check prerequisites (Docker, docker compose)
2. ✅ Create all necessary directories
3. ✅ Set up environment configuration
4. ✅ Build Docker images
5. ✅ Start all services
6. ✅ Verify everything is running
7. ✅ Show you what's available and how to access it

### Stop Everything

```bash
chmod +x stop.sh
./stop.sh
```

Or remove data too:

```bash
./stop.sh --clean
```

---

## What Each Script Does

### `start.sh` - Full Startup

#### Prerequisites Check (Lines 1-50)
```bash
# Checks:
# - Docker is installed
# - Docker daemon is running  
# - docker compose v2 is available
```

**Why:** Prevents confusing errors later if dependencies are missing

#### Directory Setup (Lines 55-70)
```bash
# Creates:
mkdir -p data/{scan_reports,repos,uploads,temp,ssl}
mkdir -p logs/{nginx,app,scanner}
```

**Why:** Docker volumes need directories to bind mount. Without these, containers can't persist data.

#### Environment Configuration (Lines 75-95)
```bash
# Checks if .env.production exists
# If not, copies from template
# Prompts user to update credentials
```

**Why:** GVD needs GitHub OAuth credentials and Flask secret key to run. Defaults are for local testing.

#### Docker Build (Lines 100-110)
```bash
docker compose -f docker-compose.production.yml build
```

**Why:** Builds Docker images from Dockerfiles. Only needed when files change or first run.

#### Start Services (Lines 115-120)
```bash
docker compose -f docker-compose.production.yml up -d
```

**Why:** Launches all containers (nginx, flask, scanner) in background (-d).

#### Verification (Lines 125-145)
```bash
# Checks each service is running
# Shows status in table format
```

**Why:** Verifies deployment succeeded before showing access information.

#### Output Information (Lines 150-180)
Shows:
- Access points (web interface, API)
- Useful commands for ongoing operations
- Important directories
- Links to detailed documentation

---

### `stop.sh` - Graceful Shutdown

#### Normal Stop (Lines 40-50)
```bash
docker compose -f docker-compose.production.yml down
```

**What happens:**
- Sends SIGTERM to all containers
- Containers shutdown gracefully (30-second timeout)
- Services stop
- **Data volumes are PRESERVED**

**Use when:** Testing, maintenance, before updates

#### Clean Stop (Lines 40-50 with --clean flag)
```bash
docker compose -f docker-compose.production.yml down -v
```

**What happens:**
- Same as above, PLUS
- Removes all volumes (data deleted)

**Use when:** Complete reset, starting fresh

---

## Command Breakdown

### Essential Commands (Used in scripts)

#### `docker compose build`
Builds images from Dockerfiles
```bash
docker compose -f docker-compose.production.yml build
```

**What it does:**
- Reads `saas/Dockerfile.prod` and `cli/Dockerfile.prod`
- Executes each instruction (apt-get, pip install, etc.)
- Creates image layers (cached for faster rebuilds)
- Tags images as `gvd_gvd-saas:latest` and `gvd_gvd-scanner:latest`

**Time:** ~2-5 minutes (first run), ~5 seconds (subsequent runs with cache)

#### `docker compose up -d`
Starts all services in background
```bash
docker compose -f docker-compose.production.yml up -d
```

**What it does:**
- Reads `docker-compose.production.yml`
- Creates bridge network `gvd-network`
- Mounts all volumes
- Starts containers in order:
  1. nginx (reverse proxy)
  2. gvd-saas (Flask backend)
  3. gvd-scanner (CLI scanner)
- Returns immediately (`-d` = detached/background mode)

**Time:** ~3-5 seconds

#### `docker compose ps`
Shows running containers
```bash
docker compose -f docker-compose.production.yml ps
```

**Output:**
```
NAME           COMMAND                STATUS         PORTS
nginx          "nginx -g daemon..."   Up (healthy)   0.0.0.0:80->80/tcp
gvd-saas       "gunicorn --config..." Up (healthy)   (no exposed ports)
gvd-scanner    "python cli.py help"   Up (healthy)   (no exposed ports)
```

#### `docker compose logs`
View container output
```bash
# All services
docker compose -f docker-compose.production.yml logs

# Specific service
docker compose -f docker-compose.production.yml logs gvd-saas

# Follow in real-time
docker compose -f docker-compose.production.yml logs -f

# Last 100 lines
docker compose -f docker-compose.production.yml logs --tail=100
```

**Why:** Debugging, monitoring, checking for errors

#### `docker compose down`
Stop services (keeps data)
```bash
docker compose -f docker-compose.production.yml down
```

**What it does:**
- Stops all containers
- Removes containers
- Removes networks
- **Keeps volumes** (data saved in `./data/`)

#### `docker compose down -v`
Stop services and delete data
```bash
docker compose -f docker-compose.production.yml down -v
```

**What it does:**
- Same as `down`, PLUS
- Removes all volumes
- Deletes all data

**Warning:** Data is lost! Use only for clean restart.

#### `docker compose exec`
Run command inside container
```bash
docker compose -f docker-compose.production.yml exec gvd-saas bash
```

**Use for:**
- Debugging
- Running commands in container
- Checking logs inside container
- Testing

#### `docker stats`
Monitor resource usage
```bash
docker stats
```

**Shows:**
- CPU usage per container
- Memory usage
- Network I/O
- Disk I/O

**Useful for:** Performance tuning, detecting issues

---

## Understanding the Flow

### When You Run `./start.sh`

```
1. Check Prerequisites
   ├─ Is Docker installed? ✓
   ├─ Is Docker running? ✓
   └─ Is docker compose available? ✓

2. Create Directories
   ├─ data/scan_reports/
   ├─ data/repos/
   ├─ data/uploads/
   ├─ data/temp/
   ├─ data/ssl/
   ├─ logs/nginx/
   ├─ logs/app/
   └─ logs/scanner/

3. Setup Environment
   ├─ Check .env.production exists
   ├─ If not, copy from template
   └─ Remind to update with GitHub credentials

4. Build Images
   ├─ Build gvd-saas (Flask backend)
   ├─ Build gvd-scanner (CLI scanner)
   └─ Cache layers for faster rebuilds

5. Start Services
   ├─ Create internal network (172.23.0.0/16)
   ├─ Mount volumes
   ├─ Start nginx on :80
   ├─ Start Flask on :5000 (internal)
   └─ Start scanner (background)

6. Verify & Report
   ├─ Check each service is running
   ├─ Show access points
   ├─ List useful commands
   └─ Link to documentation
```

---

## Data Persistence

### What Gets Saved

```
./data/
├── scan_reports/    # Scan results (persists restarts)
├── repos/           # Cloned repos (persists restarts)
├── uploads/         # User uploads (persists restarts)
├── temp/            # Temporary files (persists restarts)
└── ssl/             # SSL certificates (persists restarts)

./logs/
├── nginx/           # Web server logs
├── app/             # Flask app logs
└── scanner/         # Scanner logs
```

### Data Survival Scenarios

| Action | Data | Volumes |
|--------|------|---------|
| **Restart PC** | ✅ Preserved | ✅ Preserved |
| `./stop.sh` | ✅ Preserved | ✅ Preserved |
| `docker compose restart` | ✅ Preserved | ✅ Preserved |
| `./start.sh` | ✅ Preserved | ✅ Preserved |
| `./stop.sh --clean` | ❌ Deleted | ❌ Deleted |
| `docker system prune` | ❌ Deleted | ⚠️ At risk |

---

## Common Workflows

### Development Cycle

```bash
# 1. Start fresh
./start.sh

# 2. Make code changes in ./saas or ./cli

# 3. Rebuild and restart
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# 4. Check logs
docker compose -f docker-compose.production.yml logs -f gvd-saas

# 5. When done
./stop.sh
```

### Production Deployment (First Time)

```bash
# 1. Prepare
chmod +x start.sh stop.sh
vim .env.production  # Add real GitHub credentials

# 2. Start
./start.sh

# 3. Verify
curl http://localhost/health

# 4. Setup SSL (future: Let's Encrypt)
# See PRODUCTION_DEPLOYMENT_GUIDE.md

# 5. Configure domain DNS
# Point your-domain.com → server-ip
```

### Debugging Issue

```bash
# 1. Check status
docker compose -f docker-compose.production.yml ps

# 2. View recent logs
docker compose -f docker-compose.production.yml logs --tail=50 gvd-saas

# 3. Follow logs in real-time
docker compose -f docker-compose.production.yml logs -f gvd-saas

# 4. Enter container
docker compose -f docker-compose.production.yml exec gvd-saas bash

# 5. Check resources
docker stats

# 6. Restart if needed
docker compose -f docker-compose.production.yml restart gvd-saas
```

### Backup Before Testing

```bash
# Before running tests that might break things
docker compose -f docker-compose.production.yml exec -T gvd-saas \
  tar czf /app/backup.tar.gz /app/scan_reports /app/repos

# Extract backup if needed
docker compose -f docker-compose.production.yml exec -T gvd-saas \
  tar xzf /app/backup.tar.gz -C /
```

---

## Environment Variables

### Key Variables in `.env.production`

```bash
# GitHub OAuth (REQUIRED for login to work)
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx

# Flask Security (REQUIRED for production)
FLASK_SECRET_KEY=xxx

# Local Testing (default values work)
OAUTH_REDIRECT_URI=http://localhost:5000/callback
FLASK_ENV=production

# Optional Tuning
GUNICORN_WORKERS=4
SCAN_TIMEOUT_SECONDS=300
ENABLE_BULK_SCAN=true
```

**To get GitHub OAuth:**
1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in details
4. Copy Client ID and Client Secret
5. Paste into `.env.production`

---

## Troubleshooting

### "Permission denied" Error

```bash
# Make scripts executable
chmod +x start.sh stop.sh

# Then run
./start.sh
```

### "Docker daemon not running"

```bash
# On Linux
sudo systemctl start docker

# On Mac
open /Applications/Docker.app

# On Windows
Start Docker Desktop from Start menu
```

### "Port 80 already in use"

```bash
# See what's using port 80
sudo lsof -i :80

# Stop that service or use different port
# Edit docker-compose.production.yml line with "80:80"
# Change to "8080:80" to use port 8080 instead
```

### "Image not found" Error

```bash
# Rebuild images
docker compose -f docker-compose.production.yml build --no-cache

# Then start
./start.sh
```

### Services won't start

```bash
# Check logs
docker compose -f docker-compose.production.yml logs

# Verify .env.production is set up
cat .env.production | grep GITHUB_CLIENT_ID

# Try clean restart
./stop.sh
./start.sh
```

---

## Next Steps

Once `./start.sh` completes successfully:

1. **Access the app**: Open http://localhost in your browser
2. **Check logs**: `docker compose -f docker-compose.production.yml logs -f`
3. **Read docs**: See `PRODUCTION_DEPLOYMENT_GUIDE.md` for detailed info
4. **Configure GitHub OAuth**: Update `.env.production` with real credentials
5. **For AWS/VPS**: Follow `AWS_EC2_QUICK_START.md`

---

## Script Files

| File | Purpose |
|------|---------|
| `start.sh` | Start all services with one command |
| `stop.sh` | Stop services cleanly |
| `docker-compose.production.yml` | Defines all services, volumes, networks |
| `.env.production` | Configuration (created by start.sh) |

---

**Version:** 1.0  
**Last Updated:** 2024  
**For Help:** See `PRODUCTION_DEPLOYMENT_GUIDE.md` or `DOCKER_QUICK_REFERENCE.md`
