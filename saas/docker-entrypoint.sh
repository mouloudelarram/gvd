#!/bin/bash
# GVD Flask Backend - Production Entrypoint Script
# Handles initialization, configuration, and graceful shutdown

set -e

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [ENTRYPOINT] $@"
}

error() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [ERROR] $@" >&2
}

# ============================================================================
# ENVIRONMENT VALIDATION
# ============================================================================

log "Validating production environment..."

# Check required environment variables
required_vars=(
    "GITHUB_CLIENT_ID"
    "GITHUB_CLIENT_SECRET"
    "FLASK_SECRET_KEY"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        error "Required environment variable missing: $var"
        exit 1
    fi
done

log "Environment validation passed"

# ============================================================================
# DIRECTORY INITIALIZATION
# ============================================================================

log "Initializing application directories..."

dirs=(
    "/app/scan_reports"
    "/app/repos"
    "/app/uploads"
    "/app/temp"
    "/app/logs"
)

for dir in "${dirs[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chmod 755 "$dir"
        log "Created directory: $dir"
    fi
done

# ============================================================================
# CONFIGURATION
# ============================================================================

log "Setting up Python environment..."

# Ensure Python doesn't buffer output (needed for Docker logs)
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# ============================================================================
# SECURITY CHECKS
# ============================================================================

log "Running security checks..."

# Verify Flask secret key is not the default
if [ "$FLASK_SECRET_KEY" = "your_secret_key_here_change_in_production" ]; then
    error "FLASK_SECRET_KEY is still set to default value!"
    exit 1
fi

log "Security checks passed"

# ============================================================================
# SIGNAL HANDLERS (Graceful Shutdown)
# ============================================================================

handle_signal() {
    log "Received SIGTERM/SIGINT - initiating graceful shutdown..."
    kill -TERM $child_pid 2>/dev/null || true
    wait $child_pid 2>/dev/null || true
    log "Shutdown complete"
    exit 0
}

trap handle_signal SIGTERM SIGINT

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

log "Starting GVD Flask application with Gunicorn..."
log "Using configuration from: /app/gunicorn_config.py"

# Start Gunicorn with all arguments passed through
exec python -m gunicorn \
    --config /app/gunicorn_config.py \
    --bind 0.0.0.0:5000 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app &

child_pid=$!

# Wait for child process
wait $child_pid
