import os
from dotenv import load_dotenv

# Load .env before anything else so ANTHROPIC_API_KEY is available
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from database import init_db
from routers import agendas
from routers import export as export_router
from routers import parcels as parcels_router
from routers import staff_reports as staff_reports_router
from routers import alerts as alerts_router
from routers import analytics as analytics_router
from routers import competitive as competitive_router
from routers import bulk_import as bulk_import_router
from services.claude_analyzer import claude_available

app = FastAPI(
    title="Fort Worth Fiscal Impact Analyzer",
    description="AI-powered fiscal analysis for Fort Worth City Council agenda items",
    version="3.0.0",
)

# In production (Railway) we don't know the URL ahead of time, so allow all origins.
# For a private internal tool this is fine.
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agendas.router)
app.include_router(export_router.router)
app.include_router(parcels_router.router)
app.include_router(staff_reports_router.router)
app.include_router(alerts_router.router)
app.include_router(analytics_router.router)
app.include_router(competitive_router.router)
app.include_router(bulk_import_router.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Fort Worth Fiscal Impact Analyzer",
        "claude_enabled": claude_available(),
        "version": "3.5.0",
        "build": "2026-05-28-all-fixes",
    }


# ── Serve the React frontend (production build) ──────────────────────────────
# When deployed to Railway, the frontend is built and the dist folder sits
# next to the backend. In local development, Vite's dev server handles this
# instead, so we only mount static files if the dist folder exists.

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(_frontend_dist):
    # Serve JS/CSS/image assets
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_frontend_dist, "assets")),
        name="assets",
    )

    # Serve the SPA index.html for all other non-API paths
    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
