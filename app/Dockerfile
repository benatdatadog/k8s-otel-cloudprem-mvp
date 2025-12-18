FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .
COPY gunicorn_config.py .

# Expose port
EXPOSE 8080

# Run with gunicorn with JSON logging
CMD ["gunicorn", "--config", "gunicorn_config.py", "main:app"]

