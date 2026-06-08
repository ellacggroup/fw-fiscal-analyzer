"""
Tarrant Appraisal District (TAD) parcel lookup.
Queries the public TAD property search API for current assessed value,
owner name, and land/improvement values by address.
"""
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# TAD uses an iswdata backend — these endpoints are discovered from browser XHR
_TAD_SEARCH_URL = "https://iswdataentry.iswdev.com/api/v1/Property/QuickSearch"
_TAD_DETAIL_URL = "https://iswdataentry.iswdev.com/api/v1/Property/Detail"
_TAD_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.tad.org",
    "Referer": "https://www.tad.org/",
    "User-Agent": "Mozilla/5.0 (compatible; FWFiscalAnalyzer/1.0)",
}
_TIMEOUT = 12.0


def lookup_by_address(address: str) -> dict:
    """
    Search TAD for a property by address.
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

    # Try TAD API first
    result = _query_tad_api(clean)
    if result:
        return result

    # Fallback: Tarrant County GIS parcel layer (ESRI REST)
    result = _query_tarrant_gis(clean)
    if result:
        return result

    return {"status": "not_found", "attempted_address": clean}


def _clean_address(address: str) -> str:
    """Strip city/state/zip suffix — TAD searches on street address only."""
    addr = re.sub(r",?\s*(fort worth|FW|TX|Texas).*$", "", address, flags=re.IGNORECASE).strip()
    addr = re.sub(r"\s+", " ", addr)
    return addr


def _query_tad_api(address: str) -> Optional[dict]:
    """Hit TAD's iswdata QuickSearch endpoint."""
    try:
        payload = {
            "searchType": "Address",
            "searchValue": address,
            "taxYear": 0,
            "countyCode": "220",  # Tarrant County FIPS
        }
        resp = httpx.post(
            _TAD_SEARCH_URL,
            json=payload,
            headers=_TAD_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.debug("TAD API returned %s for address %s", resp.status_code, address)
            return None

        data = resp.json()
        results = data.get("results") or data.get("Properties") or []
        if not results:
            return None

        prop = results[0]
        return {
            "status": "found",
            "source": "tad_api",
            "account_number": str(prop.get("accountNumber") or prop.get("AccountNumber") or ""),
            "owner_name": _clean_name(prop.get("ownerName") or prop.get("OwnerName") or ""),
            "site_address": prop.get("siteAddress") or prop.get("SiteAddress") or address,
            "assessed_value": _to_int(prop.get("assessedValue") or prop.get("TotalAppraisedValue")),
            "land_value": _to_int(prop.get("landValue") or prop.get("LandValue")),
            "improvement_value": _to_int(prop.get("improvementValue") or prop.get("ImprovementValue")),
            "tax_year": prop.get("taxYear") or prop.get("TaxYear"),
        }
    except Exception as exc:
        logger.debug("TAD API query failed for %s: %s", address, exc)
        return None


def _query_tarrant_gis(address: str) -> Optional[dict]:
    """
    Fallback: Tarrant County GIS REST service — parcel layer with owner/value data.
    """
    try:
        url = (
            "https://gis.tarrantcountytx.gov/arcgis/rest/services/GIS_Data/Parcels/MapServer/0/query"
        )
        params = {
            "where": f"UPPER(SITUS_ADD) LIKE UPPER('%{address.split()[0]}%{address.split()[-1] if len(address.split()) > 1 else ''}%')",
            "outFields": "ACCOUNT_NUM,OWNER_NAME,SITUS_ADD,TOTAL_APPR,LAND_VALUE,IMPR_VALUE,TAX_YEAR",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 1,
        }
        resp = httpx.get(url, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None
        attrs = features[0].get("attributes", {})
        return {
            "status": "found",
            "source": "tarrant_gis",
            "account_number": str(attrs.get("ACCOUNT_NUM") or ""),
            "owner_name": _clean_name(attrs.get("OWNER_NAME") or ""),
            "site_address": attrs.get("SITUS_ADD") or address,
            "assessed_value": _to_int(attrs.get("TOTAL_APPR")),
            "land_value": _to_int(attrs.get("LAND_VALUE")),
            "improvement_value": _to_int(attrs.get("IMPR_VALUE")),
            "tax_year": attrs.get("TAX_YEAR"),
        }
    except Exception as exc:
        logger.debug("Tarrant GIS parcel query failed for %s: %s", address, exc)
        return None


def _to_int(val) -> Optional[int]:
    try:
        return int(float(val)) if val is not None else None
    except (TypeError, ValueError):
        return None


def _clean_name(name: str) -> str:
    return " ".join(name.strip().split())
