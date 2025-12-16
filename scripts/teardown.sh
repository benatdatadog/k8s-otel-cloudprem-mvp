#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  K8s OTEL to CloudPrem - Teardown${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Ensure we're using docker-desktop context
kubectl config use-context docker-desktop 2>/dev/null

echo -e "${YELLOW}Deleting namespaces...${NC}"
kubectl delete namespace otel-demo --ignore-not-found
kubectl delete namespace cloudprem --ignore-not-found
echo -e "${GREEN}✓ Namespaces deleted${NC}"
echo ""

echo -e "${YELLOW}Cleaning up cluster-wide resources...${NC}"
kubectl delete clusterrole datadog-agent --ignore-not-found
kubectl delete clusterrole otel-collector --ignore-not-found
kubectl delete clusterrolebinding datadog-agent --ignore-not-found
kubectl delete clusterrolebinding otel-collector --ignore-not-found
echo -e "${GREEN}✓ Cluster resources cleaned${NC}"
echo ""

echo -e "${YELLOW}Removing local Docker images (optional)...${NC}"
docker rmi sample-app:latest 2>/dev/null || true
echo -e "${GREEN}✓ Images removed${NC}"
echo ""

echo -e "${GREEN}Teardown complete! 🧹${NC}"
echo ""
echo -e "${BLUE}Note: Docker Desktop Kubernetes cluster is still running.${NC}"
echo -e "${BLUE}To disable it, go to Docker Desktop → Settings → Kubernetes → Uncheck 'Enable Kubernetes'${NC}"
