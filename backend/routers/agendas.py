from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import AgendaItem, AgendaUpload, get_db
from services.claude_analyzer import analyze_items_with_claude, claude_available
from services.fiscal_analyzer import analyze_fiscal_impact
from services.pdf_parser import detect_meeting_date, extract_agenda_items, extract_text_from_pdf
from services.url_fetcher import fetch_pdf_from_url

router = APIRouter(prefix="/agendas", tags=["agendas"])


# ---------------------------------------------------------------------------
# Upload from file
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50 MB).")

    return await _process_pdf(file_bytes, file.filename, db)


# ---------------------------------------------------------------------------
# Upload from URL
# ---------------------------------------------------------------------------

@router.post("/upload-url")
async def upload_from_url(
    payload: dict = Body(..., example={"url": "https://fortworthtexas.gov/.../agenda.pdf"}),
    db: Session = Depends(get_db),
):
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="'url' field is required.")

    pdf_bytes, filename = fetch_pdf_from_url(url)
    return await _process_pdf(pdf_bytes, filename, db, source_url=url)


# ---------------------------------------------------------------------------
# Shared processing logic
# ---------------------------------------------------------------------------

async def _process_pdf(
    file_bytes: bytes,
    filename: str,
    db: Session,
    source_url: str = None,
) -> dict:
    raw_text = extract_text_from_pdf(file_bytes)
    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract text from PDF. "
                "Is it a scanned image? Please use a text-based PDF."
            ),
        )

    meeting_date = detect_meeting_date(raw_text)
    raw_items = extract_agenda_items(raw_text)

    if not raw_items:
        raise HTTPException(
            status_code=422,
            detail=(
                "No agenda items could be identified in this PDF. "
                "The parser works best with text-based PDFs that use numbered items."
            ),
        )

    # Rule-based analysis (instant, always available)
    rule_analyses = [analyze_fiscal_impact(item) for item in raw_items]

    # Claude analysis (optional; batched)
    claude_analyses = analyze_items_with_claude(raw_items, meeting_date)
    using_claude = claude_available()

    # Merge: Claude overrides fiscal_impact_rating; everything else is additive
    merged_analyses = []
    for rule, claude in zip(rule_analyses, claude_analyses):
        merged = dict(rule)
        merged["claude_summary"] = claude["summary"]
        merged["risk_level"] = claude["risk_level"]
        merged["is_recurring"] = claude["is_recurring"]
        merged["one_time_vs_recurring_note"] = claude["one_time_vs_recurring_note"]
        merged["key_concerns"] = claude["key_concerns"]
        merged["claude_available"] = using_claude
        # Claude rating takes precedence when available and not unknown
        if using_claude and claude["fiscal_impact_rating"] != "UNKNOWN":
            merged["fiscal_impact_rating"] = claude["fiscal_impact_rating"]
        merged_analyses.append(merged)

    # Persist
    upload = AgendaUpload(
        filename=filename,
        meeting_date=meeting_date,
        raw_text=raw_text[:100_000],
        item_count=len(raw_items),
        source_url=source_url,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)

    saved_items = []
    for item_data, analysis in zip(raw_items, merged_analyses):
        db_item = AgendaItem(
            upload_id=upload.id,
            item_number=item_data.get("item_number"),
            title=item_data.get("title", ""),
            description=item_data.get("description", ""),
            section=item_data.get("section", ""),
            category=_infer_category_label(analysis, item_data.get("section", "")),
            analysis=analysis,
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        saved_items.append(db_item)

    return {
        "upload_id": upload.id,
        "filename": filename,
        "meeting_date": meeting_date,
        "source_url": source_url,
        "claude_enabled": using_claude,
        "item_count": len(saved_items),
        "items": [_serialize(i) for i in saved_items],
    }


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/{upload_id}")
def get_agenda(upload_id: int, db: Session = Depends(get_db)):
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    return {
        "upload_id": upload_id,
        "filename": upload.filename,
        "meeting_date": upload.meeting_date,
        "source_url": upload.source_url,
        "uploaded_at": upload.uploaded_at.isoformat(),
        "item_count": len(items),
        "items": [_serialize(i) for i in items],
    }


@router.get("/")
def list_agendas(db: Session = Depends(get_db)):
    uploads = db.query(AgendaUpload).order_by(AgendaUpload.uploaded_at.desc()).all()
    return [
        {
            "upload_id": u.id,
            "filename": u.filename,
            "meeting_date": u.meeting_date,
            "source_url": u.source_url,
            "uploaded_at": u.uploaded_at.isoformat(),
            "item_count": u.item_count,
        }
        for u in uploads
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(item: AgendaItem) -> dict:
    return {
        "id": item.id,
        "item_number": item.item_number,
        "title": item.title,
        "description": item.description,
        "section": item.section or "",
        "category": item.category,
        "analysis": item.analysis,
    }


def _infer_category_label(analysis: dict, section: str = "") -> str:
    # Use the category the fiscal analyzer already computed from title + description
    cat = analysis.get("category", "")
    if cat and cat != "Other":
        return cat

    # Section-header overrides for Fort Worth agenda structure
    sec = section.upper()
    if "ZONING" in sec:
        return "Zoning Change"
    if "PUBLIC HEARING" in sec:
        return "Public Hearing"
    if "ORDINANCE" in sec:
        return "Policy / Ordinance"
    if "RESOLUTION" in sec:
        return "Policy / Ordinance"
    if "LAND" in sec:
        return "Land / Real Estate"
    if "PURCHASE" in sec or "EQUIPMENT" in sec or "MATERIALS" in sec:
        return "Contract / Procurement"
    if "AWARD" in sec:
        return "Contract / Procurement"
    if "PERSONNEL" in sec:
        return "Personnel"

    return cat or "Other"
