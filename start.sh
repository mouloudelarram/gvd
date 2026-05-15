#!/bin/bash
# ============================================================================
# GVD (Git Vulnerability Detector) - Quick Start Script
# ============================================================================
# Start the entire production-ready GVD platform with a single command
# Usage: ./start.sh
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

print_header "GVD Startup - Checking Prerequisites"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    echo "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi
print_success "Docker found: $(docker --version)"

# Check if Docker daemon is running
if ! docker ps &> /dev/null; then
    print_error "Docker daemon is not running"
    echo "Start Docker and try again"
    exit 1
fi
print_success "Docker daemon is running"

# Check for docker compose (v2)
if ! command -v docker &> /dev/null; then
    print_error "docker compose (v2) not found"
    echo "You have docker-compose (v1). Please upgrade to Docker Desktop with compose v2"
    exit 1
fi
print_success "docker compose (v2) is available"

# ============================================================================
# DIRECTORY SETUP
# ============================================================================

print_header "Setting Up Directories"

DIRS=(
    "data/scan_reports"
    "data/repos"
    "data/uploads"
    "data/temp"
    "data/ssl"
    "logs/nginx"
    "logs/app"
    "logs/scanner"
)

for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_success "Created directory: $dir"
    else
        print_info "Directory exists: $dir"
    fi
done

# ============================================================================
# ENVIRONMENT FILE CHECK
# ============================================================================

print_header "Checking Environment Configuration"

if [ ! -f ".env.production" ]; then
    print_warning ".env.production not found"
    print_info "Creating .env.production from template..."
    if [ -f ".env.production.template" ]; then
        cp .env.production.template .env.production
        print_success "Created .env.production"
        print_warning "IMPORTANT: Update .env.production with your GitHub OAuth credentials!"
        print_info "Edit .env.production and set:"
        echo "  - GITHUB_CLIENT_ID"
        echo "  - GITHUB_CLIENT_SECRET"
        echo "  - FLASK_SECRET_KEY (or keep dev key for testing)"
    else
        print_error "Template file not found: .env.production.template"
        exit 1
    fi
else
    print_success ".env.production exists"
fi

# ============================================================================
# DOCKER BUILD & STARTUP
# ============================================================================

print_header "Building Docker Images"

# Use docker-compose.yml by default, unless --production flag specified
COMPOSE_FILE="docker-compose.yml"
if [ "$1" = "--production" ]; then
    COMPOSE_FILE="docker-compose.production.yml"
    print_info "Using production compose file"
else
    print_info "Using development compose file"
fi

if docker compose -f "$COMPOSE_FILE" build 2>&1 | grep -q "ERROR"; then
    print_error "Docker build failed"
    exit 1
fi
print_success "Docker images built successfully"

print_header "Starting GVD Services"

docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# ============================================================================
# VERIFICATION
# ============================================================================

print_header "Verifying Services"

sleep 3

# Check service status based on which compose file is used
if [ "$1" = "--production" ]; then
    SERVICES=("gvd-nginx" "gvd-saas" "gvd-scanner")
else
    SERVICES=("gvd-saas" "gvd-cli")
fi
ALL_HEALTHY=true

for service in "${SERVICES[@]}"; do
    if docker compose -f "$COMPOSE_FILE" ps "$service" 2>/dev/null | grep -q "Up"; then
        print_success "Service running: $service"
    else
        print_warning "Service not fully ready: $service (may still be starting)"
        ALL_HEALTHY=false
    fi
done

# ============================================================================
# POST-STARTUP INFORMATION
# ============================================================================

print_header "GVD Started Successfully!"

echo ""
echo "📊 Service Status:"
docker compose -f "$COMPOSE_FILE" ps
echo ""

echo "🌐 Access Points:"
if [ "$1" = "--production" ]; then
    print_info "Web Interface: http://localhost"
    print_info "API: http://localhost/api"
else
    print_info "Web Interface: http://localhost:5000"
    print_info "API: http://localhost:5000/api"
fi
echo ""

echo "📋 Useful Commands:"
echo "  View logs (all services):     docker compose -f $COMPOSE_FILE logs -f"
echo "  View Flask logs:              docker compose -f $COMPOSE_FILE logs -f gvd-saas"
if [ "$1" = "--production" ]; then
    echo "  View Nginx logs:              docker compose -f $COMPOSE_FILE logs -f gvd-nginx"
fi
echo "  Check services:               docker compose -f $COMPOSE_FILE ps"
echo "  Stop all services:            docker compose -f $COMPOSE_FILE down"
echo "  Stop + remove volumes:        docker compose -f $COMPOSE_FILE down -v"
echo "  Enter container:              docker compose -f $COMPOSE_FILE exec gvd-saas bash"
echo "  Monitor resources:            docker stats"
echo ""

echo "📁 Important Directories:"
echo "  Application code:  ./saas, ./cli, ./nginx"
echo "  Configuration:     ./.env.production"
echo "  Data storage:      ./data/*"
echo "  Logs:             ./logs/*"
echo ""

if [ "$ALL_HEALTHY" = false ]; then
    print_warning "Some services are still starting. Wait a few seconds and check again:"
    echo "  docker compose -f $COMPOSE_FILE ps"
    echo ""
fi

echo "📖 For detailed configuration, see:"
echo "  - PRODUCTION_DEPLOYMENT_GUIDE.md (comprehensive guide)"
echo "  - DOCKER_QUICK_REFERENCE.md (command reference)"
echo "  - AWS_EC2_QUICK_START.md (AWS deployment)"
echo ""

print_success "Ready to use GVD!"
