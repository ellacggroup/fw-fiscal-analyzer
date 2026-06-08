from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from database import AgendaItem, AgendaUpload, get_db
from services.claude_analyzer import analyze_items_with_claude, claude_available
from services.fiscal_analyzer import analyze_fiscal_impact
from services.pdf_parser import detect_meeting_date, extract_agenda_items, extract_text_from_pdf
from services.url_fetcher import fetch_pdf_from_url
from services.comprehensive_plan import lookup_comprehensive_plan, is_real_estate_item
from services.zoning_gis_lookup import extract_case_numbers, lookup_zoning_case
from services.alert_matcher import run_alert_matching
from services.proximity_matcher import run_proximity_matching

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
    display_name = _make_display_name(meeting_date, filename)

    # Deduplication: if an agenda with this meeting date already exists, remove it
    if meeting_date:
        existing = db.query(AgendaUpload).filter(AgendaUpload.meeting_date == meeting_date).first()
        if existing:
            db.query(AgendaItem).filter(AgendaItem.upload_id == existing.id).delete()
            db.delete(existing)
            db.commit()

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

    # Claude analysis (optional; batched) — pass rule analyses for context
    claude_analyses = analyze_items_with_claude(raw_items, meeting_date, rule_analyses)
    using_claude = claude_available()

    # Merge: Claude adds qualitative narrative; rule engine owns ratings for
    # items where it has authoritative data (annexation hearings, parsed zoning,
    # site plans with broader development).
    merged_analyses = []
    for rule, claude in zip(rule_analyses, claude_analyses):
        merged = dict(rule)
        merged["claude_summary"] = claude["summary"]
        merged["risk_level"] = claude["risk_level"]
        merged["is_recurring"] = claude["is_recurring"]
        merged["one_time_vs_recurring_note"] = claude["one_time_vs_recurring_note"]
        merged["key_concerns"] = claude["key_concerns"]
        merged["claude_available"] = using_claude

        if using_claude and claude["fiscal_impact_rating"] != "UNKNOWN":
            merged["fiscal_impact_rating"] = claude["fiscal_impact_rating"]

        # Guard 1: procedural annexation hearings are always NEUTRAL —
        # never let Claude mark a hearing as NEGATIVE or POSITIVE.
        if rule.get("annexation_hearing"):
            merged["fiscal_impact_rating"] = "NEUTRAL"

        # Guard 2: when the rule engine parsed the zoning FROM/TO codes,
        # trust its R/C-based rating over Claude's batch estimate.
        if rule.get("zoning_request_parsed") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
            merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]

        # Guard 3: site plan / plat approvals — the rule engine rates these
        # based on broader development potential; don't let Claude downgrade.
        if rule.get("site_plan_type") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL"):
            if claude.get("fiscal_impact_rating") == "NEGATIVE":
                merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]

        merged_analyses.append(merged)

    # GIS enrichment: comp plan + zoning case lookup for real estate / zoning items
    for i, (item_data, merged) in enumerate(zip(raw_items, merged_analyses)):
        cat = _infer_category_label(merged, item_data.get("section", ""))
        if is_real_estate_item(cat, item_data.get("title", ""), item_data.get("description", "")):
            _enrich_with_gis(merged, item_data, cat)

    # Persist
    upload = AgendaUpload(
        filename=display_name,
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

    # Post-save hooks: alert matching and proximity matching
    try:
        run_alert_matching(upload.id, db)
    except Exception:
        pass
    try:
        run_proximity_matching(upload.id, db)
    except Exception:
        pass

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

@router.post("/reanalyze-all")
async def reanalyze_all_agendas(db: Session = Depends(get_db)):
    """Re-run analysis on every stored upload. Deduplicates by meeting date and fixes filenames."""
    uploads = db.query(AgendaUpload).order_by(AgendaUpload.id).all()

    # Deduplicate: for each meeting_date keep only the most recent upload_id
    seen_dates: dict = {}
    for u in uploads:
        if u.meeting_date:
            if u.meeting_date in seen_dates:
                # Remove the older one
                older_id = seen_dates[u.meeting_date]
                db.query(AgendaItem).filter(AgendaItem.upload_id == older_id).delete()
                db.query(AgendaUpload).filter(AgendaUpload.id == older_id).delete()
                db.commit()
            seen_dates[u.meeting_date] = u.id

    # Refresh list after deduplication
    uploads = db.query(AgendaUpload).order_by(AgendaUpload.id).all()

    results = []
    for upload in uploads:
        if not upload.raw_text:
            results.append({"upload_id": upload.id, "status": "skipped — no raw text"})
            continue
        try:
            raw_items = extract_agenda_items(upload.raw_text)
            rule_analyses   = [analyze_fiscal_impact(item) for item in raw_items]
            claude_analyses = analyze_items_with_claude(raw_items, upload.meeting_date, rule_analyses)
            using_claude    = claude_available()

            db.query(AgendaItem).filter(AgendaItem.upload_id == upload.id).delete()
            db.commit()

            count = 0
            for item_data, rule, claude in zip(raw_items, rule_analyses, claude_analyses):
                merged = dict(rule)
                merged["claude_summary"]             = claude["summary"]
                merged["risk_level"]                 = claude["risk_level"]
                merged["is_recurring"]               = claude["is_recurring"]
                merged["one_time_vs_recurring_note"] = claude["one_time_vs_recurring_note"]
                merged["key_concerns"]               = claude["key_concerns"]
                merged["claude_available"]           = using_claude
                if using_claude and claude["fiscal_impact_rating"] != "UNKNOWN":
                    merged["fiscal_impact_rating"]   = claude["fiscal_impact_rating"]
                if rule.get("annexation_hearing"):
                    merged["fiscal_impact_rating"] = "NEUTRAL"
                if rule.get("zoning_request_parsed") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
                    merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]
                if rule.get("site_plan_type") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL"):
                    if claude.get("fiscal_impact_rating") == "NEGATIVE":
                        merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]

                cat = _infer_category_label(merged, item_data.get("section", ""))
                if is_real_estate_item(cat, item_data.get("title", ""), item_data.get("description", "")):
                    _enrich_with_gis(merged, item_data, cat)

                db_item = AgendaItem(
                    upload_id=upload.id,
                    item_number=item_data.get("item_number"),
                    title=item_data.get("title", ""),
                    description=item_data.get("description", ""),
                    section=item_data.get("section", ""),
                    category=cat,
                    analysis=merged,
                )
                db.add(db_item)
                count += 1

            db.commit()
            upload.item_count = count
            # Fix filename to use meeting date as display name
            upload.filename = _make_display_name(upload.meeting_date, upload.filename)
            db.commit()
            results.append({"upload_id": upload.id, "status": "ok", "items": count, "name": upload.filename})

        except Exception as exc:
            results.append({"upload_id": upload.id, "status": "error", "detail": str(exc)})

    return {"processed": len(results), "results": results}


