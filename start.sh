#!/usr/bin/env bash
# macOS/Linux equivalent of start.bat — runs backend + frontend, opens the browser.
cd "$(dirname "$0")"

echo
echo "==================================================="
echo "  Fort Worth Fiscal Impact Analyzer"
echo "==================================================="
echo

# ── Check setup was completed ──────────────────────────
if [ ! -x backend/venv/bin/python ]; then
    echo "  The app is not set up yet. Run ./setup.sh first."
    exit 1
fi
if [ ! -d frontend/node_modules ]; then
    echo "  The webpage interface is not set up yet. Run ./setup.sh first."
    exit 1
fi

# ── Kill any stale servers on 8000 / 5173 ──────────────
echo "  Clearing any previous instances..."
lsof -ti tcp:8000 | xargs kill -9 2>/dev/null || true
lsof -ti tcp:5173 | xargs kill -9 2>/dev/null || true

# ── Clear Python bytecode cache ────────────────────────
find backend -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# ── Shut both servers down together on Ctrl+C ──────────
cleanup() {
    echo
    echo "  Shutting down..."
    kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

# ── Start backend ──────────────────────────────────────
echo "  Starting the backend..."
( cd backend && exec ./venv/bin/uvicorn main:app --reload --port 8000 ) &
BACKEND_PID=$!

printf "  Waiting for backend to be ready"
for _ in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then break; fi
    printf "."
    sleep 1
done
echo

# ── Start frontend ─────────────────────────────────────
echo "  Starting the webpage interface..."
( cd frontend && exec npm run dev ) &
FRONTEND_PID=$!
sleep 4

echo
echo "==================================================="
echo "  App is running!  Open: http://localhost:5173"
echo "  Press Ctrl+C in this window to stop both servers."
echo "==================================================="
echo

open "http://localhost:5173" 2>/dev/null || true
wait
