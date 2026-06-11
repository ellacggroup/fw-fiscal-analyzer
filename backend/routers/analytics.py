"""Historical tracking / analytics endpoints."""
import json
import re
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, get_db
from services.vote_parser import _normalize_name

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


@router.get("/zoning-transitions")
def get_zoning_transitions(db: Session = Depends(get_db)):
    """
    Aggregate zoning change transitions — how many cases went from each
    zone type to each other zone type, with total acreage and meeting dates.
    Returns a list sorted by frequency.
    """
    items = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.category == "Zoning Change")
        .all()
    )

    # Map zone codes to broad land use categories for grouping
    _ZONE_CATEGORY = {
        # Single-family residential
        "A-5": "Single-Family Residential", "A-10": "Single-Family Residential",
        "A-21": "Single-Family Residential", "A-43": "Single-Family Residential",
        "AR":   "Agricultural Residential",  "GR":   "Single-Family Residential",
        # Agricultural / open
        "AG":  "Agricultural",  "AN": "Agricultural",  "O-1": "Open Space / Floodplain",
        # Multifamily
        "B": "Two-Family Residential", "C": "Low-Rise Multifamily",
        "D": "High-Density Multifamily", "D-HR": "High-Density Multifamily",
        "UR": "Urban Residential", "R1": "Cluster Residential",
        # Commercial
        "E":  "Neighborhood Commercial",  "ER": "Neighborhood Commercial Restricted",
        "F":  "General Commercial",       "FR": "General Commercial Restricted",
        "G":  "Intensive Commercial",     "H":  "Central Business District",
        "NS": "Neighborhood Service",
        # Industrial
        "I": "Light Industrial", "J": "Medium Industrial", "K": "Heavy Industrial",
        # Institutional / mixed
        "CF": "Community Facilities",
        "MU-1": "Mixed-Use", "MU-2": "Mixed-Use", "MU": "Mixed-Use",
    }

    def _categorize(code: str) -> str:
        if not code:
            return "Unknown"
        clean = code.strip().upper().split("/")[0]
        if clean in _ZONE_CATEGORY:
            return _ZONE_CATEGORY[clean]
        if clean.startswith("PD"):
            return "Planned Development"
        if clean.startswith("TL-"):
            return "Trinity Lakes District"
        if clean.startswith("SY-"):
            return "Stockyards District"
        return clean

    transitions: dict[str, dict] = {}

    for item, upload in items:
        analysis = item.analysis or {}
        from_code = analysis.get("zoning_from_code") or ""
        to_code   = analysis.get("zoning_to_code")   or ""
        to_code2  = analysis.get("zoning_to_code2")  or ""
        acreage   = analysis.get("acreage_estimate")  or 0
        date      = upload.meeting_date or ""

        if not from_code or not to_code:
            continue

        # Primary transition
        for tc in filter(None, [to_code, to_code2 or None]):
            from_cat = _categorize(from_code)
            to_cat   = _categorize(tc)
            key      = f"{from_code} → {tc}"
            cat_key  = f"{from_cat} → {to_cat}"

            if key not in transitions:
                transitions[key] = {
                    "from_code":     from_code,
                    "to_code":       tc,
                    "from_category": from_cat,
                    "to_category":   to_cat,
                    "category_key":  cat_key,
                    "count":         0,
                    "total_acres":   0.0,
                    "meetings":      set(),
                    "districts":     set(),
                }
            transitions[key]["count"]       += 1
            transitions[key]["total_acres"] += acreage or 0
            if date:
                transitions[key]["meetings"].add(date)
            district = _extract_district(item.title or "", item.description or "")
            if district:
                transitions[key]["districts"].add(district)

    results = []
    for t in transitions.values():
        results.append({
            "from_code":     t["from_code"],
            "to_code":       t["to_code"],
            "from_category": t["from_category"],
            "to_category":   t["to_category"],
            "category_key":  t["category_key"],
            "count":         t["count"],
            "total_acres":   round(t["total_acres"], 2),
            "meeting_dates": sorted(t["meetings"]),
            "districts":     sorted(t["districts"], key=lambda x: int(x) if x.isdigit() else 99),
        })

    results.sort(key=lambda x: -x["count"])
    return {"total_transitions": len(results), "transitions": results}


