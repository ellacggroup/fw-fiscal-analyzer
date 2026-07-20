"""
Tarrant Appraisal District (TAD) parcel lookup.
Queries Tarrant County's official ArcGIS REST parcel-data service for
current assessed value, owner name, and land/improvement values by address.

Note: this previously pointed at two endpoints (a reverse-engineered TAD
"iswdata" API and a guessed gis.tarrantcountytx.gov hostname) that turned
out not to resolve on the network at all — not slow, not down, just wrong.
Replaced with Tarrant County's own published ArcGIS service, confirmed
working against real Fort Worth addresses:
https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcelsApp/MapServer
Table 1 ("PARCELDATA") carries owner/valuation fields; layer 0 is parcel
geometry only and isn't used here.
"""
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PARCEL_DATA_URL = (
    "https://mapit.tarrantcounty.com/arcgis/rest/services/Dynamic/TADParcelsApp/MapServer/1/query"
)
_TIMEOUT = 12.0


def lookup_by_address(address: str) -> dict:
    """
    Search Tarrant County's parcel data for a property by address.
    Returns a dict with status and parcel data, or error details.

    Result keys (when found):
      status, account_number, owner_name, site_address,
      assessed_value, land_value, improvement_value, tax_year
    """
    if not address or not address.strip():
        return {"status": "no_address"}

    clean = _clean_address(address)
    if not clean:
        return {"status": "no_address"}

    result = _query_tarrant_county_parceldata(clean)
    if result:
        return result

    return {"status": "not_found", "attempted_address": clean}


def _clean_address(address: str) -> str:
    """Strip city/state/zip suffix — search on street address only."""
    addr = re.sub(r",?\s*(fort worth|FW|TX|Texas).*$", "", address, flags=re.IGNORECASE).strip()
    addr = re.sub(r"\s+", " ", addr)
    return addr


def _query_tarrant_county_parceldata(address: str) -> Optional[dict]:
    """
    Hit Tarrant County's TADParcelsApp PARCELDATA table. Matches on the
    leading house number plus the street name, deliberately excluding the
    trailing street-type word (Avenue/Street/Boulevard/...) — the county
    data stores these abbreviated ("AVE", "ST", "BLVD"), and a title's
    spelled-out form ("Avenue") won't substring-match "AVE", so requiring
    it would silently miss real matches like "3113 Wayside Avenue" vs. the
    stored "3113 WAYSIDE AVE".
    """
    try:
        words = address.split()
        if not words:
            return None
        house_number = words[0]
        if not house_number.isdigit():
            return None  # not a street address (e.g. an intersection description)
        # Drop the trailing street-type word if there's at least one other
        # street-name word to match on (so "1200 Main St" -> "1200"/"Main").
        street_words = words[1:-1] if len(words) > 2 else words[1:]
        # Escape single quotes for the ArcGIS SQL-style WHERE clause
        esc = lambda s: s.replace("'", "''")
        street_pattern = "%".join(esc(w) for w in street_words)
        # No leading "%" before the house number — it must anchor the start
        # of the field (a directional like "N"/"W" can follow), otherwise
        # "801" would substring-match "5801", "1801", etc.
        where = f"UPPER(Situs_Address) LIKE UPPER('{esc(house_number)} %{street_pattern}%')"

        resp = httpx.get(
            _PARCEL_DATA_URL,
            params={
                "where": where,
                "outFields": "Account_Num,Owner_Name,Situs_Address,Land_Value,Improvement_Value,Total_Value,Appraisal_Year",
                "returnGeometry": "false",
                "f": "json",
                "resultRecordCount": 5,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.debug("Tarrant County parcel query returned %s for %s", resp.status_code, address)
            return None

        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None

        # Multiple matches can occur (legacy/split-account records for the
        # same address); take the first — matches the same "best guess"
        # behavior as every other GIS lookup in this app.
        attrs = features[0].get("attributes", {})
        return {
            "status": "found",
            "source": "tarrant_county_parceldata",
            "account_number": str(attrs.get("Account_Num") or ""),
            "owner_name": _clean_name(attrs.get("Owner_Name") or ""),
            "site_address": attrs.get("Situs_Address") or address,
            "assessed_value": _to_int(attrs.get("Total_Value")),
            "land_value": _to_int(attrs.get("Land_Value")),
            "improvement_value": _to_int(attrs.get("Improvement_Value")),
            "tax_year": attrs.get("Appraisal_Year"),
        }
    except Exception as exc:
        logger.debug("Tarrant County parcel query failed for %s: %s", address, exc)
        return None


def _to_int(val) -> Optional[int]:
    try:
        return int(float(val)) if val is not None else None
    except (TypeError, ValueError):
        return None


def _clean_name(name: str) -> str:
    return " ".join(name.strip().split())
