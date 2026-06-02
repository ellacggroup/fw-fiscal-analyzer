"""
Fort Worth Comprehensive Plan – Future Land Use lookup.

Given a free-text agenda item description, this module:
  1. Extracts a street address using regex heuristics.
  2. Geocodes the address via the ArcGIS World Geocoder (no key required).
  3. Queries the FW Future Land Use MapServer layer to get the comp-plan
     designation for that parcel.

Returns a dict that is safe to merge into an AgendaItem's analysis blob.
"""

import re
import logging
import urllib.parse
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ArcGIS endpoints
# ---------------------------------------------------------------------------

GEOCODE_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer"
    "/findAddressCandidates"
)

FUTURE_LAND_USE_URL = (
    "https://mapit.fortworthtexas.gov/ags/rest/services"
    "/Planning_Development/Report_Flu_Published/MapServer/identify"
)

# Spatial reference: 4326 (WGS-84) for geocoder output; the MapServer
# identify endpoint accepts geographic SR so we can pass 4326 directly.
OUT_SR = 4326

# ---------------------------------------------------------------------------
# Comprehensive plan LU code → human label mapping
# ---------------------------------------------------------------------------

LU_LABELS: dict[str, str] = {
    "SF":    "Single-Family Residential",
    "SUB":   "Suburban Residential",
    "RURAL": "Rural Residential",
    "LDR":   "Low-Density Residential",
    "MDR":   "Medium-Density Residential",
    "HDR":   "High-Density Residential",
    "UR":    "Urban Residential",
    "MH":    "Manufactured Housing",
    "NC":    "Neighborhood Commercial",
    "GC":    "General Commercial",
    "MU":    "Mixed-Use",
    "MUGC":  "Mixed-Use Growth Center",
    "LI":    "Light Industrial",
    "HI":    "Heavy Industrial",
    "IGC":   "Industrial Growth Center",
    "INST":  "Institutional",
    "INFRA": "Infrastructure",
    "PUBPK": "Existing Public Parkland",
    "PRIPK": "Open Space / Private Parkland",
    "AG":    "Agricultural (Vacant)",
    "WATER": "Lakes and Ponds",
}

# Descriptions used in the UI tooltip
LU_DESCRIPTIONS: dict[str, str] = {
    "SF":    "Detached single-family homes, typically 2–4 units/acre.",
    "SUB":   "Suburban residential areas on larger lots.",
    "RURAL": "Very low-density residential, rural character.",
    "LDR":   "Low-density residential including duplexes and small-scale attached homes.",
    "MDR":   "Medium-density residential — townhomes, small apartments, ~8–20 units/acre.",
    "HDR":   "High-density residential — mid/high-rise apartments.",
    "UR":    "Urban residential — mixed housing types in walkable areas.",
    "MH":    "Manufactured housing / mobile home parks.",
    "NC":    "Small-scale retail and services serving nearby neighborhoods.",
    "GC":    "Full range of retail, office, and service commercial uses.",
    "MU":    "Vertical or horizontal mix of residential, retail, and office.",
    "MUGC":  "Intensive mixed-use development at identified growth centers.",
    "LI":    "Light manufacturing, warehousing, flex-industrial.",
    "HI":    "Heavy manufacturing, freight, and industrial processing.",
    "IGC":   "Large-scale industrial development at designated growth centers.",
    "INST":  "Schools, hospitals, government facilities, places of worship.",
    "INFRA": "Utilities, transportation infrastructure, public works.",
    "PUBPK": "Existing publicly-owned parks and recreation areas.",
    "PRIPK": "Private open space, greenways, nature preserves.",
    "AG":    "Agricultural land and vacant/undeveloped parcels.",
    "WATER": "Lakes, ponds, and major water bodies.",
}

# ---------------------------------------------------------------------------
# Categories / keywords that warrant a comp-plan lookup
# ---------------------------------------------------------------------------

REAL_ESTATE_CATEGORIES = {
    "Zoning Change",
    "Land / Real Estate",
    "Public Hearing",
    "Annexation",
}