@router.post("/{upload_id}/reanalyze")
async def reanalyze_agenda(upload_id: int, db: Session = Depends(get_db)):
    """
    Re-run fiscal analysis on a stored upload using the current analysis engine.
    Deletes old items and replaces them with fresh results.
    Useful when the analysis logic has been updated.
    """
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not upload.raw_text:
        raise HTTPException(
            status_code=400,
            detail="No raw text stored for this upload. Please re-upload the PDF.",
        )

    raw_items = extract_agenda_items(upload.raw_text)
    if not raw_items:
        raise HTTPException(status_code=422, detail="Could not re-parse agenda items from stored text.")

    rule_analyses   = [analyze_fiscal_impact(item) for item in raw_items]
    claude_analyses = analyze_items_with_claude(raw_items, upload.meeting_date, rule_analyses)
    using_claude    = claude_available()

    # Replace old items
    db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).delete()
    db.commit()

    saved_items = []
    for item_data, rule, claude in zip(raw_items, rule_analyses, claude_analyses):
        merged = dict(rule)
        merged["claude_summary"]            = claude["summary"]
        merged["risk_level"]                = claude["risk_level"]
        merged["is_recurring"]              = claude["is_recurring"]
        merged["one_time_vs_recurring_note"]= claude["one_time_vs_recurring_note"]
        merged["key_concerns"]              = claude["key_concerns"]
        merged["claude_available"]          = using_claude
        if using_claude and claude["fiscal_impact_rating"] != "UNKNOWN":
            merged["fiscal_impact_rating"]  = claude["fiscal_impact_rating"]
        if rule.get("annexation_hearing"):
            merged["fiscal_impact_rating"] = "NEUTRAL"
        if rule.get("zoning_request_parsed") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL", "NEGATIVE"):
            merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]
        if rule.get("site_plan_type") and rule.get("fiscal_impact_rating") in ("POSITIVE", "NEUTRAL"):
            if claude.get("fiscal_impact_rating") == "NEGATIVE":
                merged["fiscal_impact_rating"] = rule["fiscal_impact_rating"]

        cat = _infer_category_label(merged, item_data.get("section", ""))
        if is_real_estate_item(cat, item_data.get("title", ""), item_data.get("description", "")):
            _enrich_with_gis(merged, item_data, cat)

        db_item = AgendaItem(
            upload_id=upload_id,
            item_number=item_data.get("item_number"),
            title=item_data.get("title", ""),
            description=item_data.get("description", ""),
            section=item_data.get("section", ""),
            category=cat,
            analysis=merged,
        )
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        saved_items.append(db_item)

    upload.item_count = len(saved_items)
    db.commit()

    return {
        "upload_id":    upload_id,
        "filename":     upload.filename,
        "meeting_date": upload.meeting_date,
        "item_count":   len(saved_items),
        "items":        [_serialize(i) for i in saved_items],
    }


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


