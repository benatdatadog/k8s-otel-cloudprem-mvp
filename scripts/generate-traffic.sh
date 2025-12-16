#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BASE_URL="${1:-http://localhost:8080}"
ITERATIONS="${2:-10}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Generating Traffic for OTEL Demo${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if port-forward is needed
if [[ "$BASE_URL" == *"localhost:8080"* ]]; then
    if ! curl -s --connect-timeout 2 "$BASE_URL/health" > /dev/null 2>&1; then
        echo -e "${YELLOW}Starting port-forward to sample-app...${NC}"
        kubectl port-forward svc/sample-app -n otel-demo 8080:80 &
        PF_PID=$!
        sleep 3
        
        # Verify it's working
        if ! curl -s --connect-timeout 2 "$BASE_URL/health" > /dev/null 2>&1; then
            echo -e "${RED}Error: Cannot connect to sample-app${NC}"
            echo "Make sure the sample-app is running: kubectl get pods -n otel-demo"
            kill $PF_PID 2>/dev/null
            exit 1
        fi
        echo -e "${GREEN}✓ Port-forward started${NC}"
        STARTED_PF=true
    fi
fi

echo ""
echo -e "Target: ${GREEN}$BASE_URL${NC}"
echo -e "Iterations: ${GREEN}$ITERATIONS${NC}"
echo ""

for i in $(seq 1 $ITERATIONS); do
    echo -e "${YELLOW}--- Iteration $i of $ITERATIONS ---${NC}"
    
    echo -n "GET / ... "
    curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/"
    echo ""
    
    echo -n "GET /api/users ... "
    curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/users"
    echo ""
    
    echo -n "GET /api/orders ... "
    curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/orders"
    echo ""
    
    # Occasionally hit the slow endpoint
    if [ $((i % 3)) -eq 0 ]; then
        echo -n "GET /api/slow ... "
        curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/slow"
        echo ""
    fi
    
    # Occasionally generate an error
    if [ $((i % 5)) -eq 0 ]; then
        echo -n "GET /error ... "
        curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/error"
        echo ""
    fi
    
    # Small delay between iterations
    sleep 0.5
done

# Clean up port-forward if we started it
if [ "$STARTED_PF" = true ]; then
    echo ""
    echo -e "${YELLOW}Stopping port-forward...${NC}"
    kill $PF_PID 2>/dev/null
fi

echo ""
echo -e "${GREEN}Traffic generation complete!${NC}"
echo ""
echo -e "${BLUE}View in Datadog:${NC}"
echo "  Traces: https://app.datadoghq.com/apm/traces?query=service:sample-app"
echo "  Logs:   https://app.datadoghq.com/logs?query=service:sample-app (select CloudPrem index)"