REAL_ESTATE_KEYWORDS = re.compile(
    r"\b(zon|annex|plat|subdivis|site plan|replat|rezoning|development|"
    r"land use|real estate|property|parcel|acreage|lot|deed|"
    r"convey|acqui|easement|right.of.way|ROW|PD\s*\d|ZC\s*\d|SP\s*\d)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Address extraction
# ---------------------------------------------------------------------------

# Matches patterns like:
#   "123 Main St", "4500 N. Hulen Street", "8200 Camp Bowie West Blvd",
#   "located at 100 E. Weatherford", "property at 3001 W Loop 820"
_ADDR_RE = re.compile(
    r"(?:(?:located|situated|property|address|site)\s+at\s+)?"
    r"(?<!\d)(?<!-)(?P<number>\d{3,6})\s+"
    r"(?P<street>"
    r"(?:[NSEW]\.?\s+)?"
    r"[A-Z][A-Za-z0-9\.\s\-]+?"
    r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|"
    r"Lane|Ln|Court|Ct|Place|Pl|Way|Trail|Trl|Pkwy|Parkway|"
    r"Loop|Freeway|Fwy|Highway|Hwy|Circle|Cir|Terrace|Ter|"
    r"Row|Run|Path|Pass|Pike|Point|Pt|Bend|Crossing|Cove|"
    r"Commons|Landing|Ridge|Creek|North|South|East|West)"
    r"(?:\s+(?:North|South|East|West|NE|NW|SE|SW|Suite|Ste|#\s*\d+))?)",
    re.IGNORECASE,
)


def extract_address(text: str) -> Optional[str]:
    """Return the first plausible Fort Worth street address found in text."""
    m = _ADDR_RE.search(text)
    if not m:
        return None
    addr = f"{m.group('number')} {m.group('street').strip()}, Fort Worth, TX"
    # Clean up multiple spaces
    return re.sub(r"\s{2,}", " ", addr)


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(address: str) -> Optional[tuple[float, float]]:
    """Return (longitude, latitude) for *address* or None on failure."""
    params = {
        "SingleLine": address,
        "outFields": "Match_addr,Score",
        "maxLocations": "1",
        "f": "json",
        "outSR": str(OUT_SR),
        "countryCode": "USA",
    }
    try:
        r = httpx.get(GEOCODE_URL, params=params, timeout=8)
        r.raise_for_status()
        candidates = r.json().get("candidates", [])
        if not candidates or candidates[0].get("score", 0) < 70:
            return None
        loc = candidates[0]["location"]
        return loc["x"], loc["y"]
    except Exception as exc:
        logger.warning("Geocode failed for %r: %s", address, exc)
        return None


# ---------------------------------------------------------------------------
# Future Land Use spatial query
# ---------------------------------------------------------------------------

def query_future_land_use(lon: float, lat: float) -> Optional[dict]:
    """
    Identify the Future Land Use polygon at (lon, lat).
    Returns a dict with keys: lu_code, lu_label, lu_description, mu_category.
    """
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": str(OUT_SR),
        "layers": "all:6",          # layer index 6 — Future Land Use
        "tolerance": "5",
        "mapExtent": f"{lon-0.001},{lat-0.001},{lon+0.001},{lat+0.001}",
        "imageDisplay": "800,600,96",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = httpx.get(FUTURE_LAND_USE_URL, params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        attrs = results[0].get("attributes", {})
        lu_code = attrs.get("LU") or attrs.get("lu") or ""
        mu_cat  = attrs.get("MU_Category") or attrs.get("MU_CATEGORY") or ""
        if not lu_code:
            return None
        label = LU_LABELS.get(lu_code.upper(), lu_code)
        desc  = LU_DESCRIPTIONS.get(lu_code.upper(), "")
        return {
            "lu_code":        lu_code.upper(),
            "lu_label":       label,
            "lu_description": desc,
            "mu_category":    mu_cat or None,
        }
    except Exception as exc:
        logger.warning("Future land use query failed at (%s,%s): %s", lon, lat, exc)
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def lookup_comprehensive_plan(item_text: str, category: str = "") -> dict:
    """
    Main entry point.  Given agenda item text and its category label,
    returns a dict to merge into the analysis blob:

      comp_plan_address        – address that was looked up (or None)
      comp_plan_lu_code        – e.g. "GC"
      comp_plan_lu_label       – e.g. "General Commercial"
      comp_plan_lu_description – one-sentence description
      comp_plan_mu_category    – mixed-use sub-category if applicable
      comp_plan_map_url        – direct link to CFW map centred on address
      comp_plan_lookup_status  – "found" | "no_address" | "no_match" | "error"
    """
    base: dict = {
        "comp_plan_address":        None,
        "comp_plan_lu_code":        None,
        "comp_plan_lu_label":       None,
        "comp_plan_lu_description": None,
        "comp_plan_mu_category":    None,
        "comp_plan_map_url":        None,
        "comp_plan_lookup_status":  "no_address",
    }

    # Only run for relevant categories / keywords
    is_relevant = (
        category in REAL_ESTATE_CATEGORIES
        or bool(REAL_ESTATE_KEYWORDS.search(item_text))
    )
    if not is_relevant:
        return base

    address = extract_address(item_text)
    if not address:
        return base

    base["comp_plan_address"] = address

    coords = geocode(address)
    if not coords:
        base["comp_plan_lookup_status"] = "no_match"
        return base

    lon, lat = coords

    # Build a map URL centred on the address (zoom ~16)
    base["comp_plan_map_url"] = (
        "https://cfw.maps.arcgis.com/apps/webappviewer/index.html"
        f"?id=653d3a58efc848a1ad1e7516ee56c509"
        f"&center={lon},{lat}&level=16"
    )

    lu = query_future_land_use(lon, lat)
    if not lu:
        base["comp_plan_lookup_status"] = "no_match"
        return base

    base.update({
        "comp_plan_lu_code":        lu["lu_code"],
        "comp_plan_lu_label":       lu["lu_label"],
        "comp_plan_lu_description": lu["lu_description"],
        "comp_plan_mu_category":    lu["mu_category"],
        "comp_plan_lookup_status":  "found",
    })
    return base


def is_real_estate_item(category: str, title: str, description: str) -> bool:
    """Return True if this item warrants a comprehensive plan lookup."""
    if category in REAL_ESTATE_CATEGORIES:
        return True
    combined = f"{title} {description}"
    return bool(REAL_ESTATE_KEYWORDS.search(combined))
