# K8s OTEL to Datadog CloudPrem - MVP

A proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with **Observability Pipelines Worker**:
- **Traces & Metrics** → Datadog SaaS (via OTEL Collector)
- **Logs** → Datadog CloudPrem (via OP Worker)

## Features

- **JSON Structured Logging** - All app logs output in JSON format for easy parsing
- **Trace Correlation** - Logs include standard OTLP `trace_id`/`span_id` for APM correlation
- **Vendor-Agnostic** - Uses standard OpenTelemetry format (no Datadog-specific fields)
- **OP Worker Integration** - Logs routed through Observability Pipelines for transformation

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Docker Desktop Kubernetes                                │
│                                                                               │
│  ┌──────────────┐         ┌──────────────────┐                               │
│  │  Sample App  │──OTLP──▶│  OTEL Collector  │──Traces/Metrics──▶ DD SaaS    │
│  │  (Python)    │  :4317  │                  │                               │
│  └──────────────┘         └────────┬─────────┘                               │
│                                    │                                          │
│                                    │ OTLP Logs                                │
│                                    ▼                                          │
│                           ┌──────────────────┐                               │
│                           │    OP Worker     │  ← Transform / Filter / Route │
│                           │  (Obs Pipelines) │                               │
│                           └────────┬─────────┘                               │
│                                    │                                          │
│                                    ▼                                          │
│  ┌──────────────────┐         ┌──────────────────┐                           │
│  │    CloudPrem     │◀───────▶│   Datadog SaaS   │                           │
│  │    (Indexer)     │         │  (Log Explorer)  │                           │
│  └──────────────────┘         └──────────────────┘                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

<img width="1437" height="566" alt="image" src="https://github.com/user-attachments/assets/b61b34c3-4b4b-4d40-93a3-020271a6701c" />


## Prerequisites

- Docker Desktop with Kubernetes enabled (kubeadm)
- kubectl, helm
- Datadog API Key

## Setup

### 1. Create Pipeline in Datadog UI

1. Go to [Observability Pipelines](https://app.datadoghq.com/observability-pipelines)
2. Create new pipeline with:
   - **Source**: OpenTelemetry (OTLP) - endpoint `0.0.0.0:4317`
   - **Destination**: Datadog Logs - endpoint `http://cloudprem-indexer.cloudprem.svc.cluster.local:7280`
3. Save and **Deploy** the pipeline
4. Copy the **Pipeline ID**

### 2. Deploy CloudPrem and OTEL Collector

```bash
# Create .env with your API key
echo 'DD_API_KEY=your-api-key' > .env
source .env

# Deploy CloudPrem
kubectl apply -f k8s/namespace.yaml
kubectl create namespace cloudprem
kubectl create secret generic datadog-secrets --from-literal=api-key=$DD_API_KEY -n otel-demo
kubectl create secret generic datadog-secrets --from-literal=api-key=$DD_API_KEY -n cloudprem
kubectl apply -f k8s/cloudprem.yaml

# Build and deploy sample app
docker build -t sample-app:latest ./app
kubectl apply -f k8s/sample-app.yaml

# Deploy OTEL Collector
kubectl apply -f k8s/otel-collector.yaml
```

### 3. Install OP Worker via Helm

Use the command from the Datadog UI (with zsh-safe quoting):

```bash
helm upgrade --install opw \
  --namespace otel-demo \
  --set datadog.apiKey=$DD_API_KEY \
  --set datadog.pipelineId=YOUR_PIPELINE_ID \
  --set datadog.site=datadoghq.com \
  --set-string 'env[0].name=DD_OP_SOURCE_OTEL_HTTP_ADDRESS' \
  --set-string 'env[0].value=0.0.0.0:4318' \
  --set-string 'env[1].name=DD_OP_SOURCE_OTEL_GRPC_ADDRESS' \
  --set-string 'env[1].value=0.0.0.0:4317' \
  --set-string 'env[2].name=DD_OP_DESTINATION_CLOUDPREM_ENDPOINT_URL' \
  --set-string 'env[2].value=http://cloudprem-indexer.cloudprem.svc.cluster.local:7280' \
  --set 'service.ports[0].name=otel-http' \
  --set 'service.ports[0].protocol=TCP' \
  --set 'service.ports[0].port=4318' \
  --set 'service.ports[0].targetPort=4318' \
  --set 'service.ports[1].name=otel-grpc' \
  --set 'service.ports[1].protocol=TCP' \
  --set 'service.ports[1].port=4317' \
  --set 'service.ports[1].targetPort=4317' \
  datadog/observability-pipelines-worker
```

### 4. Deploy the pipeline in Datadog UI

After Helm install, go back to the Datadog UI and click **Deploy** on your pipeline.

### 5. Generate traffic

```bash
./scripts/generate-traffic.sh
```

### 6. View logs in Datadog

Go to [Logs](https://app.datadoghq.com/logs), select CloudPrem index, search `service:sample-app`.

## Data Flow

| Signal | Path |
|--------|------|
| **Traces** | App → OTEL Collector → Datadog SaaS APM |
| **Metrics** | App → OTEL Collector → Datadog SaaS Metrics |
| **Logs** | App → OTEL Collector → **OP Worker** → CloudPrem |

## Log Format

Logs are output in JSON with standard OTLP trace context:

```json
{
  "timestamp": "2025-12-17T22:37:37.721915Z",
  "level": "INFO",
  "service": "sample-app",
  "message": "Fetched users from database",
  "trace_id": "b0bbce84cafe1528a9a018c9927813e5",
  "span_id": "5e2917fa0c9e787f",
  "endpoint": "/api/users",
  "user_count": 3
}
```

This enables:
- **Trace ↔ Log correlation** in Datadog APM
- **Structured querying** in Log Explorer
- **Vendor-agnostic format** (standard OTLP, not Datadog-specific)

## OP Worker Benefits

- Transform logs before indexing
- Filter/sample high-volume logs
- Route to multiple destinations
- UI-managed configuration (edit pipeline in Datadog UI, worker auto-reloads)

## Troubleshooting

```bash
# Check OP Worker status
kubectl get pods -n otel-demo -l app.kubernetes.io/name=observability-pipelines-worker
kubectl logs -n otel-demo -l app.kubernetes.io/name=observability-pipelines-worker --tail=60

# Check OTEL Collector
kubectl logs -l app=otel-collector -n otel-demo --tail=30
```

## References

- [Datadog Observability Pipelines](https://docs.datadoghq.com/observability_pipelines/)
- [OP Worker Helm Chart](https://github.com/DataDog/helm-charts/tree/main/charts/observability-pipelines-worker)