def _enrich_with_gis(merged: dict, item_data: dict, cat: str) -> None:
    """
    Run comp-plan + zoning-case GIS lookups and merge results into *merged*.
    When the zoning regex failed to parse From/To codes, GIS data fills them in.
    """
    item_text = f"{item_data.get('title', '')} {item_data.get('description', '')}"

    # Skip comp plan lookup for text amendments — no parcel, no address
    if merged.get("text_amendment"):
        return

    # Comp plan lookup (also calls zoning GIS internally)
    cp = lookup_comprehensive_plan(item_text, category=cat)
    merged.update(cp)

    # If zoning_request_parsed is False, try to fill From/To from Zoning Cases GIS
    if not merged.get("zoning_request_parsed"):
        for case_num in extract_case_numbers(item_text):
            gis = lookup_zoning_case(case_num)
            if not gis:
                continue
            if gis.get("zoning_from") or gis.get("zoning_to"):
                merged["zoning_from_code"]           = gis["zoning_from"]
                merged["zoning_to_code"]             = gis["zoning_to"]
                merged["zoning_from_label"]          = gis["zoning_from"]
                merged["zoning_to_label"]            = gis["zoning_to"]
                merged["zoning_from_desc"]           = ""
                merged["zoning_to_desc"]             = gis["zoning_to"]
                merged["zoning_request_parsed"]      = True
                merged["zoning_gis_source"]          = True
                merged["zoning_case_number"]         = gis["case_number"]
                merged["zoning_applicant"]           = gis.get("applicant", "")
                merged["zoning_action"]              = gis.get("action", "")
                merged["consistent_with_comp_plan"]  = gis.get("consistent_with_comp_plan", "")
                if gis.get("acres") and not merged.get("acreage_estimate"):
                    merged["acreage_estimate"] = gis["acres"]
                if gis.get("address") and not merged.get("comp_plan_address"):
                    merged["comp_plan_address"] = gis["address"]
                break


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


def _make_display_name(meeting_date: str | None, fallback: str) -> str:
    """Return a human-readable agenda name based on the meeting date."""
    if meeting_date:
        return f"City Council Meeting – {meeting_date}"
    # Strip raw filename extension as a last resort
    import os
    return os.path.splitext(fallback)[0] if fallback else "Agenda"
