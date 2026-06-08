"""Staff report upload endpoints — enriches economic incentive analysis from M&C PDFs."""
import re
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from database import AgendaItem, AgendaUpload, get_db
from services.pdf_parser import extract_text_from_pdf
from services.mc_parser import parse_mc_report
from services.fiscal_analyzer import analyze_fiscal_impact

router = APIRouter(prefix="/staff-reports", tags=["staff-reports"])


@router.post("/agenda/{upload_id}")
async def upload_staff_report(
    upload_id: int,
    file: UploadFile = File(...),
    item_number: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """
    Upload an M&C staff report PDF for an agenda.
    Parses deal terms and re-enriches matching agenda items.
    """
    upload = db.query(AgendaUpload).filter(AgendaUpload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Agenda not found")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    file_bytes = await file.read()
    text = extract_text_from_pdf(file_bytes)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    mc_data = parse_mc_report(text)
    mc_number = mc_data.get("mc_number")

    # Find matching items — by item_number param, or by M&C ref in item title/description
    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    matched = []

    for item in items:
        hit = False
        if item_number and item.item_number == item_number:
            hit = True
        elif mc_number and (mc_number in (item.title or "") or mc_number in (item.description or "")):
            hit = True
        elif mc_number:
            # Try matching just the number part e.g. "25-0582"
            num_only = mc_number.replace("M&C ", "").replace("M&C", "").strip()
            if num_only and (num_only in (item.title or "") or num_only in (item.description or "")):
                hit = True

        if hit:
            matched.append(item)

    if not matched:
        return {
            "upload_id": upload_id,
            "mc_number": mc_number,
            "matched_items": 0,
            "mc_data": mc_data,
            "message": "No matching agenda items found for this M&C number. "
                       "The extracted data is shown below but was not applied.",
        }

    # Merge M&C data into each matched item's analysis
    updated = []
    for item in matched:
        analysis = dict(item.analysis or {})
        analysis.update(mc_data)

        # Re-run fiscal analysis with enriched data if it's an economic incentive
        if analysis.get("category") == "Economic Incentive" or item.category == "Economic Incentive":
            investment = mc_data.get("mc_investment")
            abate_pct = mc_data.get("mc_abatement_pct")
            rebate_cap = mc_data.get("mc_rebate_cap")
            rebate_pct = mc_data.get("mc_rebate_pct")
            term = mc_data.get("mc_term_years")

            if investment and rebate_cap and rebate_pct and term:
                # Compute actual min foregone from staff report data
                fw_tax_rate = 0.7125 / 100
                full_tax = round(investment * fw_tax_rate)
                year1_forgone = round(full_tax * (rebate_pct / 100) * -1)
                analysis["year1_revenue_estimate"] = full_tax
                analysis["year1_net_impact"] = year1_forgone
                analysis["year1_cost_estimate"] = abs(year1_forgone)
                analysis["projection_40yr_net"] = round(year1_forgone * term)
                analysis["incentive_term_years"] = term
                analysis["confidence"] = "HIGH"
                analysis["mc_data_source"] = "staff_report"

        item.analysis = analysis
        db.commit()
        updated.append({
            "item_id": item.id,
            "item_number": item.item_number,
            "title": item.title[:100] if item.title else "",
            "mc_data_applied": list(mc_data.keys()),
        })

    return {
        "upload_id": upload_id,
        "mc_number": mc_number,
        "matched_items": len(updated),
        "items": updated,
        "mc_data": mc_data,
    }


@router.get("/agenda/{upload_id}")
def get_enriched_items(upload_id: int, db: Session = Depends(get_db)):
    """Return all items that have M&C staff report data applied."""
    items = db.query(AgendaItem).filter(AgendaItem.upload_id == upload_id).all()
    enriched = [
        {
            "item_id": i.id,
            "item_number": i.item_number,
            "title": i.title[:100] if i.title else "",
            "mc_number": (i.analysis or {}).get("mc_number"),
            "mc_summary": (i.analysis or {}).get("mc_summary"),
            "mc_investment": (i.analysis or {}).get("mc_investment"),
        }
        for i in items
        if (i.analysis or {}).get("mc_enriched")
    ]
    return {"upload_id": upload_id, "enriched_items": enriched}
