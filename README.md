# K8s OTEL to Datadog CloudPrem - MVP (OP Worker Branch)

A proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with **Observability Pipelines Worker**:
- **Traces & Metrics** → Datadog SaaS (via OTEL Collector)
- **Logs** → Datadog CloudPrem (via OP Worker)

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

## ⚠️ Prerequisites: Create Pipeline in Datadog UI

**Before deploying**, you must create a pipeline in the Datadog UI:

1. Go to [Observability Pipelines](https://app.datadoghq.com/observability-pipelines)
2. Click **New Pipeline**
3. Select **OpenTelemetry (OTLP)** as Source
4. Select **Datadog Logs** as Destination
5. Configure placeholders to match `k8s/op-worker-values.yaml`:
   - Source address: `${SOURCE_OTEL_GRPC_ADDRESS}`
   - Destination endpoint: `${DESTINATION_CLOUDPREM_ENDPOINT_URL}`
6. Save and copy the **Pipeline ID** and **Worker ID**
7. Update `k8s/op-worker-values.yaml` with your IDs

## Quick Start

### 1. Create `.env` file

```bash
cat > .env << 'EOF'
DD_API_KEY=your-datadog-api-key-here
DD_SITE=datadoghq.com
EOF
```

### 2. Update OP Worker values

Edit `k8s/op-worker-values.yaml` with your Pipeline ID and Worker ID from the Datadog UI.

### 3. Deploy everything

```bash
./scripts/setup.sh
```

### 4. Generate traffic

```bash
./scripts/generate-traffic.sh
```

## Data Flow

| Signal | Path |
|--------|------|
| **Traces** | App → OTEL Collector → Datadog SaaS APM |
| **Metrics** | App → OTEL Collector → Datadog SaaS Metrics |
| **Logs** | App → OTEL Collector → **OP Worker** → CloudPrem |

## OP Worker Benefits

- **Transform logs** before indexing (parse JSON, extract fields)
- **Filter/sample** high-volume logs
- **Route** different logs to different destinations
- **Enrich** with additional metadata
- **UI-managed configuration** via Datadog platform

## Troubleshooting

### Check OP Worker status
```bash
kubectl get pods -n otel-demo -l app.kubernetes.io/name=observability-pipelines-worker
kubectl logs -n otel-demo -l app.kubernetes.io/name=observability-pipelines-worker --tail=50
```

### Common Issues

**"Missing configuration option for identifier"**
- The pipeline in Datadog UI must use placeholder variables that match your env vars
- Check that `SOURCE_OTEL_GRPC_ADDRESS` and `DESTINATION_CLOUDPREM_ENDPOINT_URL` are used in the pipeline config

## Files

```
k8s/
├── op-worker-values.yaml     # Helm values for OP Worker
├── otel-collector.yaml       # Routes logs to OP Worker
├── cloudprem.yaml            # Self-hosted log indexer
└── ...
```

## References

- [Datadog Observability Pipelines](https://docs.datadoghq.com/observability_pipelines/)
- [OP Worker Helm Chart](https://github.com/DataDog/helm-charts/tree/main/charts/observability-pipelines-worker)
