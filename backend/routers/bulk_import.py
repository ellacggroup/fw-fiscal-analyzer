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
from services.vote_parser import associate_votes_to_items, summarize_votes, extract_districts_from_ref
from services.alert_matcher import run_alert_matching
from services.proximity_matcher import run_proximity_matching
from services.youtube_votes import get_youtube_votes_for_date

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bulk-import", tags=["bulk-import"])

# ── Target categories — all items that affect real estate or RE development ───
RELEVANT_CATEGORIES = {
    # Core development approvals
    "Zoning Change",
    "Site Plan / Plat",
    "Platting",
    "Land Use / Comp Plan",
    # Financial tools
    "Economic Incentive",
    "Development Agreement",
    "TIRZ / Tax Increment",
    "Public Improvement District",
    "Impact / Development Fees",
    # Property and infrastructure
    "Annexation",
    "Right-of-Way / Easement",
    "Land Acquisition / Disposition",
    "Utility Extension / Infrastructure",
    # Regulatory
    "Development Code / Standards",
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


@router.post("/reprocess-votes")
async def reprocess_votes(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Re-run vote extraction on all imported agendas.
    Re-downloads minutes PDFs and falls back to YouTube for meetings
    without published minutes. Useful after fixing the vote parser.
    """
    job = BulkImportJob(status="pending", log=[])
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    background_tasks.add_task(_run_reprocess_votes, job_id)
    return {"job_id": job_id, "status": "pending"}


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


@router.post("/sync-youtube-votes")
async def sync_youtube_votes_endpoint(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Pull Fort Worth council meeting transcripts from YouTube and apply
    vote pass/fail data to all imported agenda items that lack vote data.
    Covers recent meetings where Legistar minutes aren't published yet.
    """
    job = BulkImportJob(status="pending", log=[])
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_youtube_vote_sync, job.id)
    return {"job_id": job.id, "status": "pending"}


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

            # Process minutes PDF (vote extraction); fall back to YouTube
            if meeting.get("minutes_url"):
                success = _process_minutes_url(
                    db, job, meeting["minutes_url"], date
                )
                if success:
                    job.processed_minutes = (job.processed_minutes or 0) + 1
                    db.commit()
            else:
                # No minutes on Legistar yet — try YouTube transcript
                _process_youtube_votes(db, job, date)

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


def _run_youtube_vote_sync(job_id: int):
    """Fetch YouTube transcripts and apply vote data to imported agenda items."""
    from services.youtube_votes import sync_youtube_votes
    db = SessionLocal()
    try:
        job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
        if not job:
            return
        _update_job(db, job, status="running")
        _append_log(db, job, "Fetching Fort Worth council meeting videos from YouTube...")

        # Get all unique meeting dates that have imported agendas
        uploads = (
            db.query(AgendaUpload)
            .filter(AgendaUpload.document_type == "agenda")
            .all()
        )
        # Normalize stored dates to ISO
        iso_dates = []
        date_to_upload: dict[str, list] = {}
        for upload in uploads:
            iso = _normalize_date_to_iso(upload.meeting_date or "")
            if iso:
                iso_dates.append(iso)
                date_to_upload.setdefault(iso, []).append(upload)

        iso_dates = list(set(iso_dates))
        _update_job(db, job, total_meetings=len(iso_dates))
        _append_log(db, job, f"Looking for YouTube videos for {len(iso_dates)} meeting dates...")

        # Batch-fetch all transcripts
        all_votes = sync_youtube_votes(iso_dates)
        _append_log(db, job, f"Got transcripts for {len(all_votes)} dates")

        total_matched = 0
        for iso_date, votes_by_ref in all_votes.items():
            _append_log(db, job, f"  {iso_date}: {len(votes_by_ref)} vote refs from YouTube")
            for upload in date_to_upload.get(iso_date, []):
                items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload.id).all()
                matched = 0
                for item in items:
                    # Skip items that already have good PDF vote data
                    if item.votes and item.votes.get("source") != "youtube":
                        continue
                    item_refs = _extract_item_refs(item)
                    for ref in item_refs:
                        if ref in votes_by_ref:
                            item.votes = summarize_votes(votes_by_ref[ref])
                            if not item.districts and votes_by_ref[ref].get("districts"):
                                item.districts = votes_by_ref[ref]["districts"]
                            matched += 1
                            break
                db.commit()
                if matched:
                    total_matched += matched
                    job.processed_minutes = (job.processed_minutes or 0) + 1
                    db.commit()
                    _append_log(db, job, f"  {iso_date}: applied {matched}/{len(items)} votes")

        _update_job(db, job, status="complete", completed_at=datetime.utcnow())
        _append_log(db, job, f"YouTube sync complete — {total_matched} items got vote data across {len(all_votes)} meetings")

    except Exception as e:
        logger.exception(f"YouTube vote sync job {job_id} failed")
        try:
            job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
            if job:
                _update_job(db, job, status="error", completed_at=datetime.utcnow())
                _append_log(db, job, f"FATAL ERROR: {e}")
        except Exception:
            pass
    finally:
        db.close()


