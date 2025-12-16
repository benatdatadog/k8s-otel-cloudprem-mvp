"""
Sample Flask application with OpenTelemetry instrumentation.
Demonstrates traces, metrics, and logs being sent via OTLP.
"""

import logging
import random
import time
from flask import Flask, jsonify
import os

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

# Create logging handler that sends to OTLP
otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

# Configure Python logging with OTLP handler
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.addHandler(otel_handler)

# Create Flask app
app = Flask(__name__)

# Instrument Flask and requests library
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()


@app.route("/")
def home():
    """Home endpoint - returns a welcome message."""
    logger.info("Home endpoint called")
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
        
    logger.info(f"Returned {len(users)} users")
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
        
    logger.info(f"Returned {len(orders)} orders")
    return jsonify({"orders": orders})


@app.route("/api/slow")
def slow_endpoint():
    """Simulates a slow endpoint for testing latency visibility."""
    with tracer.start_as_current_span("slow-operation") as span:
        delay = random.uniform(0.5, 2.0)
        span.set_attribute("delay.seconds", delay)
        time.sleep(delay)
        
    logger.warning(f"Slow endpoint completed after {delay:.2f}s")
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
            logger.error(f"Error occurred: {e}")
            return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    logger.info("Starting Sample App with OpenTelemetry instrumentation")
    logger.info(f"OTLP Endpoint: {otlp_endpoint}")
    app.run(host="0.0.0.0", port=8080, debug=False)

