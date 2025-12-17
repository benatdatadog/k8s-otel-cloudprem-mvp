"""Gunicorn configuration with JSON logging."""
import json
import datetime

# Server settings
bind = "0.0.0.0:8080"
workers = 2

# Disable default access log (we use custom JSON format in post_request)
accesslog = None
errorlog = "-"
loglevel = "info"

def get_header(headers, name, default="-"):
    """Get header value from gunicorn headers list."""
    for header_name, header_value in headers:
        if header_name.lower() == name.lower():
            return header_value
    return default

def post_request(worker, req, environ, resp):
    """Log each request in JSON format."""
    status_code = resp.status.split()[0] if hasattr(resp, 'status') else "200"
    log_data = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "level": "INFO",
        "service": "sample-app",
        "logger": "gunicorn.access",
        "message": f"{req.method} {req.path} {status_code}",
        "http": {
            "method": req.method,
            "path": req.path,
            "status_code": int(status_code),
            "user_agent": get_header(req.headers, "User-Agent"),
        },
        "network": {
            "client_ip": environ.get("REMOTE_ADDR", "-"),
        }
    }
    print(json.dumps(log_data), flush=True)

def on_starting(server):
    """Log when server starts."""
    log_data = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "level": "INFO", 
        "service": "sample-app",
        "logger": "gunicorn",
        "message": "Gunicorn server starting",
        "workers": workers,
        "bind": bind
    }
    print(json.dumps(log_data), flush=True)

