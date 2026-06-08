"""Parcel lookup endpoints — TAD assessed value and ownership."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, ParcelLookup, get_db
from services.tad_lookup import lookup_by_address

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.post("/agenda/{upload_id}")
def lookup_parcels_for_agenda(upload_id: int, db: Session = Depends(get_db)):
    """Trigger TAD lookup for all zoning/real estate items in an agenda."""
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Agenda not found")

    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    results = []
    for item in items:
        analysis = item.analysis or {}
        cat = item.category or ""
        if cat not in ("Zoning Change", "Annexation", "Development Agreement", "Site Plan / Plat"):
            continue
        address = analysis.get("comp_plan_address") or ""
        if not address:
            continue

        # Check if already looked up
        existing = db.query(ParcelLookup).filter(
            ParcelLookup.agenda_item_id == item.id
        ).first()
        if existing:
            results.append(_serialize_parcel(existing, item.id))
            continue

        data = lookup_by_address(address)
        parcel = ParcelLookup(
            agenda_item_id=item.id,
            upload_id=upload_id,
            address=address,
            account_number=data.get("account_number"),
            owner_name=data.get("owner_name"),
            site_address=data.get("site_address"),
            assessed_value=data.get("assessed_value"),
            land_value=data.get("land_value"),
            improvement_value=data.get("improvement_value"),
            tax_year=data.get("tax_year"),
            source=data.get("source"),
            status=data.get("status", "error"),
        )
        db.add(parcel)
        db.commit()
        db.refresh(parcel)
        results.append(_serialize_parcel(parcel, item.id))

    return {"upload_id": upload_id, "parcels": results}


@router.post("/item/{item_id}")
def lookup_parcel_for_item(item_id: int, db: Session = Depends(get_db)):
    """On-demand TAD lookup for a single agenda item."""
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    analysis = item.analysis or {}
    address = analysis.get("comp_plan_address") or ""
    if not address:
        raise HTTPException(status_code=422, detail="No address available for this item")

    # Delete stale lookup if it exists
    db.query(ParcelLookup).filter(ParcelLookup.agenda_item_id == item_id).delete()

    data = lookup_by_address(address)
    parcel = ParcelLookup(
        agenda_item_id=item.id,
        upload_id=item.upload_id,
        address=address,
        account_number=data.get("account_number"),
        owner_name=data.get("owner_name"),
        site_address=data.get("site_address"),
        assessed_value=data.get("assessed_value"),
        land_value=data.get("land_value"),
        improvement_value=data.get("improvement_value"),
        tax_year=data.get("tax_year"),
        source=data.get("source"),
        status=data.get("status", "error"),
    )
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return _serialize_parcel(parcel, item_id)


@router.get("/agenda/{upload_id}")
def get_parcels_for_agenda(upload_id: int, db: Session = Depends(get_db)):
    """Return stored parcel data for all items in an agenda."""
    parcels = db.query(ParcelLookup).filter(ParcelLookup.upload_id == upload_id).all()
    return {"upload_id": upload_id, "parcels": [_serialize_parcel(p, p.agenda_item_id) for p in parcels]}


@router.get("/item/{item_id}")
def get_parcel_for_item(item_id: int, db: Session = Depends(get_db)):
    parcel = db.query(ParcelLookup).filter(ParcelLookup.agenda_item_id == item_id).first()
    if not parcel:
        return {"status": "not_looked_up"}
    return _serialize_parcel(parcel, item_id)


def _serialize_parcel(p: ParcelLookup, item_id: int) -> dict:
    return {
        "item_id":          item_id,
        "status":           p.status,
        "address":          p.address,
        "account_number":   p.account_number,
        "owner_name":       p.owner_name,
        "site_address":     p.site_address,
        "assessed_value":   p.assessed_value,
        "land_value":       p.land_value,
        "improvement_value":p.improvement_value,
        "tax_year":         p.tax_year,
        "source":           p.source,
        "looked_up_at":     p.looked_up_at.isoformat() if p.looked_up_at else None,
    }
