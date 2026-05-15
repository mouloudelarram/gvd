"""
Production Gunicorn Configuration for GVD Flask Backend
Optimized for AWS EC2, VPS, and cloud deployments
"""

import multiprocessing
import os

# ============================================================================
# WORKER CONFIGURATION
# ============================================================================

# Calculate optimal worker count based on CPU cores
# Formula: (2 x CPU_CORES) + 1
cpu_count = multiprocessing.cpu_count()
workers = (2 * cpu_count) + 1

# Production tuning
worker_class = 'sync'  # Use sync workers for Flask
worker_connections = 1000
timeout = 300  # 5 minutes for long-running scans
keepalive = 5

# ============================================================================
# THREADING & CONCURRENCY
# ============================================================================

# Threads per worker for better concurrency
threads = 1

# ============================================================================
# LOGGING
# ============================================================================

# Send logs to stdout for Docker/container logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ============================================================================
# SERVER MECHANICS
# ============================================================================

# Restart workers periodically to prevent memory leaks
max_requests = 10000
max_requests_jitter = 1000

# Graceful reload timeout
graceful_timeout = 30

# ============================================================================
# SECURITY & PERFORMANCE
# ============================================================================

# Limit request field sizes
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Socket settings
backlog = 2048

# Reload workers on code changes (development only, disabled in production)
reload = os.environ.get('FLASK_ENV') != 'production'

# ============================================================================
# SECURITY HEADERS
# ============================================================================

# Secure headers - handled by Nginx, but good to set at app level too
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on',
}

# ============================================================================
# BINDING & NETWORK
# ============================================================================

# Bind to all interfaces (Nginx will handle reverse proxy)
bind = ['0.0.0.0:5000']

# TCP backlog
backlog = 2048

# ============================================================================
# PROCESS NAMING
# ============================================================================

proc_name = 'gvd-flask'

# ============================================================================
# ENVIRONMENT & DEBUGGING
# ============================================================================

# Set environment variables
raw_env = [
    'PYTHONUNBUFFERED=1',
    'PYTHONDONTWRITEBYTECODE=1',
]
