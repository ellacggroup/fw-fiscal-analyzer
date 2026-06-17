FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install Node.js for frontend build
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Build the frontend
COPY frontend/package*.json frontend/
RUN cd frontend && npm install

COPY frontend/ frontend/
RUN cd frontend && npm run build

# Copy the backend
COPY backend/ backend/

# Ensure /data directory exists for the SQLite database (Railway volume mounts here)
RUN mkdir -p /data

CMD find /app -name "__pycache__" -type d | xargs rm -rf 2>/dev/null; \
    cd /app/backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
