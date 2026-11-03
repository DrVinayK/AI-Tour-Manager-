FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# For backend (FastAPI)
CMD ["uvicorn", "Backend_main_new:app", "--host", "0.0.0.0", "--port", "8000"]

# For frontend (Flask) - uncomment the appropriate CMD
# CMD ["gunicorn", "--workers", "2", "--worker-class", "sync", "--timeout", "120", "--bind", "0.0.0.0:8000", "app:app"]
