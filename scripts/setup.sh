#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  K8s OTEL to CloudPrem - MVP Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Load .env file if it exists
if [ -f .env ]; then
    echo -e "${BLUE}Loading configuration from .env file...${NC}"
    export $(grep -v '^#' .env | xargs)
fi

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}Error: Docker daemon is not running${NC}"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed${NC}"
    echo "Install with: brew install kubectl"
    exit 1
fi

echo -e "${GREEN}✓ Docker and kubectl installed${NC}"

# Check for Docker Desktop Kubernetes
echo -e "${YELLOW}Checking for Docker Desktop Kubernetes...${NC}"
if ! kubectl config get-contexts | grep -q "docker-desktop"; then
    echo -e "${RED}Error: Docker Desktop Kubernetes is not enabled${NC}"
    echo ""
    echo "Please enable Kubernetes in Docker Desktop:"
    echo "  1. Open Docker Desktop"
    echo "  2. Go to Settings → Kubernetes"
    echo "  3. Check 'Enable Kubernetes' (select kubeadm)"
    echo "  4. Click 'Apply & Restart'"
    exit 1
fi

# Switch to docker-desktop context
echo -e "${YELLOW}Switching to docker-desktop context...${NC}"
kubectl config use-context docker-desktop
echo -e "${GREEN}✓ Using docker-desktop context${NC}"
echo ""

# Check for Datadog API key
if [ -z "$DD_API_KEY" ]; then
    echo -e "${RED}Error: DD_API_KEY environment variable is not set${NC}"
    echo ""
    echo "Create a .env file with your Datadog API key:"
    echo "  echo 'DD_API_KEY=your-api-key-here' > .env"
    echo "  echo 'DD_SITE=datadoghq.com' >> .env"
    echo ""
    echo "You can find your API key at:"
    echo "  https://app.datadoghq.com/organization-settings/api-keys"
    exit 1
fi

DD_SITE="${DD_SITE:-datadoghq.com}"
echo -e "${GREEN}✓ Datadog API key found${NC}"
echo -e "${BLUE}  Using Datadog site: ${DD_SITE}${NC}"
echo ""

# Create namespaces
echo -e "${YELLOW}Creating namespaces...${NC}"
kubectl apply -f k8s/namespace.yaml
kubectl create namespace cloudprem --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Namespaces created${NC}"
echo ""

# Create Datadog secrets in both namespaces
echo -e "${YELLOW}Creating Datadog secrets...${NC}"
kubectl create secret generic datadog-secrets \
    --from-literal=api-key="$DD_API_KEY" \
    -n otel-demo --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic datadog-secrets \
    --from-literal=api-key="$DD_API_KEY" \
    -n cloudprem --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Secrets created${NC}"
echo ""

# Create Datadog config in both namespaces
echo -e "${YELLOW}Creating Datadog config...${NC}"
kubectl create configmap datadog-config \
    --from-literal=site="$DD_SITE" \
    -n otel-demo --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap datadog-config \
    --from-literal=site="$DD_SITE" \
    -n cloudprem --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓ Config created${NC}"
echo ""

# Build sample app Docker image
echo -e "${YELLOW}Building sample app Docker image...${NC}"
docker build -t sample-app:latest ./app
echo -e "${GREEN}✓ Image built${NC}"
echo ""

# Deploy CloudPrem
echo -e "${YELLOW}Deploying CloudPrem...${NC}"
kubectl apply -f k8s/cloudprem.yaml
echo -e "${GREEN}✓ CloudPrem deployed${NC}"
echo ""

# Deploy OTEL Collector
echo -e "${YELLOW}Deploying OTEL Collector...${NC}"
kubectl apply -f k8s/otel-collector.yaml
echo -e "${GREEN}✓ OTEL Collector deployed${NC}"
echo ""

# Deploy Datadog Agent
echo -e "${YELLOW}Deploying Datadog Agent...${NC}"
kubectl apply -f k8s/datadog-agent.yaml
echo -e "${GREEN}✓ Datadog Agent deployed${NC}"
echo ""

# Deploy sample app
echo -e "${YELLOW}Deploying sample app...${NC}"
kubectl apply -f k8s/sample-app.yaml
echo -e "${GREEN}✓ Sample app deployed${NC}"
echo ""

# Wait for deployments
echo -e "${YELLOW}Waiting for pods to be ready...${NC}"
kubectl rollout status deployment/cloudprem-indexer -n cloudprem --timeout=180s
kubectl rollout status deployment/otel-collector -n otel-demo --timeout=120s
kubectl rollout status daemonset/datadog-agent -n otel-demo --timeout=120s
kubectl rollout status deployment/sample-app -n otel-demo --timeout=120s
echo -e "${GREEN}✓ All pods ready${NC}"
echo ""

# Show status
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Deployment Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}Pods in otel-demo:${NC}"
kubectl get pods -n otel-demo
echo ""
echo -e "${GREEN}Pods in cloudprem:${NC}"
kubectl get pods -n cloudprem
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Access Instructions${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Port-forward to sample app:${NC}"
echo "  kubectl port-forward svc/sample-app -n otel-demo 8080:80"
echo ""
echo -e "${YELLOW}Try these endpoints to generate traces & logs:${NC}"
echo "  curl http://localhost:8080/"
echo "  curl http://localhost:8080/api/users"
echo "  curl http://localhost:8080/api/orders"
echo "  curl http://localhost:8080/api/slow"
echo "  curl http://localhost:8080/error"
echo ""
echo -e "${YELLOW}View in Datadog:${NC}"
echo "  Traces:  https://app.${DD_SITE}/apm/traces"
echo "  Logs:    https://app.${DD_SITE}/logs (select CloudPrem index)"
echo ""
echo -e "${YELLOW}Check DD Agent log collection:${NC}"
echo "  kubectl exec -n otel-demo \$(kubectl get pods -n otel-demo -l app=datadog-agent -o jsonpath='{.items[0].metadata.name}') -- agent status | grep -A 20 'Logs Agent'"
echo ""
echo -e "${GREEN}Setup complete! 🎉${NC}"
