"""
Proximity / competitive intelligence matcher.
After each agenda upload, checks economic incentive and major zoning items
against user-saved watched properties, flagging deals within the radius.
"""
import logging
import re
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, WatchedProperty, ProximityAlert
from services.geocoder import geocode_address, haversine_miles

logger = logging.getLogger(__name__)

_INCENTIVE_CATEGORIES = {"Economic Incentive", "Development Agreement"}
_MAJOR_ZONING_ACRES = 5.0   # flag zoning changes >= this acreage


def run_proximity_matching(upload_id: int, db: Session) -> int:
    """
    Geocode relevant new items and check them against WatchedProperty records.
    Returns number of ProximityAlert records created.
    """
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        return 0

    properties = db.query(WatchedProperty).all()
    if not properties:
        return 0

    # Only check items that are economic incentives or large zoning changes
    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    candidates = []
    for item in items:
        analysis = item.analysis or {}
        cat = item.category or ""
        if cat in _INCENTIVE_CATEGORIES:
            candidates.append(item)
        elif cat == "Zoning Change":
            acres = analysis.get("acreage_estimate") or 0
            if (acres or 0) >= _MAJOR_ZONING_ACRES:
                candidates.append(item)

    if not candidates:
        return 0

    # Ensure watched properties are geocoded
    for prop in properties:
        if prop.lat is None or prop.lng is None:
            coords = geocode_address(prop.address)
            if coords:
                prop.lat, prop.lng = coords
                from datetime import datetime
                prop.geocoded_at = datetime.utcnow()
    db.commit()

    matches_created = 0
    for item in candidates:
        analysis = item.analysis or {}
        item_address = (
            analysis.get("comp_plan_address")
            or _extract_address_from_title(item.title or "")
        )
        if not item_address:
            continue

        item_coords = geocode_address(item_address)
        if not item_coords:
            continue

        item_lat, item_lng = item_coords

        for prop in properties:
            if prop.lat is None or prop.lng is None:
                continue

            dist = haversine_miles(prop.lat, prop.lng, item_lat, item_lng)
            if dist <= prop.radius_miles:
                # Avoid duplicate
                existing = db.query(ProximityAlert).filter(
                    ProximityAlert.watched_property_id == prop.id,
                    ProximityAlert.agenda_item_id == item.id,
                ).first()
                if not existing:
                    deal_type = (
                        analysis.get("economic_incentive_type")
                        or item.category
                        or "Unknown"
                    )
                    alert = ProximityAlert(
                        watched_property_id=prop.id,
                        agenda_item_id=item.id,
                        upload_id=upload_id,
                        meeting_date=upload.meeting_date,
                        item_title=item.title[:200] if item.title else "",
                        distance_miles=round(dist, 2),
                        deal_type=deal_type,
                    )
                    db.add(alert)
                    matches_created += 1

    if matches_created:
        db.commit()

    return matches_created


def _extract_address_from_title(title: str) -> str | None:
    """Pull a street address from a ZC item title as a fallback."""
    m = re.search(r'\d+\s+[A-Za-z][A-Za-z0-9\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Trail|Pkwy|Highway|Hwy)\b', title, re.IGNORECASE)
    if m:
        return m.group(0).strip() + ", Fort Worth, TX"
    return None
