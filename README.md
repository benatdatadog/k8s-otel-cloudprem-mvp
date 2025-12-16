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
│  │  Sample App  │──OTLP──▶│  OTEL Collector  │──Traces/Metrics──▶ DD SaaS    │
│  │  (Python)    │  :4317  │                  │                               │
│  └──────────────┘         └────────┬─────────┘                               │
│         │                          │                                          │
│         │ stdout                   │ OTLP Logs                                │
│         ▼                          ▼                                          │
│  ┌──────────────────────────────────────────┐                                │
│  │           Datadog Agent (Operator)        │                                │
│  │  • Collects container logs (stdout)       │                                │
│  │  • Receives OTLP logs on :4317            │                                │
│  └────────────────────┬─────────────────────┘                                │
│                       │                                                       │
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
EOF
```

### 2. Deploy everything

```bash
./scripts/setup.sh
```

### 3. Generate traffic

```bash
./scripts/generate-traffic.sh
```

### 4. View in Datadog

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

| Signal | Path |
|--------|------|
| **Traces** | App → OTEL Collector → Datadog SaaS APM |
| **Metrics** | App → OTEL Collector → Datadog SaaS Metrics |
| **Logs (OTLP)** | App → OTEL Collector → DD Agent OTLP → CloudPrem |
| **Logs (stdout)** | Container → DD Agent → CloudPrem |

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
