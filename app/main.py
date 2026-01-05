"""
Sample Flask application with OpenTelemetry instrumentation.
Maximum observability: every trace has multiple correlated logs.
"""

import datetime
import logging
import os
import random
import sys
import time
import uuid
from flask import Flask, jsonify, request, g, render_template_string

# JSON logging
from pythonjsonlogger import jsonlogger

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry._logs import set_logger_provider

# Configure OpenTelemetry Resource with Datadog Unified Service Tagging
resource = Resource.create({
    # Standard OTEL attributes
    "service.name": os.getenv("DD_SERVICE", os.getenv("OTEL_SERVICE_NAME", "sample-app")),
    "service.version": os.getenv("DD_VERSION", "1.0.0"),
    "deployment.environment": os.getenv("DD_ENV", os.getenv("OTEL_ENVIRONMENT", "demo")),
    
    # Host/container info for infrastructure correlation
    "host.name": os.getenv("NODE_NAME", os.getenv("HOSTNAME", "local")),
    "container.id": os.getenv("HOSTNAME", ""),  # In K8s, HOSTNAME is usually the pod name
    "k8s.pod.name": os.getenv("POD_NAME", os.getenv("HOSTNAME", "")),
    "k8s.namespace.name": os.getenv("POD_NAMESPACE", "otel-demo"),
    "k8s.node.name": os.getenv("NODE_NAME", ""),
})

# OTLP endpoint
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

# Set up tracer provider
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__, "1.0.0")

# Configure OTLP trace exporter
otlp_trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
span_processor = BatchSpanProcessor(otlp_trace_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Set up logger provider for OTLP log export
logger_provider = LoggerProvider(resource=resource)
set_logger_provider(logger_provider)

# Configure OTLP log exporter
otlp_log_exporter = OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(otlp_log_exporter))

# Create logging handler that sends to OTLP
otel_handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)

# Configure JSON logging format with trace correlation
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        log_record['service'] = 'sample-app'
        log_record['environment'] = os.getenv("OTEL_ENVIRONMENT", "demo")
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['timestamp'] = datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        
        # Inject standard OTLP trace context
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            log_record['trace_id'] = format(ctx.trace_id, '032x')
            log_record['span_id'] = format(ctx.span_id, '016x')

# Set up JSON formatter
json_formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(json_formatter)
console_handler.setLevel(logging.DEBUG)
root_logger.addHandler(console_handler)
root_logger.addHandler(otel_handler)