@router.get("/land-use-trends")
def get_land_use_trends(db: Session = Depends(get_db)):
    """
    Aggregate zoning changes by broad land use category transition over time.
    Shows how many acres moved from one use type to another per meeting date.
    """
    items = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.category == "Zoning Change")
        .all()
    )

    _BROAD = {
        "Single-Family Residential": "Residential",
        "Agricultural Residential":  "Residential",
        "Two-Family Residential":    "Residential",
        "Low-Rise Multifamily":      "Residential",
        "High-Density Multifamily":  "Residential",
        "Urban Residential":         "Residential",
        "Cluster Residential":       "Residential",
        "Neighborhood Commercial":   "Commercial",
        "Neighborhood Commercial Restricted": "Commercial",
        "General Commercial":        "Commercial",
        "General Commercial Restricted": "Commercial",
        "Intensive Commercial":      "Commercial",
        "Central Business District": "Commercial",
        "Neighborhood Service":      "Commercial",
        "Mixed-Use":                 "Mixed-Use",
        "Trinity Lakes District":    "Mixed-Use",
        "Stockyards District":       "Mixed-Use",
        "Light Industrial":          "Industrial",
        "Medium Industrial":         "Industrial",
        "Heavy Industrial":          "Industrial",
        "Planned Development":       "Planned Development",
        "Community Facilities":      "Institutional / CF",
        "Agricultural":              "Agricultural / Open",
        "Agricultural / Natural":    "Agricultural / Open",
        "Open Space / Floodplain":   "Agricultural / Open",
        "Unknown":                   "Other",
    }

    _ZONE_CATEGORY = {
        "A-5": "Residential", "A-10": "Residential", "A-21": "Residential",
        "A-43": "Residential", "AR": "Residential", "GR": "Residential",
        "AG": "Agricultural / Open", "AN": "Agricultural / Open", "O-1": "Agricultural / Open",
        "B": "Residential", "C": "Residential", "D": "Residential",
        "D-HR": "Residential", "UR": "Residential", "R1": "Residential",
        "E": "Commercial", "ER": "Commercial", "F": "Commercial",
        "FR": "Commercial", "G": "Commercial", "H": "Commercial", "NS": "Commercial",
        "I": "Industrial", "J": "Industrial", "K": "Industrial",
        "CF": "Institutional / CF",
        "MU-1": "Mixed-Use", "MU-2": "Mixed-Use", "MU": "Mixed-Use",
    }

    def _broad(code: str) -> str:
        if not code:
            return "Other"
        clean = code.strip().upper().split("/")[0]
        if clean in _ZONE_CATEGORY:
            return _ZONE_CATEGORY[clean]
        if clean.startswith("PD"):
            return "Planned Development"
        return "Other"

    by_date: dict[str, dict] = {}

    for item, upload in items:
        analysis = item.analysis or {}
        from_code = analysis.get("zoning_from_code") or ""
        to_code   = analysis.get("zoning_to_code")   or ""
        acreage   = analysis.get("acreage_estimate")  or 0
        date      = upload.meeting_date or "Unknown"

        if not from_code or not to_code or not acreage:
            continue

        from_broad = _broad(from_code)
        to_broad   = _broad(to_code)
        key        = f"{from_broad} → {to_broad}"

        if date not in by_date:
            by_date[date] = {}
        by_date[date][key] = by_date[date].get(key, 0) + acreage

    # Build sorted output
    all_keys = sorted({k for d in by_date.values() for k in d})
    dates = sorted(by_date.keys())

    rows = []
    for date in dates:
        row = {"meeting_date": date}
        for k in all_keys:
            row[k] = round(by_date[date].get(k, 0), 2)
        rows.append(row)

    return {"dates": dates, "transition_types": all_keys, "by_date": rows}


# All categories that affect real estate / real estate development
_TREND_CATEGORIES = {
    "Zoning Change",
    "Site Plan / Plat",
    "Platting",
    "Land Use / Comp Plan",
    "Economic Incentive",
    "Development Agreement",
    "TIRZ / Tax Increment",
    "Public Improvement District",
    "Impact / Development Fees",
    "Annexation",
    "Right-of-Way / Easement",
    "Land Acquisition / Disposition",
    "Utility Extension / Infrastructure",
    "Development Code / Standards",
}


@router.get("/category-trends")
def get_category_trends(db: Session = Depends(get_db)):
    """
    Return item counts per relevant category per calendar quarter
    for the past 5 years. Used for the Trends view.
    """
    rows = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.category.in_(_TREND_CATEGORIES))
        .all()
    )

    # Group by quarter + category
    by_quarter: dict[str, dict[str, int]] = {}
    for item, upload in rows:
        date = upload.meeting_date or ""
        if not date:
            continue
        # Parse date to quarter string like "2023-Q2"
        try:
            parts = date.replace(",", "").split()
            if len(parts) == 3:
                # "January 16, 2024" or already numeric
                from datetime import datetime as dt
                d = dt.strptime(date.replace(",", ""), "%B %d %Y")
            else:
                d = dt.fromisoformat(date[:10])
            quarter = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
        except Exception:
            quarter = date[:7]  # fallback: YYYY-MM

        cat = item.category or "Other"
        if quarter not in by_quarter:
            by_quarter[quarter] = {}
        by_quarter[quarter][cat] = by_quarter[quarter].get(cat, 0) + 1

    quarters_sorted = sorted(by_quarter.keys())
    all_cats = sorted(_TREND_CATEGORIES)

    rows_out = []
    for q in quarters_sorted:
        row = {"quarter": q}
        for cat in all_cats:
            row[cat] = by_quarter[q].get(cat, 0)
        row["total"] = sum(by_quarter[q].values())
        rows_out.append(row)

    return {
        "quarters": quarters_sorted,
        "categories": all_cats,
        "by_quarter": rows_out,
    }


