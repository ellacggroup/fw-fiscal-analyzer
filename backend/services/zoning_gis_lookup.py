"""
Fort Worth Zoning Cases GIS lookup.

Queries the Fort Worth MapServer zoning case layers by ZC case number
to get authoritative From/To zoning codes, address, acreage, and the
Future Land Use (comp plan) designation — no PDF text parsing needed.

Layers queried (in order):
  Layer 3   — Zoning Cases Current (pending + recently approved)
  Layer 196 — Zoning Cases 2025
  Layer 195 — Zoning Cases 2024
  Layer 91  — Zoning Cases 2023
"""

import re
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ZONING_MAPSERVER = (
    "https://mapit.fortworthtexas.gov/ags/rest/services"
    "/Planning_Development/Zoning/MapServer"
)

# Layers to try, in order (most recent first)
CASE_LAYERS = [3, 196, 195, 91, 85, 68]

FIELDS = "CASE_NMBR,ZONING_FRO,ZONING_TO,ADDRESS,ACRES,FUTURE_LAN,ACTION_,APPLT_NAME,CONSISTENC"

# Regex to find ZC / SUP / BOA case numbers in agenda text
_CASE_RE = re.compile(
    r'\b(ZC|SUP|BOA)[-\s](\d{2})[-\s](\d{3,4}[A-Z]?)\b',
    re.IGNORECASE,
)


def extract_case_numbers(text: str) -> list[str]:
    """Return normalised case numbers found in text, e.g. ['ZC-26-015', 'ZC-26-022']."""
    results = []
    seen = set()
    for m in _CASE_RE.finditer(text):
        case = f"{m.group(1).upper()}-{m.group(2)}-{m.group(3).upper()}"
        if case not in seen:
            seen.add(case)
            results.append(case)
    return results


def _query_layer(layer_id: int, case_number: str) -> Optional[dict]:
    """Query a single MapServer layer for *case_number*. Returns raw attributes or None."""
    url = f"{ZONING_MAPSERVER}/{layer_id}/query"
    # Escape single quotes in case number for SQL
    safe = case_number.replace("'", "''")
    params = {
        "where": f"CASE_NMBR='{safe}'",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = httpx.get(url, params=params, timeout=10)
        r.raise_for_status()
        features = r.json().get("features", [])
        if features:
            return features[0].get("attributes", {})
    except Exception as exc:
        logger.warning("Zoning GIS layer %s query failed for %s: %s", layer_id, case_number, exc)
    return None


def lookup_zoning_case(case_number: str) -> Optional[dict]:
    """
    Look up a ZC case across all known layers.
    Returns a normalised dict or None if not found.

    Keys returned:
      case_number, zoning_from, zoning_to, address, acres,
      future_land_use_code, applicant, action
    """
    for layer_id in CASE_LAYERS:
        attrs = _query_layer(layer_id, case_number)
        if attrs:
            consistenc = (attrs.get("CONSISTENC") or "").strip()
            return {
                "case_number":              case_number,
                "zoning_from":              (attrs.get("ZONING_FRO") or "").strip(),
                "zoning_to":                (attrs.get("ZONING_TO") or "").strip(),
                "address":                  (attrs.get("ADDRESS") or "").strip(),
                "acres":                    attrs.get("ACRES"),
                "future_land_use_code":     (attrs.get("FUTURE_LAN") or "").strip().upper(),
                "applicant":                (attrs.get("APPLT_NAME") or "").strip(),
                "action":                   (attrs.get("ACTION_") or "").strip(),
                "consistent_with_comp_plan": consistenc,  # "Yes" | "No" | ""
            }
    return None


def lookup_all_cases(text: str) -> list[dict]:
    """
    Find all ZC/SUP case numbers in *text* and return GIS data for each.
    Skips case numbers that return no GIS record.
    """
    results = []
    for case_number in extract_case_numbers(text):
        data = lookup_zoning_case(case_number)
        if data:
            results.append(data)
    return results
