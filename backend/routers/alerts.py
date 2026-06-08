"""Alert system endpoints — watch criteria and match retrieval."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import AgendaItem, AlertMatch, WatchAlert, get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    label: str
    alert_type: str   # "district" | "address" | "category"
    criteria: str


@router.get("/")
def list_alerts(db: Session = Depends(get_db)):
    alerts = db.query(WatchAlert).order_by(WatchAlert.created_at.desc()).all()
    return [_ser_alert(a) for a in alerts]


@router.post("/")
def create_alert(body: AlertCreate, db: Session = Depends(get_db)):
    if body.alert_type not in ("district", "address", "category"):
        raise HTTPException(status_code=400, detail="alert_type must be district, address, or category")
    alert = WatchAlert(label=body.label, alert_type=body.alert_type, criteria=body.criteria)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return _ser_alert(alert)


@router.delete("/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(WatchAlert).filter(WatchAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.query(AlertMatch).filter(AlertMatch.alert_id == alert_id).delete()
    db.delete(alert)
    db.commit()
    return {"deleted": alert_id}


@router.get("/matches/unread-count")
def unread_count(db: Session = Depends(get_db)):
    count = db.query(AlertMatch).filter(AlertMatch.is_read == False).count()
    return {"unread": count}


@router.get("/matches")
def list_matches(unread_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(AlertMatch)
    if unread_only:
        q = q.filter(AlertMatch.is_read == False)
    matches = q.order_by(AlertMatch.matched_at.desc()).limit(200).all()
    result = []
    for m in matches:
        alert = db.query(WatchAlert).filter(WatchAlert.id == m.alert_id).first()
        result.append({
            "match_id":     m.id,
            "alert_id":     m.alert_id,
            "alert_label":  alert.label if alert else "",
            "alert_type":   alert.alert_type if alert else "",
            "criteria":     alert.criteria if alert else "",
            "upload_id":    m.upload_id,
            "item_id":      m.agenda_item_id,
            "meeting_date": m.meeting_date,
            "item_title":   m.item_title,
            "match_reason": m.match_reason,
            "matched_at":   m.matched_at.isoformat() if m.matched_at else None,
            "is_read":      m.is_read,
        })
    return result


@router.post("/matches/{match_id}/read")
def mark_read(match_id: int, db: Session = Depends(get_db)):
    match = db.query(AlertMatch).filter(AlertMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match.is_read = True
    db.commit()
    return {"match_id": match_id, "is_read": True}


@router.post("/matches/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(AlertMatch).filter(AlertMatch.is_read == False).update({"is_read": True})
    db.commit()
    return {"marked_read": True}


def _ser_alert(a: WatchAlert) -> dict:
    return {
        "id":          a.id,
        "label":       a.label,
        "alert_type":  a.alert_type,
        "criteria":    a.criteria,
        "is_active":   a.is_active,
        "created_at":  a.created_at.isoformat() if a.created_at else None,
    }