def _normalize_date_to_iso(date_str: str) -> Optional[str]:
    """Convert any stored date format to ISO YYYY-MM-DD."""
    if not date_str:
        return None
    # Already ISO
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    # "June 9, 2026" or "June 9 2026"
    m = re.match(
        r'^(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{1,2}),?\s+(\d{4})$',
        date_str.strip(), re.IGNORECASE,
    )
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _run_reprocess_votes(job_id: int):
    """Re-run vote extraction on all imported agenda uploads."""
    db = SessionLocal()
    try:
        job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
        if not job:
            return
        _update_job(db, job, status="running")
        _append_log(db, job, "Re-processing vote data for all imported meetings...")

        # Get all meetings with minutes URLs from Legistar
        meetings = get_council_meetings(years=5)
        # Index by both ISO date ("2026-06-09") and human-readable ("June 9, 2026")
        minutes_by_date: dict[str, str] = {}
        for m in meetings:
            if not m.get("minutes_url"):
                continue
            iso_date = m["date"]  # "2026-06-09"
            minutes_by_date[iso_date] = m["minutes_url"]
            # Also index human-readable forms the PDF parser may produce
            try:
                from datetime import datetime as _dt
                dt = _dt.strptime(iso_date, "%Y-%m-%d")
                # "June 9, 2026" — lstrip removes leading zero on day
                human = f"{dt.strftime('%B')} {dt.day}, {dt.year}"
                minutes_by_date[human] = m["minutes_url"]
            except Exception:
                pass

        uploads = (
            db.query(AgendaUpload)
            .filter(AgendaUpload.document_type == "agenda")
            .order_by(AgendaUpload.meeting_date)
            .all()
        )
        _update_job(db, job, total_meetings=len(uploads))
        _append_log(db, job, f"Found {len(uploads)} agenda uploads to reprocess")

        _append_log(db, job, f"Minutes index has {len(minutes_by_date)} entries")

        processed = 0
        for upload in uploads:
            date = upload.meeting_date or ""
            # Try stored date as-is, then normalized to ISO
            minutes_url = minutes_by_date.get(date)
            if not minutes_url:
                iso = _normalize_date_to_iso(date)
                if iso:
                    minutes_url = minutes_by_date.get(iso)

            matched = 0
            if minutes_url:
                pdf_bytes = fetch_pdf_bytes_lenient(minutes_url)
                if not pdf_bytes:
                    _append_log(db, job, f"  {date}: could not download minutes PDF")
                    continue
                try:
                    raw_text = extract_text_from_pdf(pdf_bytes)
                    votes_by_ref = associate_votes_to_items(raw_text)
                    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload.id).all()
                    # Log first item's refs vs first vote key for debugging
                    if items and votes_by_ref:
                        sample_refs = _extract_item_refs(items[0])[:3]
                        sample_keys = list(votes_by_ref.keys())[:3]
                        _append_log(db, job, f"  {date}: {len(votes_by_ref)} vote refs, sample={sample_keys[:2]}, item refs={sample_refs[:2]}")
                    for item in items:
                        item_refs = _extract_item_refs(item)
                        for ref in item_refs:
                            if ref in votes_by_ref:
                                vote_result = votes_by_ref[ref]
                                item.votes = summarize_votes(vote_result)
                                if not item.districts and vote_result.get("districts"):
                                    item.districts = vote_result["districts"]
                                matched += 1
                                break
                    db.commit()
                    _append_log(db, job, f"  {date}: matched {matched}/{len(items)} votes")
                except Exception as e:
                    _append_log(db, job, f"  {date} minutes error: {e}")
            else:
                _append_log(db, job, f"  {date}: no minutes URL (stored date not in index)")
                matched = _process_youtube_votes(db, job, date, upload_id=upload.id, quiet=True)

            if matched:
                processed += 1
                job.processed_minutes = (job.processed_minutes or 0) + 1
                db.commit()

        _update_job(db, job, status="complete", completed_at=datetime.utcnow())
        _append_log(db, job, f"Reprocess complete — {processed}/{len(uploads)} meetings got vote data")
    except Exception as e:
        logger.exception(f"Reprocess job {job_id} failed")
        try:
            job = db.query(BulkImportJob).filter(BulkImportJob.id == job_id).first()
            if job:
                _update_job(db, job, status="error", completed_at=datetime.utcnow())
                _append_log(db, job, f"FATAL ERROR: {e}")
        except Exception:
            pass
    finally:
        db.close()


