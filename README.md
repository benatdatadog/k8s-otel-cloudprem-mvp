# K8s OTEL to Datadog CloudPrem - MVP

A minimal proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with:
- **Traces & Metrics** → Datadog SaaS (via OTEL Collector)
- **Logs** → Datadog CloudPrem (self-hosted, via DD Agent)

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Docker Desktop Kubernetes                                │
│                                                                               │
│  ┌──────────────┐         ┌──────────────────┐                               │
│  │  Sample App  │──OTLP──▶│  OTEL Collector  │────Traces/Metrics────▶ DD SaaS│
│  │  (Python)    │  :4317  │                  │                               │
│  └──────────────┘         └──────────────────┘                               │
│         │                                                                     │
│         │ stdout (container logs)                                             │
│         ▼                                                                     │
│  ┌──────────────┐         ┌──────────────────┐         ┌──────────────────┐  │
│  │  DD Agent    │──Logs──▶│    CloudPrem     │◀───────▶│   Datadog SaaS   │  │
│  │  (Operator)  │         │    (Indexer)     │         │  (Log Explorer)  │  │
│  └──────────────┘         └──────────────────┘         └──────────────────┘  │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Note:** The DD Agent OTLP receiver only supports traces/metrics, not logs. Logs are collected via container stdout.

## Components

| Component | Purpose | Namespace |
|-----------|---------|-----------|
| **Sample App** | Python Flask app with OTEL instrumentation | otel-demo |
| **OTEL Collector** | Receives OTLP, exports traces/metrics to Datadog SaaS | otel-demo |
| **Datadog Agent** | Collects container logs, sends to CloudPrem | otel-demo |
| **CloudPrem** | Self-hosted Datadog log indexer (reverse-connected to SaaS) | cloudprem |

## Prerequisites