@router.get("/votes-by-member")
def get_votes_by_member(
    category: str = "",
    db: Session = Depends(get_db),
):
    """
    Aggregate vote records by councilmember across all stored items.
    Optionally filter by category.
    Returns vote totals per member.
    """
    query = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.votes.isnot(None))
    )
    if category:
        query = query.filter(AgendaItem.category == category)
    rows = query.all()

    # Aggregate: {name+district → {AYE, NAY, ABSTAIN, ABSENT, items}}
    member_stats: dict[str, dict] = {}

    for item, upload in rows:
        votes_data = item.votes or {}
        by_member = votes_data.get("by_member") or []
        for vote_rec in by_member:
            raw_name = vote_rec.get("name", "Unknown")
            name = _normalize_name(raw_name) if raw_name != "Unknown" else raw_name
            district = vote_rec.get("district", "")
            vote_type = vote_rec.get("vote", "")
            key = f"{name}|{district}"

            if key not in member_stats:
                member_stats[key] = {
                    "name": name,
                    "district": district,
                    "AYE": 0,
                    "NAY": 0,
                    "ABSTAIN": 0,
                    "ABSENT": 0,
                    "items": 0,
                }
            member_stats[key][vote_type] = member_stats[key].get(vote_type, 0) + 1
            member_stats[key]["items"] += 1

    results = sorted(
        member_stats.values(),
        key=lambda x: (
            int(x["district"]) if x["district"].isdigit() else 0,
            x["name"],
        ),
    )

    return {"total_items_with_votes": len(rows), "members": results}


@router.get("/member-vote-items")
def get_member_vote_items(
    name: str,
    vote: str = "",
    category: str = "",
    db: Session = Depends(get_db),
):
    """
    Return the specific agenda items a council member voted a given way on.
    name: canonical member name (e.g. "Elizabeth Beck")
    vote: AYE | NAY | ABSTAIN | ABSENT — omit to return all vote types
    category: optional category filter
    """
    query = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(AgendaItem.votes.isnot(None))
    )
    if category:
        query = query.filter(AgendaItem.category == category)
    rows = query.all()

    name_lower = name.strip().lower()
    vote_filter = vote.strip().upper() if vote.strip() else None
    results = []

    for item, upload in rows:
        votes_data = item.votes or {}
        by_member = votes_data.get("by_member") or []
        for vote_rec in by_member:
            raw_name = vote_rec.get("name", "Unknown")
            canonical = _normalize_name(raw_name) if raw_name != "Unknown" else raw_name
            if canonical.lower() != name_lower:
                continue
            actual_vote = vote_rec.get("vote", "").upper()
            if vote_filter and actual_vote != vote_filter:
                continue
            analysis = item.analysis or {}
            results.append({
                "item_id":       item.id,
                "upload_id":     item.upload_id,
                "meeting_date":  upload.meeting_date,
                "item_number":   item.item_number,
                "title":         item.title or "",
                "category":      item.category or "",
                "vote":          actual_vote,
                "fiscal_rating": analysis.get("fiscal_impact_rating"),
                "summary":       (item.description or "")[:180] or (item.title or "")[:180],
            })
            break  # one vote per item per member

    results.sort(key=lambda x: (x["category"], x["meeting_date"] or ""), reverse=False)
    return {"member": name, "vote": vote_filter or "ALL", "total": len(results), "items": results}


@router.get("/votes-timeline")
def get_votes_timeline(db: Session = Depends(get_db)):
    """
    Return vote outcomes (passed/failed) over time for relevant categories.
    """
    rows = (
        db.query(AgendaItem, AgendaUpload)
        .join(AgendaUpload, AgendaItem.upload_id == AgendaUpload.id)
        .filter(
            AgendaItem.category.in_(_TREND_CATEGORIES),
            AgendaItem.votes.isnot(None),
        )
        .all()
    )

    by_date: dict[str, dict] = {}
    for item, upload in rows:
        date = upload.meeting_date or "Unknown"
        votes = item.votes or {}
        passed = votes.get("passed", None)

        if date not in by_date:
            by_date[date] = {"meeting_date": date, "passed": 0, "failed": 0, "total": 0}
        if passed is True:
            by_date[date]["passed"] += 1
        elif passed is False:
            by_date[date]["failed"] += 1
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
