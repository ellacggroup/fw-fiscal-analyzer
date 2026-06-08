"""
Alert matching service.
Runs after each agenda upload to check new items against saved WatchAlerts.
"""
import re
import logging
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, WatchAlert, AlertMatch

logger = logging.getLogger(__name__)


def run_alert_matching(upload_id: int, db: Session) -> int:
    """
    Check all items in upload_id against all active WatchAlerts.
    Creates AlertMatch records for any hits.
    Returns the number of matches created.
    """
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        return 0

    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    alerts = db.query(WatchAlert).filter(WatchAlert.is_active == True).all()

    if not items or not alerts:
        return 0

    matches_created = 0
    for alert in alerts:
        for item in items:
            reason = _check_match(alert, item)
            if reason:
                # Avoid duplicate matches for the same alert + item
                existing = db.query(AlertMatch).filter(
                    AlertMatch.alert_id == alert.id,
                    AlertMatch.agenda_item_id == item.id,
                ).first()
                if not existing:
                    match = AlertMatch(
                        alert_id=alert.id,
                        agenda_item_id=item.id,
                        upload_id=upload_id,
                        meeting_date=upload.meeting_date,
                        item_title=item.title[:200] if item.title else "",
                        match_reason=reason,
                    )
                    db.add(match)
                    matches_created += 1

    if matches_created:
        db.commit()

    return matches_created


def _check_match(alert: WatchAlert, item: AgendaItem) -> str | None:
    """
    Returns a reason string if the item matches the alert, or None if no match.
    """
    text = f"{item.title or ''} {item.description or ''}".lower()
    criteria = alert.criteria.strip().lower()

    if alert.alert_type == "district":
        # Match "CD 5", "District 5", "(CD5)", "(CD 5)"
        district_num = re.sub(r"[^\d]", "", criteria)
        if district_num:
            patterns = [
                rf'\bcd\s*{district_num}\b',
                rf'\bdistrict\s+{district_num}\b',
                rf'\bcouncil\s+district\s+{district_num}\b',
            ]
            for pat in patterns:
                if re.search(pat, text, re.IGNORECASE):
                    return f"Council District {district_num} match"

    elif alert.alert_type == "address":
        # Case-insensitive substring match on address
        if criteria in text:
            return f"Address match: '{alert.criteria}'"
        # Also check comp_plan_address in analysis
        analysis = item.analysis or {}
        comp_addr = (analysis.get("comp_plan_address") or "").lower()
        if criteria in comp_addr:
            return f"Address match in GIS data: '{alert.criteria}'"

    elif alert.alert_type == "category":
        item_cat = (item.category or "").lower()
        if criteria in item_cat:
            return f"Category match: '{alert.criteria}'"

    return None