- **Docker Desktop** with Kubernetes enabled (kubeadm, NOT kind)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) - `brew install kubectl`
- Datadog API Key (from your Datadog account)
- (Optional) [Lens](https://k8slens.dev/) - K8s GUI - `brew install --cask lens`

### Enable Docker Desktop Kubernetes

1. Open Docker Desktop
2. Go to **Settings → Kubernetes**
3. Check **"Enable Kubernetes"**
4. Select **kubeadm** (NOT kind)
5. Click **Apply & Restart**

> ⚠️ **Why Docker Desktop K8s?** Kind and Minikube (docker driver) have Kubelet access issues that prevent the DD Agent from discovering containers for log collection. Docker Desktop's kubeadm-based K8s has proper Kubelet access.

## Quick Start

### 1. Create `.env` file with your Datadog credentials

```bash
cat > .env << 'EOF'
DD_API_KEY=your-datadog-api-key-here
DD_SITE=datadoghq.com
EOF
```

### 2. Switch to Docker Desktop context

```bash
kubectl config use-context docker-desktop
kubectl get nodes  # Should show "docker-desktop" node
```

### 3. Deploy the stack

```bash
source .env

# Create namespaces
kubectl apply -f k8s/namespace.yaml
kubectl create namespace cloudprem

# Create secrets and configmaps
kubectl create secret generic datadog-secrets --from-literal=api-key=$DD_API_KEY -n otel-demo
kubectl create secret generic datadog-secrets --from-literal=api-key=$DD_API_KEY -n cloudprem
kubectl create configmap datadog-config --from-literal=site=$DD_SITE -n otel-demo
kubectl create configmap datadog-config --from-literal=site=$DD_SITE -n cloudprem

# Build and deploy
docker build -t sample-app:latest ./app
kubectl apply -f k8s/cloudprem.yaml
kubectl apply -f k8s/otel-collector.yaml
kubectl apply -f k8s/datadog-agent.yaml
kubectl apply -f k8s/sample-app.yaml
```

### 4. Generate traffic

```bash
# Port forward to sample app
kubectl port-forward svc/sample-app -n otel-demo 8080:80 &

# Generate some requests
curl http://localhost:8080/
curl http://localhost:8080/api/users
curl http://localhost:8080/api/orders
curl http://localhost:8080/error        # Generate an error
curl http://localhost:8080/api/slow     # Slow request

# Stop port-forward
pkill -f "port-forward"
```

### 5. View in Datadog

| Signal | Where to Find It |
|--------|------------------|
| **Traces** | [APM → Traces](https://app.datadoghq.com/apm/traces) - search `service:sample-app` |
| **Metrics** | [Metrics Explorer](https://app.datadoghq.com/metric/explorer) |
| **Logs** | [Logs](https://app.datadoghq.com/logs) - select CloudPrem index, search `service:sample-app` |

## Project Structure

```
.
├── README.md
├── .env                          # Datadog credentials (git-ignored)
├── app/                          # Sample Python application
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml
│   ├── otel-collector.yaml       # OTEL Collector (traces/metrics → DD SaaS)
│   ├── datadog-operator-agent.yaml  # DD Agent via Operator (logs → CloudPrem)
│   ├── cloudprem.yaml            # Self-hosted log indexer
│   └── sample-app.yaml
└── scripts/                      # Automation scripts
    ├── setup.sh                  # Full stack deployment
    ├── teardown.sh
    └── generate-traffic.sh
```

## Data Flow

| Signal | Source | Path | Destination |
|--------|--------|------|-------------|
| **Traces** | Sample App | App → OTEL Collector → Datadog API | Datadog SaaS APM |
| **Metrics** | Sample App | App → OTEL Collector → Datadog API | Datadog SaaS Metrics |
| **Logs** | Container stdout | Container → DD Agent → CloudPrem → Datadog | CloudPrem Index |

## Troubleshooting

### Check pod status
```bash
kubectl get pods -n otel-demo
kubectl get pods -n cloudprem
```

### Check DD Agent is collecting logs
```bash
kubectl exec -n otel-demo $(kubectl get pods -n otel-demo -l app=datadog-agent -o jsonpath='{.items[0].metadata.name}') -- agent status | grep -A 20 "Logs Agent"
```

Expected output should show `LogsProcessed: <number>` increasing.

### Check DD Agent sees sample-app
```bash
kubectl exec -n otel-demo $(kubectl get pods -n otel-demo -l app=datadog-agent -o jsonpath='{.items[0].metadata.name}') -- agent status | grep -A 10 "sample-app"
```

### Check CloudPrem is running
```bash
kubectl logs -l app=cloudprem-indexer -n cloudprem --tail=20
```

### Check OTEL Collector logs
```bash
kubectl logs -l app=otel-collector -n otel-demo --tail=20
```

### Check sample app logs
```bash
kubectl logs -l app=sample-app -n otel-demo --tail=20
```

## Cleanup

```bash
kubectl delete namespace otel-demo
kubectl delete namespace cloudprem
kubectl delete clusterrole datadog-agent otel-collector
kubectl delete clusterrolebinding datadog-agent otel-collector
```

## Key Configuration Details

### DD Agent Volume Mounts (Docker Desktop)

The DD Agent needs access to Docker's socket and container logs:

```yaml
volumeMounts:
  - name: dockersocket
    mountPath: /var/run/docker.sock
  - name: podlogs
    mountPath: /var/log/pods
  - name: dockercontainerlogs
    mountPath: /var/lib/docker/containers
```

### DD Agent → CloudPrem Configuration

```yaml
env:
  - name: DD_LOGS_ENABLED
    value: "true"
  - name: DD_LOGS_CONFIG_CONTAINER_COLLECT_ALL
    value: "true"
  - name: DD_LOGS_CONFIG_LOGS_DD_URL
    value: "http://cloudprem-indexer.cloudprem.svc.cluster.local:7280"
```

## References

- [Datadog CloudPrem Docs](https://docs.datadoghq.com/cloudprem/)
- [Datadog Agent + CloudPrem](https://docs.datadoghq.com/cloudprem/ingest_logs/datadog_agent/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [Docker Desktop Kubernetes](https://docs.docker.com/desktop/kubernetes/)
