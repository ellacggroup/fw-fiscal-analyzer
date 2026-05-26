FROM python:3.12-slim

# Install Node.js 20 for building the React frontend
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

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

# Start the server (Railway injects $PORT automatically)
CMD cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
