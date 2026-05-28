FROM python:3.12-slim

# Install Node.js 20 for building the React frontend
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Prevent Python from writing .pyc files so stale bytecode never persists
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Install and build the React frontend
COPY frontend/package*.json frontend/
RUN cd frontend && npm install

COPY frontend/ frontend/
RUN cd frontend && npm run build

# Copy the rest of the backend
COPY backend/ backend/

# Ensure /data directory exists for the SQLite database (Railway volume mounts here)
RUN mkdir -p /data

# Start the server — clear any stale bytecode first, then launch
# (Railway preserves runtime files across redeploys; this guarantees fresh code)
CMD find /app -name "__pycache__" -type d | xargs rm -rf 2>/dev/null; \
    echo "=== STARTUP: main.py version ===" && \
    grep version /app/backend/main.py && \
    cd /app/backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
