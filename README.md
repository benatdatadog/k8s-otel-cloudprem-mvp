# K8s OTEL to Datadog CloudPrem - MVP

A proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with **all telemetry flowing through the Datadog Agent**:
- **Traces & Metrics** → DD Agent (OTLP) → Datadog SaaS
- **Logs** → DD Agent (OTLP) → Datadog CloudPrem

## Features

- **Maximum Observability** - Every request generates 6-10 correlated logs with full trace context
- **Unified Telemetry Pipeline** - All signals (traces, metrics, logs) flow through DD Agent
- **Trace Correlation** - Logs include standard OTLP `trace_id`/`span_id` for APM correlation
- **Vendor-Agnostic App** - Uses standard OpenTelemetry format (no Datadog-specific code)
- **Rich Span Attributes** - Database queries, HTTP details, timing metrics on every span
- **RUM Integration** - Optional browser-side Real User Monitoring with session replay

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Docker Desktop Kubernetes                                │
│                                                                               │
│  ┌──────────────┐         ┌──────────────────┐                               │
│  │  Sample App  │──OTLP──▶│  OTEL Collector  │                               │
│  │  (Python)    │  :4317  │                  │                               │
│  └──────────────┘         └────────┬─────────┘                               │
│                                    │                                          │
│                                    │ OTLP (traces, metrics, logs)             │
│                                    ▼                                          │
│  ┌──────────────────────────────────────────┐                                │
│  │           Datadog Agent (Operator)        │──Traces/Metrics──▶ DD SaaS    │
│  │  • Receives ALL telemetry via OTLP :4317  │                                │
│  │  • Forwards traces/metrics to DD SaaS     │                                │
│  │  • Forwards logs to CloudPrem             │                                │
│  └────────────────────┬─────────────────────┘                                │
│                       │ Logs                                                  │
│                       ▼                                                       │
│  ┌──────────────────┐         ┌──────────────────┐                           │
│  │    CloudPrem     │◀───────▶│   Datadog SaaS   │                           │
│  │    (Indexer)     │         │  (Log Explorer)  │                           │
│  └──────────────────┘         └──────────────────┘                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Purpose | Namespace |
|-----------|---------|-----------|
| **Sample App** | Python Flask app with OTEL instrumentation | otel-demo |
| **OTEL Collector** | Receives OTLP, exports traces/metrics to DD SaaS, logs to DD Agent | otel-demo |
| **Datadog Agent** | Collects container + OTLP logs, sends to CloudPrem | otel-demo |
| **CloudPrem** | Self-hosted Datadog log indexer (reverse-connected to SaaS) | cloudprem |

## Prerequisites

- **Docker Desktop** with Kubernetes enabled (kubeadm)
- **kubectl** - `brew install kubectl`
- **helm** - `brew install helm`
- Datadog API Key

### Enable Docker Desktop Kubernetes

1. Open Docker Desktop → **Settings → Kubernetes**
2. Check **"Enable Kubernetes"** (select **kubeadm**)
3. Click **Apply & Restart**

## Quick Start

### 1. Create `.env` file

```bash
cat > .env << 'EOF'
DD_API_KEY=your-datadog-api-key-here
DD_SITE=datadoghq.com

# Optional: Enable RUM (Real User Monitoring)
DD_RUM_APPLICATION_ID=your-rum-app-id
DD_RUM_CLIENT_TOKEN=your-rum-client-token
EOF
```