def _process_youtube_votes(
    db: Session,
    job: BulkImportJob,
    date: str,
    upload_id: int = None,
    quiet: bool = False,
) -> int:
    """
    Try to get vote data from YouTube for a meeting date.
    Returns number of items matched.
    """
    try:
        votes_by_ref = get_youtube_votes_for_date(date)
        if not votes_by_ref:
            return 0

        if not upload_id:
            upload = (
                db.query(AgendaUpload)
                .filter(
                    AgendaUpload.meeting_date == date,
                    AgendaUpload.document_type == "agenda",
                )
                .first()
            )
            if not upload:
                return 0
            upload_id = upload.id

        items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
        matched = 0
        for item in items:
            item_refs = _extract_item_refs(item)
            for ref in item_refs:
                if ref in votes_by_ref:
                    vote_result = votes_by_ref[ref]
                    item.votes = summarize_votes(vote_result)
                    if not item.districts and vote_result.get("districts"):
                        item.districts = vote_result["districts"]
                    matched += 1
                    break
        db.commit()
        if matched and not quiet:
            _append_log(db, job, f"  {date}: matched {matched} votes from YouTube")
        return matched
    except Exception as e:
        if not quiet:
            _append_log(db, job, f"  {date} YouTube vote error: {e}")
        return 0


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
            # Extract council districts from case ref inline annotations
            item_text = f"{item_data.get('item_number', '')} {item_data.get('title', '')} {item_data.get('description', '')}"
            item_districts = _extract_districts_from_text(item_text)
            db_item = AgendaItem(
                upload_id=upload.id,
                item_number=item_data.get("item_number"),
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                section=item_data.get("section", ""),
                category=cat,
                analysis=analysis,
                districts=item_districts or None,
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
                    vote_result = votes_by_ref[ref]
                    item.votes = summarize_votes(vote_result)
                    # Backfill districts from vote record if not already set
                    if not item.districts and vote_result.get("districts"):
                        item.districts = vote_result["districts"]
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
    """
    Extract all candidate case refs from an agenda item.
    Returns multiple key formats so we can match against whatever the vote
    parser generates from the minutes PDF.
    """
    import re
    text = f"{item.item_number or ''} {item.title or ''} {item.description or ''}"

    refs: list[str] = []
    seen: set[str] = set()

    def add(r: str):
        r = r.strip().upper()
        # Normalize whitespace
        r = re.sub(r'\s+', ' ', r)
        if r and r not in seen:
            seen.add(r)
            refs.append(r)

    # Explicit M&C + number: "M&C 26-0267"
    for m in re.finditer(r'\bM&?C\s+([A-Z]-\d{4,6}|\d{2}-\d{4,6})', text, re.IGNORECASE):
        add(f"M&C {m.group(1)}")

    # Zoning/site plan case numbers: ZC-25-078, SP-23-009
    for m in re.finditer(r'\b(ZC|SP|AX|FP|PP|RP|PD|CUP)-(\d{2})-(\d{3,6})', text, re.IGNORECASE):
        add(m.group(0))

    # Bare Legistar item IDs: 26-0267, 25-5257 — generate both bare and M&C forms
    for m in re.finditer(r'\b(\d{2})-(\d{4,6})\b', text):
        bare = f"{m.group(1)}-{m.group(2)}"
        add(bare)
        add(f"M&C {bare}")          # minutes may key it as "M&C 26-0267"
        add(f"M&C  {bare}")         # double-space from PDF extraction artifact

    return refs


def _extract_districts_from_text(text: str) -> list[str]:
    """
    Pull all (CD X) and (ALL) district annotations from a text string.
    Returns a deduplicated list like ["2", "9"] or ["ALL"].
    """
    import re
    cd_re = re.compile(
        r'\((?:Future\s+)?(?:(ALL)|(CD\s*\d+(?:\s+and\s+CD\s*\d+)*))\)',
        re.IGNORECASE,
    )
    districts: list[str] = []
    seen: set[str] = set()
    for m in cd_re.finditer(text):
        if m.group(1):
            if "ALL" not in seen:
                districts.append("ALL")
                seen.add("ALL")
        elif m.group(2):
            nums = re.findall(r'\d+', m.group(2))
            for n in nums:
                if n not in seen:
                    districts.append(n)
                    seen.add(n)
    return districts


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
