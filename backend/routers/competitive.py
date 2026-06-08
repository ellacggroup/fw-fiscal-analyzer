"""Competitive intelligence endpoints — watched properties and proximity alerts."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import AgendaItem, ProximityAlert, WatchedProperty, get_db
from services.geocoder import geocode_address

router = APIRouter(prefix="/competitive", tags=["competitive"])


class PropertyCreate(BaseModel):
    label: str
    address: str
    radius_miles: float = 1.0


@router.get("/properties")
def list_properties(db: Session = Depends(get_db)):
    props = db.query(WatchedProperty).order_by(WatchedProperty.created_at.desc()).all()
    return [_ser_prop(p) for p in props]


@router.post("/properties")
def add_property(body: PropertyCreate, db: Session = Depends(get_db)):
    coords = geocode_address(body.address)
    prop = WatchedProperty(
        label=body.label,
        address=body.address,
        radius_miles=body.radius_miles,
        lat=coords[0] if coords else None,
        lng=coords[1] if coords else None,
        geocoded_at=datetime.utcnow() if coords else None,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return _ser_prop(prop)


@router.delete("/properties/{prop_id}")
def delete_property(prop_id: int, db: Session = Depends(get_db)):
    prop = db.query(WatchedProperty).filter(WatchedProperty.id == prop_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    db.query(ProximityAlert).filter(ProximityAlert.watched_property_id == prop_id).delete()
    db.delete(prop)
    db.commit()
    return {"deleted": prop_id}


@router.get("/alerts")
def list_proximity_alerts(unread_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(ProximityAlert)
    if unread_only:
        q = q.filter(ProximityAlert.is_read == False)
    alerts = q.order_by(ProximityAlert.matched_at.desc()).limit(200).all()
    result = []
    for a in alerts:
        prop = db.query(WatchedProperty).filter(WatchedProperty.id == a.watched_property_id).first()
        result.append({
            "alert_id":         a.id,
            "property_id":      a.watched_property_id,
            "property_label":   prop.label if prop else "",
            "property_address": prop.address if prop else "",
            "radius_miles":     prop.radius_miles if prop else None,
            "upload_id":        a.upload_id,
            "item_id":          a.agenda_item_id,
            "meeting_date":     a.meeting_date,
            "item_title":       a.item_title,
            "distance_miles":   a.distance_miles,
            "deal_type":        a.deal_type,
            "matched_at":       a.matched_at.isoformat() if a.matched_at else None,
            "is_read":          a.is_read,
        })
    return result


@router.get("/alerts/unread-count")
def unread_count(db: Session = Depends(get_db)):
    count = db.query(ProximityAlert).filter(ProximityAlert.is_read == False).count()
    return {"unread": count}


@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: int, db: Session = Depends(get_db)):
    a = db.query(ProximityAlert).filter(ProximityAlert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    a.is_read = True
    db.commit()
    return {"alert_id": alert_id, "is_read": True}


def _ser_prop(p: WatchedProperty) -> dict:
    return {
        "id":            p.id,
        "label":         p.label,
        "address":       p.address,
        "radius_miles":  p.radius_miles,
        "geocoded":      p.lat is not None,
        "lat":           p.lat,
        "lng":           p.lng,
        "created_at":    p.created_at.isoformat() if p.created_at else None,
    }
