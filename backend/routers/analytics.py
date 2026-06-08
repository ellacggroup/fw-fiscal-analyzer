"""Historical tracking / analytics endpoints."""
import json
import re
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _extract_district(title: str, description: str) -> str | None:
    combined = f"{title or ''} {description or ''}"
    m = re.search(r'\bCD\s*(\d+)\b|\bDistrict\s+(\d+)\b|\bCouncil\s+District\s+(\d+)\b',
                  combined, re.IGNORECASE)
    if m:
        return m.group(1) or m.group(2) or m.group(3)
    return None


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """High-level counts across all uploaded agendas."""
    uploads = db.query(AgendaUpload).all()
    items = db.query(AgendaItem).all()

    by_category = {}
    by_rating = {}
    by_district = {}

    for item in items:
        cat = item.category or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1

        rating = (item.analysis or {}).get("fiscal_impact_rating") or "UNKNOWN"
        by_rating[rating] = by_rating.get(rating, 0) + 1

        district = _extract_district(item.title or "", item.description or "")
        if district:
            by_district[district] = by_district.get(district, 0) + 1

    dates = sorted(
        [u.meeting_date for u in uploads if u.meeting_date],
        key=lambda d: d or ""
    )

    return {
        "total_uploads":  len(uploads),
        "total_items":    len(items),
        "date_range":     {"earliest": dates[0] if dates else None,
                           "latest":   dates[-1] if dates else None},
        "by_category":    dict(sorted(by_category.items(), key=lambda x: -x[1])),
        "by_rating":      by_rating,
        "by_district":    dict(sorted(by_district.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 99)),
    }


@router.get("/zoning-activity")
def get_zoning_activity(
    district: str = "",
    land_use_type: str = "",
    db: Session = Depends(get_db),
):
    """Zoning change items across all agendas, optionally filtered."""
    items = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.category == "Zoning Change")
        .all()
    )

    results = []
    for item, upload in items:
        analysis = item.analysis or {}
        item_district = _extract_district(item.title or "", item.description or "")
        item_lu = analysis.get("land_use_type") or ""

        if district and item_district != district:
            continue
        if land_use_type and land_use_type.lower() not in item_lu.lower():
            continue

        results.append({
            "item_id":            item.id,
            "upload_id":          item.upload_id,
            "meeting_date":       upload.meeting_date,
            "item_number":        item.item_number,
            "title":              item.title[:120] if item.title else "",
            "district":           item_district,
            "land_use_type":      item_lu,
            "zoning_from":        analysis.get("zoning_from_code"),
            "zoning_to":          analysis.get("zoning_to_code"),
            "acreage":            analysis.get("acreage_estimate"),
            "fiscal_impact_rating": analysis.get("fiscal_impact_rating"),
            "comp_plan_status":   analysis.get("comp_plan_lookup_status"),
            "consistent":         analysis.get("consistent_with_comp_plan"),
        })

    # Sort by meeting date descending
    results.sort(key=lambda x: x["meeting_date"] or "", reverse=True)
    return {"total": len(results), "items": results}


@router.get("/timeline")
def get_timeline(db: Session = Depends(get_db)):
    """Items by meeting date grouped by fiscal rating — for timeline chart."""
    rows = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .all()
    )

    by_date: dict[str, dict] = {}
    for item, upload in rows:
        date = upload.meeting_date or "Unknown"
        if date not in by_date:
            by_date[date] = {"meeting_date": date, "upload_id": upload.id,
                             "POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0, "UNKNOWN": 0, "total": 0}
        rating = (item.analysis or {}).get("fiscal_impact_rating") or "UNKNOWN"
        by_date[date][rating] = by_date[date].get(rating, 0) + 1
        by_date[date]["total"] += 1

    return sorted(by_date.values(), key=lambda x: x["meeting_date"] or "")


@router.get("/economic-incentives")
def get_incentive_history(db: Session = Depends(get_db)):
    """All economic incentive deals across all agendas."""
    items = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.category == "Economic Incentive")
        .all()
    )
    results = []
    for item, upload in items:
        analysis = item.analysis or {}
        results.append({
            "item_id":        item.id,
            "upload_id":      item.upload_id,
            "meeting_date":   upload.meeting_date,
            "title":          item.title[:120] if item.title else "",
            "incentive_type": analysis.get("economic_incentive_type"),
            "term_years":     analysis.get("incentive_term_years"),
            "min_foregone":   analysis.get("year1_net_impact"),
            "total_cap":      analysis.get("projection_40yr_net"),
            "mc_investment":  analysis.get("mc_investment"),
            "mc_enriched":    analysis.get("mc_enriched", False),
            "rating":         analysis.get("fiscal_impact_rating"),
        })
    results.sort(key=lambda x: x["meeting_date"] or "", reverse=True)
    return {"total": len(results), "items": results}
