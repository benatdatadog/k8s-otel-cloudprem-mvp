# K8s OTEL to Datadog CloudPrem - MVP

A proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with **Observability Pipelines Worker**:
- **Traces & Metrics** → Datadog SaaS (via OTEL Collector)
- **Logs** → Datadog CloudPrem (via OP Worker)

## Features

- **Maximum Observability** - Every request generates 6-10 correlated logs with full trace context
- **JSON Structured Logging** - All app logs output in JSON format for easy parsing
- **Trace Correlation** - Logs include standard OTLP `trace_id`/`span_id` for APM correlation
- **Vendor-Agnostic** - Uses standard OpenTelemetry format (no Datadog-specific fields)
- **OP Worker Integration** - Logs routed through Observability Pipelines for transformation
- **Rich Span Attributes** - Database queries, HTTP details, timing metrics on every span

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

### 1. Create Pipeline in Datadog UI (Required)

1. Go to **[Observability Pipelines](https://app.datadoghq.com/observability-pipelines)**
2. Click **New Pipeline**
3. Configure:
   - **Source**: OpenTelemetry - listen on `0.0.0.0:4317`
   - **Destination**: Datadog Logs
   - **Destination endpoint**: `http://cloudprem-indexer.cloudprem.svc.cluster.local:7280`
4. Click **Deploy** and **copy the Pipeline ID**

### 2. Create `.env` file

```bash
cat > .env << 'EOF'
DD_API_KEY=your-datadog-api-key
DD_SITE=datadoghq.com
DD_OP_PIPELINE_ID=your-pipeline-id-from-step-1
EOF
```

### 3. Deploy everything

```bash
./scripts/setup.sh
```

This deploys: CloudPrem, OTEL Collector, **OP Worker (via Helm)**, DD Agent, and sample app.

### 4. Access the app

```bash
curl localhost:30080              # Home
curl localhost:30080/api/users    # 7 logs, 4 spans
curl localhost:30080/api/orders   # 9 logs, 6 spans
```

---

<details>
<summary>Manual Helm install (alternative)</summary>

```bash
helm upgrade --install opw \
  --namespace otel-demo \
  --set datadog.apiKey=$DD_API_KEY \
  --set datadog.pipelineId=$DD_OP_PIPELINE_ID \
  --set datadog.site=datadoghq.com \
  --set 'env[0].name=DD_OP_SOURCE_OTLP_GRPC_ADDRESS' \
  --set 'env[0].value=0.0.0.0:4317' \
  --set 'env[1].name=DD_OP_SOURCE_OTLP_HTTP_ADDRESS' \
  --set 'env[1].value=0.0.0.0:4318' \
  --set 'service.ports[0].name=otlp-grpc' \
  --set 'service.ports[0].protocol=TCP' \
  --set 'service.ports[0].port=4317' \
  --set 'service.ports[0].targetPort=4317' \
  --set 'service.ports[1].name=otlp-http' \
  --set 'service.ports[1].protocol=TCP' \
  --set 'service.ports[1].port=4318' \
  --set 'service.ports[1].targetPort=4318' \
  datadog/observability-pipelines-worker
```

</details>

### 5. Generate traffic

```bash
./scripts/generate-traffic.sh
```

### 6. View in Datadog

- **Traces**: [APM → Traces](https://app.datadoghq.com/apm/traces) - `service:sample-app`
- **Logs**: [Logs](https://app.datadoghq.com/logs) - select CloudPrem index
- **OP Metrics**: [Observability Pipelines](https://app.datadoghq.com/observability-pipelines) - pipeline stats

## Data Flow

| Signal | Path |
|--------|------|
| **Traces** | App → OTEL Collector → Datadog SaaS APM |
| **Metrics** | App → OTEL Collector → Datadog SaaS Metrics |
| **Logs** | App → OTEL Collector → **OP Worker** → CloudPrem |

## Observability Per Request

Each request generates **multiple correlated logs** sharing the same `trace_id`:

| Endpoint | Logs per Trace | Spans per Trace |
|----------|----------------|-----------------|
| `/api/users` | 7 logs | 4 spans |
| `/api/orders` | 9 logs | 6 spans |
| `/api/slow` | 6 logs | 4+ spans |
| `/error` | 6 logs | 3 spans |

**Example trace for `/api/users`:**
```
trace_id: fb660b37912196669d0468e34a7879ad
├── Request received (request_start)
├── Starting user fetch operation
├── Request validation passed
├── Database query executed (query_time_ms, rows_returned)
├── Data transformation complete
├── User fetch completed successfully
└── Request completed (duration_ms: 54.82)
```

## Log Format

Logs are output in JSON with standard OTLP trace context:

```json
{
  "timestamp": "2025-12-17T22:37:37.721915Z",
  "level": "INFO",
  "service": "sample-app",
  "message": "Database query executed",
  "trace_id": "b0bbce84cafe1528a9a018c9927813e5",
  "span_id": "5e2917fa0c9e787f",
  "request_id": "a945183e",
  "db_system": "postgresql",
  "db_operation": "SELECT",
  "query_time_ms": 45.87,
  "rows_returned": 3
}
```

This enables:
- **Trace ↔ Log correlation** in Datadog APM (click trace → see all related logs)
- **Structured querying** in Log Explorer
- **Vendor-agnostic format** (standard OTLP, not Datadog-specific)

## OP Worker Benefits

- Transform logs before indexing
- Filter/sample high-volume logs
- Route to multiple destinations
- UI-managed configuration (edit pipeline in Datadog UI, worker auto-reloads)

## OP Worker challenges 
 - If you view from log UI you can see the log and then the trace and metrics etc.
 - If you view the trace from the trace / APM part or Datadog, there is no way to select the cloudprem index and so you dont see the correlation ( even though its in the data ) .

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
