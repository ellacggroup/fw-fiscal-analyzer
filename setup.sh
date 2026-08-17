#!/usr/bin/env bash
# macOS/Linux equivalent of setup.bat — first-time setup.
set -euo pipefail
cd "$(dirname "$0")"

echo
echo "==================================================="
echo "  Fort Worth Fiscal Impact Analyzer — Setup"
echo "==================================================="
echo

# ── Locate Python 3.12 (matches the Dockerfile/production runtime) ──
if command -v python3.12 >/dev/null 2>&1; then
    PY=python3.12
elif [ -x /opt/homebrew/bin/python3.12 ]; then
    PY=/opt/homebrew/bin/python3.12
else
    echo "  Python 3.12 not found. Install it with:"
    echo "    brew install python@3.12"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "  Node.js/npm not found. Install it with:"
    echo "    brew install node"
    exit 1
fi

# ── Backend ────────────────────────────────────────────
echo "  Creating the Python environment..."
[ -d backend/venv ] || "$PY" -m venv backend/venv
backend/venv/bin/pip install --upgrade pip -q
echo "  Installing backend packages (this takes a minute)..."
backend/venv/bin/pip install -q -r backend/requirements.txt

# ── Frontend ───────────────────────────────────────────
echo "  Installing the webpage interface..."
cd frontend
npm install
# npm >=11 blocks native postinstall scripts by default; esbuild needs its binary.
npm install-scripts approve esbuild >/dev/null 2>&1 || true
npm install-scripts approve fsevents >/dev/null 2>&1 || true
npm rebuild esbuild >/dev/null 2>&1 || true
cd ..

echo
echo "  Setup complete. Run ./start.sh to launch the app."
echo
