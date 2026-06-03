FROM python:3.12-slim

# Prevent Python from writing .pyc files so stale bytecode never persists
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy pre-built frontend (dist is committed to the repo)
COPY frontend/dist/ frontend/dist/

# Copy the backend
COPY backend/ backend/

# Ensure /data directory exists for the SQLite database (Railway volume mounts here)
RUN mkdir -p /data

# Start the server — clear any stale bytecode first, then launch
# (Railway preserves runtime files across redeploys; this guarantees fresh code)
CMD find /app -name "__pycache__" -type d | xargs rm -rf 2>/dev/null; \
    cd /app/backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
