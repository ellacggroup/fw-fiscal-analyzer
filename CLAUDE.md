# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

**First-time setup** (installs Python venv + npm deps):
```
setup.bat
```

**Claude AI (optional):** Create `backend/.env` with your Anthropic API key:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Without it, the app falls back to rule-based analysis automatically.

**Start both servers** (opens browser automatically):
```
start.bat
```

- Backend: `http://localhost:8000` (FastAPI + uvicorn, auto-reload enabled)
- Frontend: `http://localhost:5173` (Vite dev server)

**Manual start (if needed):**
```
# Backend
cd backend && venv\Scripts\activate && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

**Frontend build:**
```
cd frontend && npm run build
```

## Architecture

This is a two-process local app with no external dependencies or API keys:

```
PDF upload → FastAPI → pdf_parser → fiscal_analyzer → SQLite → React frontend
```

**Backend** (`backend/`) — Python/FastAPI:
- `main.py` — app wiring, CORS (allows ports 5173 and 3000), startup hook
- `database.py` — SQLAlchemy models (`AgendaUpload`, `AgendaItem`) backed by `fw_fiscal.db` (SQLite, created on startup)
- `routers/agendas.py` — three endpoints: `POST /agendas/upload`, `GET /agendas/`, `GET /agendas/{id}`
- `services/pdf_parser.py` — extracts text with `pdfplumber`, then parses Fort Worth agenda structure (M&C references, numbered items, section headers) into structured dicts
- `services/fiscal_analyzer.py` — rule-based fiscal engine; no ML, no API calls

**Frontend** (`frontend/`) — React 18 + Vite + Tailwind:
- `src/App.jsx` — all state lives here: upload flow, agenda history, active filter
- `src/services/api.js` — thin axios wrapper; `baseURL: ''` so Vite's proxy routes `/agendas/*` to the backend
- Components are purely presentational: `UploadZone`, `FiscalCard`, `HistorySidebar`, `SummaryBar`

## Fiscal Analysis Engine

`fiscal_analyzer.py` is the core domain logic. Key things to know:

- **`PARAMETERS`** dict at the top contains all Fort Worth fiscal constants (tax rates, service costs, projection assumptions). Update these when city data changes.
- **`LAND_USE_PROTOTYPES`** contains per-acre revenue/cost estimates for 8 land-use types, each with an `rc_ratio` (revenue-to-cost). R/C ≥ 1.0 = POSITIVE, ≥ 0.85 = NEUTRAL, < 0.85 = NEGATIVE.
- **`analyze_fiscal_impact(item)`** is the entry point — classifies the item by category and land use via keyword matching, extracts dollar amounts and acreage via regex, then dispatches to a category-specific function (`_land_use_analysis`, `_contract_analysis`, `_budget_analysis`, `_infrastructure_analysis`, `_policy_analysis`).
- **`_project_40yr()`** computes the 40-year NPV and cumulative net using the Fate TX methodology (2.5% growth, 3% discount rate).
- The analysis result dict schema is fixed — the frontend's `FiscalCard` component renders it directly. Adding new keys to the result is safe; removing or renaming existing keys will break the UI.

## PDF Parser

`pdf_parser.py` has two extraction modes:
1. **Primary**: Line-by-line scan tracking section headers, M&C/ZC/SP reference numbers, and numbered item prefixes. Skips ceremonial sections (call to order, invocation, etc.).
2. **Fallback** (`_fallback_extraction`): Used when primary finds < 2 items — grabs any line 20–200 chars that isn't all-caps.

The parser works best with text-based PDFs; scanned/image PDFs return empty text and are rejected with a 400 error.

## Data Persistence

SQLite file `backend/fw_fiscal.db` is created on first run and is not committed to version control. `AgendaUpload` stores metadata + raw text (truncated at 100k chars). `AgendaItem` stores the structured item plus the full `analysis` JSON blob.
