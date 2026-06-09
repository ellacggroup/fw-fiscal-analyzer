"""
Bulk import router — scrapes Fort Worth Legistar for all City Council
agendas and meeting minutes from the past N years and processes them.

Endpoints:
  POST /bulk-import/start        — kick off a background import job
  GET  /bulk-import/status/{id}  — poll job progress
  GET  /bulk-import/jobs         — list recent jobs
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from database import (
    AgendaItem, AgendaUpload, BulkImportJob, get_db, SessionLocal,
)
from services.legistar_scraper import get_council_meetings, fetch_pdf_bytes_lenient
from services.pdf_parser import detect_meeting_date, extract_agenda_items, extract_text_from_pdf
from services.fiscal_analyzer import analyze_fiscal_impact
from services.claude_analyzer import analyze_items_with_claude, claude_available
from services.vote_parser import associate_votes_to_items, summarize_votes
from services.alert_matcher import run_alert_matching
from services.proximity_matcher import run_proximity_matching

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bulk-import", tags=["bulk-import"])

# ── Target categories we care about ──────────────────────────────────────────
RELEVANT_CATEGORIES = {
    "Zoning Change",
    "Economic Incentive",
    "Site Plan / Plat",
    "Impact / Development Fees",
    "Land Use / Comp Plan",
    "Development Agreement",
    "Platting",
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_bulk_import(
    background_tasks: BackgroundTasks,
    payload: dict = Body(default={"years": 5}),
    db: Session = Depends(get_db),
):
    """Kick off background scrape + import for the past N years (default 5)."""
    years = max(1, min(int(payload.get("years", 5)), 10))

    job = BulkImportJob(status="pending", log=[])
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id

    background_tasks.add_task(_run_import, job_id, years)
    return {"job_id": job_id, "status": "pending", "years": years}


@router.get("/status/{job_id}")
def get_job_status(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job)


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(BulkImportJob).order_by(BulkImportJob.id.desc()).limit(10).all()
    return [_serialize_job(j) for j in jobs]


# ── Background task ───────────────────────────────────────────────────────────

def _serialize_job(job: BulkImportJob) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "total_meetings": job.total_meetings,
        "processed_agendas": job.processed_agendas,
        "processed_minutes": job.processed_minutes,
        "skipped": job.skipped,
        "errors": job.errors,
        "log": (job.log or [])[-50:],  # last 50 log lines
    }


def _update_job(db: Session, job: BulkImportJob, **kwargs):
    for k, v in kwargs.items():
        setattr(job, k, v)
    db.commit()


def _append_log(db: Session, job: BulkImportJob, msg: str):
    log = list(job.log or [])
    log.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")
    job.log = log
    db.commit()
    logger.info(f"[job {job.id}] {msg}")


def _run_import(job_id: int, years: int):
    """Background task: scrape Legistar and process each meeting."""
    db = SessionLocal()
    try:
        job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
        if not job:
            return

        _update_job(db, job, status="running")
        _append_log(db, job, f"Starting bulk import for the past {years} years")

        # ── Step 1: Get meeting list from Legistar ─────────────────────────
        _append_log(db, job, "Fetching meeting list from Fort Worth Legistar...")
        meetings = get_council_meetings(years=years)

        if not meetings:
            _update_job(db, job, status="error", completed_at=datetime.utcnow())
            _append_log(db, job, "ERROR: No meetings returned from Legistar. Check API connectivity.")
            return

        _update_job(db, job, total_meetings=len(meetings))
        _append_log(db, job, f"Found {len(meetings)} meetings with documents")

        # Sort oldest-first so history builds chronologically
        meetings_sorted = sorted(meetings, key=lambda m: m.get("date", ""))

        # ── Step 2: Process each meeting ───────────────────────────────────
        for i, meeting in enumerate(meetings_sorted):
            date = meeting.get("date", "unknown")
            _append_log(db, job, f"[{i+1}/{len(meetings_sorted)}] Processing {date}...")

            # Process agenda PDF
            if meeting.get("agenda_url"):
                success = _process_agenda_url(
                    db, job, meeting["agenda_url"], date, "agenda"
                )
                if success:
                    job.processed_agendas = (job.processed_agendas or 0) + 1
                    db.commit()

            # Process minutes PDF (vote extraction)
            if meeting.get("minutes_url"):
                success = _process_minutes_url(
                    db, job, meeting["minutes_url"], date
                )
                if success:
                    job.processed_minutes = (job.processed_minutes or 0) + 1
                    db.commit()

        _update_job(db, job, status="complete", completed_at=datetime.utcnow())
        _append_log(
            db, job,
            f"Import complete — {job.processed_agendas} agendas, "
            f"{job.processed_minutes} minutes sets, "
            f"{job.skipped} skipped, {job.errors} errors"
        )

    except Exception as e:
        logger.exception(f"Bulk import job {job_id} failed")
        try:
            job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
            if job:
                _update_job(db, job, status="error", completed_at=datetime.utcnow())
                _append_log(db, job, f"FATAL ERROR: {e}")
        except Exception:
            pass
    finally:
        db.close()


def _process_agenda_url(
    db: Session, job: BulkImportJob, url: str, date: str, doc_type: str
) -> bool:
    """
    Download, parse, and store one agenda PDF.
    Returns True on success, False on failure/skip.
    """
    # Skip if we already have an agenda for this meeting date
    if date and date != "unknown":
        existing = (
            db.query(AgendaUpload)
            .filter(
                AgendaUpload.meeting_date == date,
                AgendaUpload.document_type == "agenda",
            )
            .first()
        )
        if existing:
            _append_log(db, job, f"  Skipping {date} agenda (already imported)")
            job.skipped = (job.skipped or 0) + 1
            db.commit()
            return False

    pdf_bytes = fetch_pdf_bytes_lenient(url)
    if not pdf_bytes:
        _append_log(db, job, f"  Could not download agenda PDF: {url[:80]}")
        job.errors = (job.errors or 0) + 1
        db.commit()
        return False

    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
        if not raw_text.strip():
            _append_log(db, job, f"  No text extracted from {date} agenda (scanned PDF?)")
            job.skipped = (job.skipped or 0) + 1
            db.commit()
            return False

        meeting_date = detect_meeting_date(raw_text) or date
        raw_items = extract_agenda_items(raw_text)

        if not raw_items:
            _append_log(db, job, f"  No items parsed from {date} agenda")
            job.skipped = (job.skipped or 0) + 1
            db.commit()
            return False

        # Rule-based analysis only for bulk import (skip Claude to save time/cost)
        rule_analyses = [analyze_fiscal_impact(item) for item in raw_items]

        # Filter to relevant categories only for bulk import
        relevant_pairs = [
            (item, analysis)
            for item, analysis in zip(raw_items, rule_analyses)
            if _is_relevant(analysis, item)
        ]

        if not relevant_pairs:
            _append_log(db, job, f"  {date}: no relevant items found (all filtered)")
            job.skipped = (job.skipped or 0) + 1
            db.commit()
            return False

        display_name = f"City Council Meeting – {meeting_date}"

        upload = AgendaUpload(
            filename=display_name,
            meeting_date=meeting_date,
            raw_text=raw_text[:100_000],
            item_count=len(relevant_pairs),
            source_url=url,
            document_type="agenda",
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)

        for item_data, analysis in relevant_pairs:
            cat = _infer_category(analysis, item_data.get("section", ""))
            db_item = AgendaItem(
                upload_id=upload.id,
                item_number=item_data.get("item_number"),
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                section=item_data.get("section", ""),
                category=cat,
                analysis=analysis,
            )
            db.add(db_item)
        db.commit()

        # Run alert + proximity matching
        try:
            run_alert_matching(upload.id, db)
        except Exception:
            pass
        try:
            run_proximity_matching(upload.id, db)
        except Exception:
            pass

        _append_log(db, job, f"  {date}: saved {len(relevant_pairs)} relevant items")
        return True

    except Exception as e:
        _append_log(db, job, f"  ERROR processing {date} agenda: {e}")
        job.errors = (job.errors or 0) + 1
        db.commit()
        return False


def _process_minutes_url(
    db: Session, job: BulkImportJob, url: str, date: str
) -> bool:
    """
    Download minutes PDF and extract votes, matching them to stored agenda items.
    Returns True on success.
    """
    pdf_bytes = fetch_pdf_bytes_lenient(url)
    if not pdf_bytes:
        _append_log(db, job, f"  Could not download minutes PDF for {date}")
        job.errors = (job.errors or 0) + 1
        db.commit()
        return False

    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
        if not raw_text.strip():
            return False

        # Detect date from minutes text if not provided
        meeting_date = detect_meeting_date(raw_text) or date

        # Extract vote associations from minutes text
        votes_by_ref = associate_votes_to_items(raw_text)
        if not votes_by_ref:
            _append_log(db, job, f"  {date} minutes: no vote records parsed")
            return True

        # Find the agenda upload for this meeting date
        upload = (
            db.query(AgendaUpload)
            .filter(
                AgendaUpload.meeting_date == meeting_date,
                AgendaUpload.document_type == "agenda",
            )
            .first()
        )

        if not upload:
            # Store minutes as its own upload record so votes aren't lost
            upload = AgendaUpload(
                filename=f"City Council Minutes – {meeting_date}",
                meeting_date=meeting_date,
                raw_text=raw_text[:100_000],
                item_count=0,
                source_url=url,
                document_type="minutes",
            )
            db.add(upload)
            db.commit()
            db.refresh(upload)
            _append_log(db, job, f"  {date} minutes: stored (no matching agenda found)")
            return True

        # Match votes to agenda items by case number reference
        items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload.id).all()
        matched = 0
        for item in items:
            item_refs = _extract_item_refs(item)
            for ref in item_refs:
                if ref in votes_by_ref:
                    item.votes = summarize_votes(votes_by_ref[ref])
                    db.commit()
                    matched += 1
                    break

        _append_log(db, job, f"  {date} minutes: matched votes to {matched}/{len(items)} items")
        return True

    except Exception as e:
        _append_log(db, job, f"  ERROR processing {date} minutes: {e}")
        job.errors = (job.errors or 0) + 1
        db.commit()
        return False


def _extract_item_refs(item: AgendaItem) -> list[str]:
    """Extract case/M&C numbers from an agenda item to match against vote records."""
    import re
    text = f"{item.item_number or ''} {item.title or ''} {item.description or ''}"
    pattern = re.compile(
        r'\b(?:'
        r'(?:M&?C)\s+(?:[A-Z]-\d{4,6}|\d{2}-\d{4,6})|'
        r'ZC-\d{2}-\d{3,6}|'
        r'SP-\d{2}-\d{3,6}|'
        r'AX-\d{2}-\d{3,6}|'
        r'FP-\d{2}-\d{3,6}|'
        r'PP-\d{2}-\d{3,6}|'
        r'RP-\d{2}-\d{3,6}'
        r')',
        re.IGNORECASE
    )
    refs = [m.group(0).upper() for m in pattern.finditer(text)]
    return refs


def _is_relevant(analysis: dict, item: dict) -> bool:
    """Return True if this item belongs to one of our target categories."""
    cat = _infer_category(analysis, item.get("section", ""))
    return cat in RELEVANT_CATEGORIES


def _infer_category(analysis: dict, section: str = "") -> str:
    """Mirror of routers/agendas._infer_category_label."""
    cat = analysis.get("category", "")
    if cat and cat not in ("Other", "Administrative", "Personnel"):
        return cat

    sec = (section or "").upper()
    if "ZONING" in sec:
        return "Zoning Change"
    if "PUBLIC HEARING" in sec:
        return cat or "Other"
    if "LAND" in sec:
        return "Land Use / Comp Plan"
    return cat or "Other"
