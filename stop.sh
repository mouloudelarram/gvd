#!/bin/bash
# ============================================================================
# GVD (Git Vulnerability Detector) - Stop Script
# ============================================================================
# Stop all GVD services cleanly
# Usage: ./stop.sh [--clean]
#   (no args) - Stop services, keep volumes
#   --clean   - Stop services and remove all volumes
# ============================================================================

CLEAN_MODE=false

if [ "$1" = "--clean" ]; then
    CLEAN_MODE=true
fi

# Colors
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Stopping GVD Services${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$CLEAN_MODE" = true ]; then
    echo -e "${YELLOW}⚠ CLEAN MODE: Removing volumes (data will be lost)${NC}"
    echo ""
    docker compose -f docker-compose.production.yml down -v
    echo -e "${GREEN}✓ All services stopped and volumes removed${NC}"
else
    echo -e "${BLUE}Stopping services (keeping data volumes)${NC}"
    echo ""
    docker compose -f docker-compose.production.yml down
    echo -e "${GREEN}✓ All services stopped${NC}"
    echo -e "${BLUE}ℹ Data preserved in ./data/ directories${NC}"
    echo ""
    echo "To also remove data, run: ./stop.sh --clean"
fi

echo ""
echo -e "${GREEN}Done!${NC}"
