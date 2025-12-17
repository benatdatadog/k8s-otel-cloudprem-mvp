"""
Sample Flask application with OpenTelemetry instrumentation.
Demonstrates traces, metrics, and logs being sent via OTLP.
Logs are output in JSON format for easy parsing.
"""

import logging
import random
import time
import json
from flask import Flask, jsonify, request
import os

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

# Configure OpenTelemetry Resource
resource = Resource.create({
    "service.name": os.getenv("OTEL_SERVICE_NAME", "sample-app"),
    "service.version": "1.0.0",
    "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "demo"),
})

# OTLP endpoint
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

# Set up tracer provider
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)

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

# Create logging handler that sends to OTLP (silent - no console output)
otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

# Configure JSON logging format with trace correlation
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        log_record['service'] = 'sample-app'
        log_record['environment'] = os.getenv("OTEL_ENVIRONMENT", "demo")
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        
        # Use ISO format timestamp
        import datetime
        log_record['timestamp'] = datetime.datetime.utcfromtimestamp(record.created).isoformat() + "Z"
        
        # Inject standard OTLP trace context (vendor-agnostic)
        # Datadog and other backends can correlate using W3C trace context format
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            # Standard OTLP format: 128-bit trace_id, 64-bit span_id (hex)
            log_record['trace_id'] = format(ctx.trace_id, '032x')
            log_record['span_id'] = format(ctx.span_id, '016x')

# Set up JSON formatter for console output
json_formatter = CustomJsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s'
)

# Configure root logger with JSON format
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Clear all existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# JSON handler for stdout (for container logs / Datadog)
import sys
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(json_formatter)
console_handler.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

# OTLP handler for sending to OpenTelemetry Collector
root_logger.addHandler(otel_handler)

# Suppress noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("opentelemetry").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# Instrument Flask and requests library
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()


@app.route("/")
def home():
    """Home endpoint - returns a welcome message."""
    with tracer.start_as_current_span("home-handler") as span:
        span.set_attribute("http.route", "/")
        logger.info("Home endpoint called", extra={
            "endpoint": "/",
            "method": "GET",
            "action": "home"
        })
        return jsonify({
            "message": "Welcome to the OTEL Demo App!",
            "endpoints": ["/", "/api/users", "/api/orders", "/api/slow", "/error", "/health"]
        })


@app.route("/api/users")
def get_users():
    """Simulates fetching users with some processing time."""
    with tracer.start_as_current_span("fetch-users-from-db") as span:
        # Simulate database query
        time.sleep(random.uniform(0.01, 0.05))
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", "SELECT")
        span.set_attribute("db.table", "users")
        
        users = [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
            {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
        ]
        span.set_attribute("user.count", len(users))
        
        # Log inside span for trace correlation
        logger.info("Fetched users from database", extra={
            "endpoint": "/api/users",
            "method": "GET",
            "action": "fetch_users",
            "user_count": len(users),
            "db_system": "postgresql"
        })
        return jsonify({"users": users})


@app.route("/api/orders")
def get_orders():
    """Simulates fetching orders with nested spans."""
    with tracer.start_as_current_span("process-orders") as span:
        # Simulate multiple operations
        with tracer.start_as_current_span("validate-request"):
            time.sleep(random.uniform(0.005, 0.01))
        
        with tracer.start_as_current_span("fetch-orders-from-db") as db_span:
            time.sleep(random.uniform(0.02, 0.08))
            db_span.set_attribute("db.system", "postgresql")
            db_span.set_attribute("db.operation", "SELECT")
            
        with tracer.start_as_current_span("enrich-order-data"):
            time.sleep(random.uniform(0.01, 0.03))
            
        orders = [
            {"id": 101, "user_id": 1, "total": 99.99, "status": "shipped"},
            {"id": 102, "user_id": 2, "total": 149.50, "status": "pending"},
        ]
        span.set_attribute("order.count", len(orders))
        
        # Log inside span for trace correlation
        logger.info("Fetched orders from database", extra={
            "endpoint": "/api/orders",
            "method": "GET",
            "action": "fetch_orders",
            "order_count": len(orders),
            "db_system": "postgresql"
        })
        return jsonify({"orders": orders})


@app.route("/api/slow")
def slow_endpoint():
    """Simulates a slow endpoint for testing latency visibility."""
    with tracer.start_as_current_span("slow-operation") as span:
        delay = random.uniform(0.5, 2.0)
        span.set_attribute("delay.seconds", delay)
        time.sleep(delay)
        
        # Log inside span for trace correlation
        logger.warning("Slow endpoint completed", extra={
            "endpoint": "/api/slow",
            "method": "GET",
            "action": "slow_operation",
            "delay_seconds": round(delay, 2),
            "warning_type": "latency"
        })
        return jsonify({"message": "Slow operation completed", "delay": delay})


@app.route("/error")
def error_endpoint():
    """Simulates an error for testing error tracing."""
    with tracer.start_as_current_span("error-operation") as span:
        try:
            # Simulate an error condition
            span.set_attribute("error.simulated", True)
            raise ValueError("Simulated error for testing!")
        except ValueError as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logger.error("Error occurred in request", extra={
                "endpoint": "/error",
                "method": "GET",
                "action": "error_simulation",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "status_code": 500
            })
            return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    logger.info("Application starting", extra={
        "action": "startup",
        "otlp_endpoint": otlp_endpoint,
        "host": "0.0.0.0",
        "port": 8080
    })
    app.run(host="0.0.0.0", port=8080, debug=False)