> **RUM Setup**: To get RUM credentials, go to [Digital Experience → Add an Application](https://app.datadoghq.com/rum/application/create) in Datadog.

### 2. Deploy everything

```bash
./scripts/setup.sh
```

### 3. Access the app

The sample app is exposed via NodePort on `localhost:30080`:

```bash
curl localhost:30080              # Home - list endpoints
curl localhost:30080/api/users    # Get users (7 logs, 4 spans)
curl localhost:30080/api/orders   # Get orders (9 logs, 6 spans)
curl localhost:30080/api/slow     # Slow operation (latency tracing)
curl localhost:30080/error        # Error simulation
```

### 4. Generate traffic

```bash
./scripts/generate-traffic.sh
```

### 5. View in Datadog

| Signal | Where to Find It |
|--------|------------------|
| **Traces** | [APM → Traces](https://app.datadoghq.com/apm/traces) - `service:sample-app` |
| **Logs** | [Logs](https://app.datadoghq.com/logs) - select CloudPrem index |

## Project Structure

```
.
├── .env                              # Datadog credentials (git-ignored)
├── app/
│   ├── Dockerfile
│   ├── main.py                       # Flask app with OTEL instrumentation
│   └── requirements.txt
├── k8s/
│   ├── namespace.yaml
│   ├── otel-collector.yaml           # OTLP receiver, DD SaaS exporter
│   ├── datadog-operator-agent.yaml   # DD Agent CRD (Operator)
│   ├── cloudprem.yaml                # Self-hosted log indexer
│   └── sample-app.yaml
└── scripts/
    ├── setup.sh                      # Full deployment
    ├── teardown.sh                   # Cleanup
    └── generate-traffic.sh           # Load generator
```

## Data Flow

All telemetry flows through the DD Agent via OTLP:

| Signal | Path |
|--------|------|
| **Traces** | App → OTEL Collector → **DD Agent** → Datadog SaaS APM |
| **Metrics** | App → OTEL Collector → **DD Agent** → Datadog SaaS Metrics |
| **Logs** | App → OTEL Collector → **DD Agent** → CloudPrem |
| **RUM** | Browser → Datadog SaaS RUM (optional) |

## Observability Per Request

Each request generates **multiple correlated logs** sharing the same `trace_id`:

| Endpoint | Logs per Trace | Spans per Trace |
|----------|----------------|-----------------|
| `/api/users` | 7 logs | 4 spans |
| `/api/orders` | 9 logs | 6 spans |
| `/api/slow` | 6 logs | 4+ spans |
| `/error` | 6 logs | 3 spans |

## Key Configuration

### DD Agent OTLP Logs (datadog-operator-agent.yaml)

```yaml
spec:
  global:
    env:
      - name: DD_OTLP_CONFIG_LOGS_ENABLED
        value: "true"
      - name: DD_LOGS_CONFIG_LOGS_DD_URL
        value: http://cloudprem-indexer.cloudprem.svc.cluster.local:7280
  features:
    otlp:
      receiver:
        protocols:
          grpc:
            enabled: true
            endpoint: 0.0.0.0:4317
    logCollection:
      enabled: true
      containerCollectAll: true
```

## Troubleshooting

### Check pod status
```bash
kubectl get pods -n otel-demo
kubectl get pods -n cloudprem
```

### Check DD Agent logs status
```bash
kubectl exec -n otel-demo $(kubectl get pods -n otel-demo -l app.kubernetes.io/component=agent -o jsonpath='{.items[0].metadata.name}') -c agent -- agent status | grep -A 15 "Logs Agent"
```

### Check OTLP receiver status
```bash
kubectl exec -n otel-demo $(kubectl get pods -n otel-demo -l app.kubernetes.io/component=agent -o jsonpath='{.items[0].metadata.name}') -c agent -- agent status | grep -A 5 "OTLP"
```

### View OTEL Collector logs
```bash
kubectl logs -l app=otel-collector -n otel-demo --tail=30
```

## Cleanup

```bash
./scripts/teardown.sh
```

## References

- [Datadog OTLP Ingest](https://docs.datadoghq.com/opentelemetry/setup/otlp_ingest_in_the_agent/)
- [Datadog CloudPrem](https://docs.datadoghq.com/cloudprem/)
- [Datadog Operator](https://docs.datadoghq.com/containers/kubernetes/installation/?tab=operator)