# Suppress noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# HTML Template for Web UI
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTEL Demo App</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --accent: #58a6ff;
            --accent-green: #3fb950;
            --accent-orange: #d29922;
            --accent-red: #f85149;
            --accent-purple: #a371f7;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --border: #30363d;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 3rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid var(--border);
        }
        
        h1 {
            font-size: 2.5rem;
            font-weight: 600;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-purple) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
        }
        
        .flow-diagram {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            text-align: center;
            color: var(--text-secondary);
        }
        
        .flow-diagram .highlight { color: var(--accent); }
        .flow-diagram .green { color: var(--accent-green); }
        .flow-diagram .orange { color: var(--accent-orange); }
        
        .endpoints {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        
        .endpoint-card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            transition: all 0.2s ease;
        }
        
        .endpoint-card:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
        }
        
        .endpoint-card h3 {
            font-family: 'JetBrains Mono', monospace;
            color: var(--accent);
            margin-bottom: 0.5rem;
            font-size: 1.1rem;
        }
        
        .endpoint-card p {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        
        .stats {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            font-size: 0.8rem;
        }
        
        .stat {
            background: var(--bg-tertiary);
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
        }
        
        .stat-logs { color: var(--accent-green); }
        .stat-spans { color: var(--accent-purple); }
        
        button {
            width: 100%;
            padding: 0.75rem 1.5rem;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border);
            border-radius: 8px;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        button:hover {
            background: var(--accent);
            color: var(--bg-primary);
            border-color: var(--accent);
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        button.error-btn:hover { background: var(--accent-red); border-color: var(--accent-red); }
        button.slow-btn:hover { background: var(--accent-orange); border-color: var(--accent-orange); }
        
        .response-section {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
        }
        
        .response-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .response-header h2 {
            font-size: 1.2rem;
            color: var(--text-primary);
        }
        
        .trace-id {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: var(--accent-purple);
            background: var(--bg-tertiary);
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
        }
        
        #response {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            min-height: 200px;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }
        
        .loading {
            color: var(--text-secondary);
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .success { color: var(--accent-green); }
        .error { color: var(--accent-red); }
        
        footer {
            text-align: center;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 0.85rem;
        }
        
        footer a {
            color: var(--accent);
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔭 OTEL Demo App</h1>
            <p class="subtitle">OpenTelemetry → Datadog SaaS</p>
        </header>
        
        <div class="flow-diagram">
            <span class="highlight">App</span> → OTEL Collector → 
            <span class="green">Datadog SaaS</span>
        </div>
        
        <div class="endpoints">
            <div class="endpoint-card">
                <h3>GET /api/users</h3>
                <p>Fetch users with database query simulation</p>
                <div class="stats">
                    <span class="stat stat-logs">📝 7 logs</span>
                    <span class="stat stat-spans">🔗 4 spans</span>
                </div>
                <button onclick="callEndpoint('/api/users')">Fetch Users</button>
            </div>
            
            <div class="endpoint-card">
                <h3>GET /api/orders</h3>
                <p>Process orders with auth and enrichment</p>
                <div class="stats">
                    <span class="stat stat-logs">📝 9 logs</span>
                    <span class="stat stat-spans">🔗 6 spans</span>
                </div>
                <button onclick="callEndpoint('/api/orders')">Get Orders</button>
            </div>
            
            <div class="endpoint-card">
                <h3>GET /api/slow</h3>
                <p>Simulate slow operation (0.5-2s delay)</p>
                <div class="stats">
                    <span class="stat stat-logs">📝 6 logs</span>
                    <span class="stat stat-spans">🔗 4+ spans</span>
                </div>
                <button class="slow-btn" onclick="callEndpoint('/api/slow')">Slow Request</button>
            </div>
            
            <div class="endpoint-card">
                <h3>GET /error</h3>
                <p>Trigger random error for error tracing</p>
                <div class="stats">
                    <span class="stat stat-logs">📝 6 logs</span>
                    <span class="stat stat-spans">🔗 3 spans</span>
                </div>
                <button class="error-btn" onclick="callEndpoint('/error')">Trigger Error</button>
            </div>
        </div>
        
        <div class="response-section">
            <div class="response-header">
                <h2>Response</h2>
                <span class="trace-id" id="trace-id">trace_id: waiting...</span>
            </div>
            <pre id="response">Click an endpoint above to generate traffic and see the response here.

Each request generates correlated logs and traces that flow through:
  • OTEL Collector (receives OTLP data)
  • Datadog SaaS (traces, metrics, logs)

Check Datadog for:
  • Traces: APM → Traces → service:sample-app
  • Logs: Logs → service:sample-app
  • Metrics: Metrics Explorer</pre>
        </div>
        
        <footer>
            <p>Part of the <a href="https://github.com/benatdatadog/k8s-otel-cloudprem-mvp">K8s OTEL to CloudPrem</a> demo</p>
        </footer>
    </div>
    
    <script>
        async function callEndpoint(path) {
            const responseEl = document.getElementById('response');
            const traceIdEl = document.getElementById('trace-id');
            
            responseEl.className = 'loading';
            responseEl.textContent = `Calling ${path}...`;
            traceIdEl.textContent = 'trace_id: generating...';
            
            try {
                const start = performance.now();
                const res = await fetch(path);
                const duration = Math.round(performance.now() - start);
                const data = await res.json();
                
                responseEl.className = res.ok ? 'success' : 'error';
                responseEl.textContent = JSON.stringify(data, null, 2);
                
                if (data.request_id) {
                    traceIdEl.textContent = `request_id: ${data.request_id} | ${duration}ms`;
                }
            } catch (err) {
                responseEl.className = 'error';
                responseEl.textContent = `Error: ${err.message}`;
                traceIdEl.textContent = 'trace_id: error';
            }
        }
    </script>
</body>
</html>
'''

# Instrument Flask
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()


@app.before_request
def before_request():
    """Log every incoming request with trace context."""
    g.request_id = str(uuid.uuid4())[:8]
    g.start_time = time.time()
    
    span = trace.get_current_span()
    if span:
        span.set_attribute("http.request_id", g.request_id)
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.route", request.path)
        span.set_attribute("http.user_agent", request.headers.get("User-Agent", "unknown"))
        span.add_event("request_received", {
            "request_id": g.request_id,
            "path": request.path
        })
    
    logger.info("Request received", extra={
        "event": "request_start",
        "request_id": g.request_id,
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "unknown")
    })


@app.after_request
def after_request(response):
    """Log every response with duration and trace context."""
    duration_ms = (time.time() - g.start_time) * 1000
    
    span = trace.get_current_span()
    if span:
        span.set_attribute("http.status_code", response.status_code)
        span.set_attribute("http.response_time_ms", round(duration_ms, 2))
        span.add_event("response_sent", {
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2)
        })
    
    logger.info("Request completed", extra={
        "event": "request_end",
        "request_id": g.request_id,
        "method": request.method,
        "path": request.path,
        "status_code": response.status_code,
        "duration_ms": round(duration_ms, 2)
    })
    
    return response


@app.route("/")
def home():
    """Home page with web UI."""
    with tracer.start_as_current_span("home-handler", kind=trace.SpanKind.INTERNAL) as span:
        span.set_attribute("http.route", "/")
        span.set_attribute("handler.name", "home")
        span.set_attribute("response.type", "html")
        
        logger.info("Serving web UI", extra={
            "request_id": g.request_id,
            "handler": "home",
            "response_type": "html"
        })
        
        return render_template_string(HTML_TEMPLATE)


@app.route("/api")
def api_home():
    """API home endpoint with JSON response."""
    with tracer.start_as_current_span("api-home-handler", kind=trace.SpanKind.INTERNAL) as span:
        span.set_attribute("http.route", "/api")
        span.set_attribute("handler.name", "api_home")
        
        logger.info("Processing API home request", extra={
            "request_id": g.request_id,
            "handler": "api_home",
            "action": "processing"
        })
        
        endpoints = ["/", "/api", "/api/users", "/api/orders", "/api/slow", "/error", "/health"]
        span.set_attribute("response.endpoint_count", len(endpoints))
        
        return jsonify({
            "message": "Welcome to the OTEL Demo App API!",
            "endpoints": endpoints,
            "request_id": g.request_id
        })


@app.route("/api/users")
def get_users():
    """Users endpoint with detailed database simulation."""
    with tracer.start_as_current_span("users-handler", kind=trace.SpanKind.INTERNAL) as handler_span:
        handler_span.set_attribute("http.route", "/api/users")
        
        logger.info("Starting user fetch operation", extra={
            "request_id": g.request_id,
            "handler": "get_users",
            "action": "start"
        })
        
        # Validate request
        with tracer.start_as_current_span("validate-request") as val_span:
            val_span.set_attribute("validation.type", "user_request")
            time.sleep(random.uniform(0.002, 0.005))
            val_span.add_event("validation_complete", {"valid": True})
            
            logger.debug("Request validation passed", extra={
                "request_id": g.request_id,
                "validation": "passed"
            })
        
        # Query database
        with tracer.start_as_current_span("db-query", kind=trace.SpanKind.CLIENT) as db_span:
            db_span.set_attribute("db.system", "postgresql")
            db_span.set_attribute("db.name", "users_db")
            db_span.set_attribute("db.operation", "SELECT")
            db_span.set_attribute("db.statement", "SELECT * FROM users WHERE active = true")
            
            query_start = time.time()
            time.sleep(random.uniform(0.01, 0.05))
            query_time = (time.time() - query_start) * 1000
            
            db_span.set_attribute("db.query_time_ms", round(query_time, 2))
            db_span.add_event("query_executed", {
                "rows_returned": 3,
                "query_time_ms": round(query_time, 2)
            })
            
            logger.info("Database query executed", extra={
                "request_id": g.request_id,
                "db_system": "postgresql",
                "db_operation": "SELECT",
                "table": "users",
                "query_time_ms": round(query_time, 2),
                "rows_returned": 3
            })
            
            users = [
                {"id": 1, "name": "Alice", "email": "alice@example.com", "active": True},
                {"id": 2, "name": "Bob", "email": "bob@example.com", "active": True},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com", "active": True},
            ]
        
        # Transform data
        with tracer.start_as_current_span("transform-data") as transform_span:
            transform_span.set_attribute("transform.input_count", len(users))
            time.sleep(random.uniform(0.001, 0.003))
            transform_span.add_event("transform_complete")
            
            logger.debug("Data transformation complete", extra={
                "request_id": g.request_id,
                "user_count": len(users)
            })
        
        handler_span.set_attribute("response.user_count", len(users))
        
        logger.info("User fetch completed successfully", extra={
            "request_id": g.request_id,
            "handler": "get_users",
            "action": "complete",
            "user_count": len(users)
        })
        
        return jsonify({"users": users, "count": len(users), "request_id": g.request_id})


@app.route("/api/orders")
def get_orders():
    """Orders endpoint with complex nested operations."""
    with tracer.start_as_current_span("orders-handler", kind=trace.SpanKind.INTERNAL) as handler_span:
        handler_span.set_attribute("http.route", "/api/orders")
        
        logger.info("Starting order processing", extra={
            "request_id": g.request_id,
            "handler": "get_orders",
            "action": "start"
        })
        
        # Authentication check
        with tracer.start_as_current_span("auth-check") as auth_span:
            auth_span.set_attribute("auth.method", "token")
            time.sleep(random.uniform(0.003, 0.008))
            auth_span.add_event("auth_success", {"user_id": 1})
            
            logger.debug("Authentication verified", extra={
                "request_id": g.request_id,
                "auth_method": "token",
                "auth_result": "success"
            })
        
        # Fetch orders from database
        with tracer.start_as_current_span("db-query-orders", kind=trace.SpanKind.CLIENT) as db_span:
            db_span.set_attribute("db.system", "postgresql")
            db_span.set_attribute("db.name", "orders_db")
            db_span.set_attribute("db.operation", "SELECT")
            db_span.set_attribute("db.statement", "SELECT * FROM orders WHERE status IN ('pending', 'shipped')")
            
            query_start = time.time()
            time.sleep(random.uniform(0.02, 0.06))
            query_time = (time.time() - query_start) * 1000
            
            db_span.set_attribute("db.query_time_ms", round(query_time, 2))
            
            logger.info("Orders query executed", extra={
                "request_id": g.request_id,
                "db_system": "postgresql",
                "table": "orders",
                "query_time_ms": round(query_time, 2),
                "rows_returned": 2
            })
            
            orders = [
                {"id": 101, "user_id": 1, "total": 99.99, "status": "shipped", "items": 3},
                {"id": 102, "user_id": 2, "total": 149.50, "status": "pending", "items": 5},
            ]
        
        # Enrich with user data
        with tracer.start_as_current_span("enrich-user-data") as enrich_span:
            enrich_span.set_attribute("enrichment.type", "user_details")
            time.sleep(random.uniform(0.01, 0.02))
            
            logger.debug("Enriching orders with user data", extra={
                "request_id": g.request_id,
                "order_count": len(orders)
            })
        
        # Calculate totals
        with tracer.start_as_current_span("calculate-totals") as calc_span:
            total_value = sum(o["total"] for o in orders)
            total_items = sum(o["items"] for o in orders)
            calc_span.set_attribute("calculation.total_value", total_value)
            calc_span.set_attribute("calculation.total_items", total_items)
            
            logger.info("Order totals calculated", extra={
                "request_id": g.request_id,
                "total_value": total_value,
                "total_items": total_items,
                "order_count": len(orders)
            })
        
        handler_span.set_attribute("response.order_count", len(orders))
        handler_span.set_attribute("response.total_value", total_value)
        
        logger.info("Order processing completed", extra={
            "request_id": g.request_id,
            "handler": "get_orders",
            "action": "complete",
            "order_count": len(orders),
            "total_value": total_value
        })
        
        return jsonify({
            "orders": orders,
            "summary": {"count": len(orders), "total_value": total_value, "total_items": total_items},
            "request_id": g.request_id
        })


@app.route("/api/slow")
def slow_endpoint():
    """Slow endpoint demonstrating latency tracing."""
    with tracer.start_as_current_span("slow-operation", kind=trace.SpanKind.INTERNAL) as span:
        span.set_attribute("http.route", "/api/slow")
        span.set_attribute("operation.type", "slow_simulation")
        
        delay = random.uniform(0.5, 2.0)
        span.set_attribute("delay.target_seconds", round(delay, 2))
        
        logger.warning("Starting slow operation", extra={
            "request_id": g.request_id,
            "handler": "slow_endpoint",
            "expected_delay_seconds": round(delay, 2),
            "warning_type": "latency"
        })
        
        span.add_event("slow_operation_start", {"target_delay": round(delay, 2)})
        
        # Simulate slow work in phases
        phases = 3
        for i in range(phases):
            with tracer.start_as_current_span(f"slow-phase-{i+1}") as phase_span:
                phase_delay = delay / phases
                phase_span.set_attribute("phase.number", i + 1)
                phase_span.set_attribute("phase.delay", round(phase_delay, 3))
                time.sleep(phase_delay)
                
                logger.debug(f"Slow operation phase {i+1} complete", extra={
                    "request_id": g.request_id,
                    "phase": i + 1,
                    "phase_delay_seconds": round(phase_delay, 3)
                })
        
        span.add_event("slow_operation_complete", {"actual_delay": round(delay, 2)})
        
        logger.warning("Slow operation completed", extra={
            "request_id": g.request_id,
            "handler": "slow_endpoint",
            "actual_delay_seconds": round(delay, 2),
            "warning_type": "latency_complete"
        })
        
        return jsonify({
            "message": "Slow operation completed",
            "delay_seconds": round(delay, 2),
            "phases": phases,
            "request_id": g.request_id
        })


@app.route("/error")
def error_endpoint():
    """Error endpoint with comprehensive error tracing."""
    with tracer.start_as_current_span("error-operation", kind=trace.SpanKind.INTERNAL) as span:
        span.set_attribute("http.route", "/error")
        span.set_attribute("error.simulated", True)
        
        logger.info("Processing error simulation request", extra={
            "request_id": g.request_id,
            "handler": "error_endpoint",
            "action": "start"
        })
        
        try:
            # Simulate some work before error
            with tracer.start_as_current_span("pre-error-work") as work_span:
                time.sleep(random.uniform(0.01, 0.02))
                work_span.add_event("work_in_progress")
                
                logger.debug("Pre-error processing", extra={
                    "request_id": g.request_id,
                    "stage": "pre_error"
                })
            
            # Simulate error
            error_type = random.choice(["ValueError", "RuntimeError", "KeyError"])
            span.set_attribute("error.type", error_type)
            span.add_event("error_triggered", {"error_type": error_type})
            
            if error_type == "ValueError":
                raise ValueError("Simulated validation error - invalid input data")
            elif error_type == "RuntimeError":
                raise RuntimeError("Simulated runtime error - service unavailable")
            else:
                raise KeyError("Simulated key error - missing configuration")
                
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            
            logger.error("Error occurred during request processing", extra={
                "request_id": g.request_id,
                "handler": "error_endpoint",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "status_code": 500
            })
            
            logger.error("Error details for debugging", extra={
                "request_id": g.request_id,
                "exception_class": type(e).__name__,
                "exception_args": str(e.args),
                "recovery_action": "retry_recommended"
            })
            
            return jsonify({
                "error": str(e),
                "error_type": type(e).__name__,
                "request_id": g.request_id
            }), 500


@app.route("/health")
def health():
    """Health check with minimal logging."""
    with tracer.start_as_current_span("health-check") as span:
        span.set_attribute("health.status", "healthy")
        return jsonify({"status": "healthy", "service": "sample-app"})


if __name__ == "__main__":
    logger.info("Application starting", extra={
        "action": "startup",
        "otlp_endpoint": otlp_endpoint,
        "service": "sample-app",
        "version": "1.0.0"
    })
    app.run(host="0.0.0.0", port=8080, debug=False)
