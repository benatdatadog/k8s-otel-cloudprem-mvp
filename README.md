# K8s OTEL to Datadog CloudPrem - MVP (OP Worker Branch)

Proof-of-concept demonstrating OpenTelemetry instrumentation on Kubernetes with **Observability Pipelines Worker (bootstrap config)**:
- **Traces & Metrics** → Datadog SaaS (via OTEL Collector)
- **Logs** → OP Worker → Datadog CloudPrem

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

## What’s in this branch
- Local bootstrap config for OP Worker (no Datadog UI pipeline required)
- OTEL Collector exports logs to OP Worker (gRPC :4317)
- OP Worker forwards to CloudPrem ingest

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
kubectl get pods -n otel-demo -l app=op-worker
kubectl logs -n otel-demo -l app=op-worker --tail=50
```

### Common Issues

**"Missing configuration option for identifier"**
- The pipeline in Datadog UI must use placeholder variables that match your env vars
- Check that `SOURCE_OTEL_GRPC_ADDRESS` and `DESTINATION_CLOUDPREM_ENDPOINT_URL` are used in the pipeline config

## Files

```
k8s/
├── op-worker.yaml            # OP Worker (bootstrap config)
├── otel-collector.yaml       # Routes logs to OP Worker
├── cloudprem.yaml            # Self-hosted log indexer
└── ...
```

## References

- [Datadog Observability Pipelines](https://docs.datadoghq.com/observability_pipelines/)
