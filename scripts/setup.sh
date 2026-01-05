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

if ! command -v helm &> /dev/null; then
    echo -e "${RED}Error: helm is not installed${NC}"
    echo "Install with: brew install helm"
    exit 1
fi

echo -e "${GREEN}✓ Docker, kubectl, and helm installed${NC}"

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
    echo "Create a .env file with your Datadog credentials:"
    echo "  DD_API_KEY=your-api-key-here"
    echo "  DD_SITE=datadoghq.com"
    echo "  DD_OP_PIPELINE_ID=your-pipeline-id  # From Datadog UI"
    exit 1
fi

# Check for OP Pipeline ID
if [ -z "$DD_OP_PIPELINE_ID" ]; then
    echo -e "${RED}Error: DD_OP_PIPELINE_ID environment variable is not set${NC}"
    echo ""
    echo "Create a Pipeline in Datadog UI first:"
    echo "  1. Go to https://app.datadoghq.com/observability-pipelines"
    echo "  2. Create New Pipeline with:"
    echo "     - Source: OpenTelemetry"
    echo "     - Destination: Datadog Logs"
    echo "     - Destination URL: http://cloudprem-indexer.cloudprem.svc.cluster.local:7280"
    echo "  3. Deploy and copy the Pipeline ID"
    echo "  4. Add to .env: DD_OP_PIPELINE_ID=your-pipeline-id"
    exit 1
fi

DD_SITE="${DD_SITE:-datadoghq.com}"
echo -e "${GREEN}✓ Datadog API key found${NC}"
echo -e "${GREEN}✓ OP Pipeline ID found${NC}"
echo -e "${BLUE}  Using Datadog site: ${DD_SITE}${NC}"
echo -e "${BLUE}  Using Pipeline ID: ${DD_OP_PIPELINE_ID}${NC}"
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

# Install OP Worker (Observability Pipelines) via Helm
# Uses official Datadog OP Worker with Pipeline ID from UI
echo -e "${YELLOW}Installing OP Worker via Helm...${NC}"
helm repo add datadog https://helm.datadoghq.com 2>/dev/null || true
helm repo update datadog

helm upgrade --install opw \
    --namespace otel-demo \
    --set datadog.apiKey="$DD_API_KEY" \
    --set datadog.pipelineId="$DD_OP_PIPELINE_ID" \
    --set datadog.site="$DD_SITE" \
    --set service.ports[0].name=otlp-grpc \
    --set service.ports[0].protocol=TCP \
    --set service.ports[0].port=4317 \
    --set service.ports[0].targetPort=4317 \
    --set service.ports[1].name=otlp-http \
    --set service.ports[1].protocol=TCP \
    --set service.ports[1].port=4318 \
    --set service.ports[1].targetPort=4318 \
    --set env[0].name=DD_OP_SOURCE_OTLP_GRPC_ADDRESS \
    --set env[0].value=0.0.0.0:4317 \
    --set env[1].name=DD_OP_SOURCE_OTLP_HTTP_ADDRESS \
    --set env[1].value=0.0.0.0:4318 \
    datadog/observability-pipelines-worker \
    --wait --timeout=300s
echo -e "${GREEN}✓ OP Worker installed${NC}"
echo ""

# Install Datadog Operator
echo -e "${YELLOW}Installing Datadog Operator...${NC}"
helm repo add datadog https://helm.datadoghq.com 2>/dev/null || true
helm repo update
helm upgrade --install datadog-operator datadog/datadog-operator \
    -n otel-demo \
    --set watchNamespaces="{otel-demo}" \
    --wait
echo -e "${GREEN}✓ Datadog Operator installed${NC}"
echo ""

# Deploy Datadog Agent via Operator
echo -e "${YELLOW}Deploying Datadog Agent (via Operator)...${NC}"
kubectl apply -f k8s/datadog-operator-agent.yaml
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
kubectl rollout status statefulset/opw-observability-pipelines-worker -n otel-demo --timeout=180s || true
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
echo -e "${YELLOW}Access the app:${NC}"
echo "  curl localhost:30080              # NodePort - works immediately"
echo "  curl localhost:30080/api/users    # Get users (7 logs, 4 spans)"
echo "  curl localhost:30080/api/orders   # Get orders (9 logs, 6 spans)"
echo ""
echo -e "${YELLOW}Generate traffic:${NC}"
echo "  ./scripts/generate-traffic.sh"
echo ""
echo -e "${YELLOW}View in Datadog:${NC}"
echo "  Traces:  https://app.${DD_SITE}/apm/traces?query=service:sample-app"
echo "  Logs:    https://app.${DD_SITE}/logs (select CloudPrem index)"
echo ""
echo -e "${GREEN}Setup complete! 🎉${NC}"
