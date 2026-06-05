"""
Fort Worth Comprehensive Plan – Future Land Use lookup.

Extracts a location from agenda item text, geocodes it, then queries
the FW Future Land Use MapServer layer for the comp-plan designation.

Handles all Fort Worth ZC description patterns:
  - Standard address:  "1234 Main Street"
  - Block reference:   "5200 block of Oak Grove Road"
  - Intersection:      "corner of Crowley Road and Altamesa Boulevard"
  - Directional clue:  "north of I-20 at Bryant Irvin Road"
  - Located-at phrase: "located at the southeast corner of ..."
"""

import re
import logging
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

OUT_SR = 4326  # WGS-84

# ---------------------------------------------------------------------------
# Comp-plan LU code → label / description
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
    "PRIOS": "Private Open Space (unverified — not in published comp plan legend)",
    "SY-TSA-130": "Stockyards Traditional Surrounding Area",
}

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
    # Non-standard codes returned by FW GIS but not defined in the published comp plan legend
    "PRIOS": "Private Open Space — code returned by Fort Worth GIS; not defined in the published comp plan legend. Likely denotes private open space, consistent with the PRIPK/PUBPK naming pattern. Verify with Fort Worth Planning & Development.",
    "SY-TSA-130": "Stockyards Traditional Surrounding Area — historic Stockyards district overlay zone.",
}

# ---------------------------------------------------------------------------
# Which items get the comp-plan lookup
# ---------------------------------------------------------------------------

REAL_ESTATE_CATEGORIES = {
    "Zoning Change",
    "Land / Real Estate",
    "Public Hearing",
    "Annexation",
    "Site Plan / Plat",
}

REAL_ESTATE_KEYWORDS = re.compile(
    r"\b("
    r"zon(ing)?|annex(ation)?|plat|subdivis|site\s*plan|replat|rezoning|"
    r"development|land\s*use|real\s*estate|property|parcel|acreage|"
    r"easement|right.of.way|"
    r"ZC[\s\-]?\d|SP[\s\-]?\d|SUP[\s\-]?\d|PD[\s\-]?\d|"
    r"specific\s*use|conditional\s*use|variance|"
    r"planned\s*dev|urban\s*village|growth\s*center|"
    r"overlay|corridor|concept\s*plan|"
    r"townhome|apartment|retail|warehouse|industrial\s*park"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Street-suffix vocabulary (for all regex patterns below)
# ---------------------------------------------------------------------------

_SUFFIX = (
    r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|"
    r"Lane|Ln|Court|Ct|Place|Pl|Way|Trail|Trl|Pkwy|Parkway|"
    r"Loop|Freeway|Fwy|Highway|Hwy|Circle|Cir|Terrace|Ter|"
    r"Run|Path|Pass|Pike|Point|Pt|Bend|Crossing|Cove|"
    r"Commons|Landing|Ridge|Creek|Row|Expressway|Expy|"
    r"North|South|East|West)"
)

_DIR = r"(?:[NSEW]\.?\s+|North\s+|South\s+|East\s+|West\s+|NE\s+|NW\s+|SE\s+|SW\s+)?"

# ---------------------------------------------------------------------------
# Pattern 1: standard numbered address
#   "1234 Main St", "4500 N. Hulen Street", "12400 W Cleburne Road"
# ---------------------------------------------------------------------------
_P_NUMBERED = re.compile(
    r"(?<!\d)(?<!-)(\d{3,6})\s+"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 2: "X block of <Street Name>"
#   "5200 block of Oak Grove Road", "the 4000 block of Camp Bowie"
# ---------------------------------------------------------------------------
_P_BLOCK = re.compile(
    r"(?<!\d)(\d{3,6})\s+block\s+of\s+"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 3: intersection  "X Road and Y Boulevard"
#   Triggered by "corner of", "intersection of", "at X and Y"
# ---------------------------------------------------------------------------
_P_INTERSECTION = re.compile(
    r"(?:corner\s+of|intersection\s+of|at\s+the\s+(?:\w+\s+)?corner\s+of)"
    r"\s+"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")"
    r"\s+and\s+"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")",
    re.IGNORECASE,
)

# Simpler "X Street and Y Road" without a corner/intersection prefix
_P_AND_STREETS = re.compile(
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")"
    r"\s+and\s+"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")"
    r"(?:\s+in\s+Fort\s+Worth)?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern 4: "located at/near/on <Street>"  (single street, no number)
#   "located on Berry Street", "property on Hulen"
# ---------------------------------------------------------------------------
_P_LOCATED_ON = re.compile(
    r"(?:located|situated|property|site|parcel)\s+(?:at|on|near|along)\s+"
    r"(?:the\s+)?"
    r"(" + _DIR + r"[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?" + _SUFFIX + r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helper: clean extracted text
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return re.sub(r"\s{2,}", " ", s).strip().rstrip(".,;")


def _fw(addr: str) -> str:
    """Append ', Fort Worth, TX' if not already present."""
    if "Fort Worth" not in addr:
        return f"{addr}, Fort Worth, TX"
    return addr


# ---------------------------------------------------------------------------
# Extract all candidate geocode strings from item text
# ---------------------------------------------------------------------------

def extract_location_candidates(text: str) -> list[str]:
    """
    Return a list of geocodable location strings from *text*, ordered from
    most to least specific.  Deduplicated, preserving order.
    """
    seen: set[str] = set()
    results: list[str] = []

    def add(s: str) -> None:
        s = _fw(_clean(s))
        # Drop strings that are too short or contain leading garbage
        core = s.replace(", Fort Worth, TX", "").strip()
        if len(core) < 6:
            return
        # Drop if it starts mid-word (artifact of partial regex match)
        if re.match(r"^[a-z]", core):
            return
        if s not in seen:
            seen.add(s)
            results.append(s)

    # 0. Dual address: "5329 & 5355 Main Street" → use first number + street
    _P_DUAL = re.compile(
        r'(?<!\d)(\d{3,6})\s*[&,]\s*\d{3,6}\s+'
        r'(' + _DIR + r'[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?' + _SUFFIX + r')',
        re.IGNORECASE,
    )
    for m in _P_DUAL.finditer(text):
        num = m.group(1)
        street = _clean(m.group(2))
        add(f"{num} {street}")

    # 0b. Boundary description: "generally bounded by ... Street" → extract first named street
    _P_BOUNDED = re.compile(
        r'(?:generally\s+bounded\s+by|between|north\s+of|south\s+of|east\s+of|west\s+of)'
        r'\s+(?:the\s+)?'
        r'(' + _DIR + r'[A-Za-z][A-Za-z0-9\.\s\-]{1,40}?' + _SUFFIX + r')',
        re.IGNORECASE,
    )
    for m in _P_BOUNDED.finditer(text):
        street = _clean(m.group(1))
        if len(street) > 5:
            add(street)

    # 1. Standard numbered addresses (most specific — try first)
    for m in _P_NUMBERED.finditer(text):
        num = m.group(1)
        street = _clean(m.group(2))
        # Skip if the number is part of a case reference like ZC-24-015
        pre = text[max(0, m.start()-5):m.start()]
        if re.search(r"[\-\.]$", pre.rstrip()):
            continue
        add(f"{num} {street}")

    # 2. Block references  →  use block number as the street number
    for m in _P_BLOCK.finditer(text):
        num = m.group(1)
        street = _clean(m.group(2))
        add(f"{num} {street}")

    # 3. Explicit intersections  →  "Street1 & Street2, Fort Worth, TX"
    for m in _P_INTERSECTION.finditer(text):
        s1 = _clean(m.group(1))
        s2 = _clean(m.group(2))
        add(f"{s1} & {s2}")

    # 4. "and" between two named streets (less reliable — add last)
    for m in _P_AND_STREETS.finditer(text):
        s1 = _clean(m.group(1))
        s2 = _clean(m.group(2))
        # Skip if too short or looks like a zone code
        if len(s1) < 5 or len(s2) < 5:
            continue
        add(f"{s1} & {s2}")

    # 5. Single street from "located at/on" phrase
    for m in _P_LOCATED_ON.finditer(text):
        add(_clean(m.group(1)))

    return results


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(address: str) -> Optional[tuple[float, float]]:
    """Return (longitude, latitude) or None.  Requires score ≥ 65."""
    params = {
        "SingleLine": address,
        "outFields": "Match_addr,Score",
        "maxLocations": "1",
        "f": "json",
        "outSR": str(OUT_SR),
        "countryCode": "USA",
        "location": "-97.3308,32.7555",   # Fort Worth centre — boosts local matches
        "distance": "50000",               # 50 km search radius
    }
    try:
        r = httpx.get(GEOCODE_URL, params=params, timeout=10)
        r.raise_for_status()
        candidates = r.json().get("candidates", [])
        if not candidates:
            return None
        best = candidates[0]
        if best.get("score", 0) < 65:
            logger.debug("Low geocode score %s for %r", best.get("score"), address)
            return None
        loc = best["location"]
        return loc["x"], loc["y"]
    except Exception as exc:
        logger.warning("Geocode failed for %r: %s", address, exc)
        return None


# ---------------------------------------------------------------------------
# FLU reverse mapping — some GIS records return full labels instead of codes
# ---------------------------------------------------------------------------
_FLU_LABEL_TO_CODE: dict[str, str] = {
    "SINGLE-FAMILY RESIDENTIAL":  "SF",
    "SINGLE FAMILY RESIDENTIAL":  "SF",
    "SUBURBAN RESIDENTIAL":        "SUB",
    "RURAL RESIDENTIAL":           "RURAL",
    "LOW-DENSITY RESIDENTIAL":     "LDR",
    "LOW DENSITY RESIDENTIAL":     "LDR",
    "MEDIUM-DENSITY RESIDENTIAL":  "MDR",
    "MEDIUM DENSITY RESIDENTIAL":  "MDR",
    "HIGH-DENSITY RESIDENTIAL":    "HDR",
    "HIGH DENSITY RESIDENTIAL":    "HDR",
    "URBAN RESIDENTIAL":           "UR",
    "MANUFACTURED HOUSING":        "MH",
    "NEIGHBORHOOD COMMERCIAL":     "NC",
    "GENERAL COMMERCIAL":          "GC",
    "MIXED-USE":                   "MU",
    "MIXED USE":                   "MU",
    "MIXED-USE GROWTH CENTER":     "MUGC",
    "MIXED USE GROWTH CENTER":     "MUGC",
    "LIGHT INDUSTRIAL":            "LI",
    "HEAVY INDUSTRIAL":            "HI",
    "INDUSTRIAL GROWTH CENTER":    "IGC",
    "INSTITUTIONAL":               "INST",
    "INFRASTRUCTURE":              "INFRA",
    "EXISTING PUBLIC PARKLAND":    "PUBPK",
    "PUBLIC PARK":                 "PUBPK",
    "PRIVATE PARK":                "PRIPK",
    "OPEN SPACE / PRIVATE PARKLAND": "PRIPK",
    "AGRICULTURAL":                "AG",
    "AGRICULTURAL (VACANT)":       "AG",
    "LAKES AND PONDS":             "WATER",
    "WATER":                       "WATER",
}


# ---------------------------------------------------------------------------
# Future Land Use spatial query
# ---------------------------------------------------------------------------

def query_future_land_use(lon: float, lat: float) -> Optional[dict]:
    """Query the FW Future Land Use MapServer layer at (lon, lat)."""
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": str(OUT_SR),
        "layers": "all:6",
        "tolerance": "10",
        "mapExtent": f"{lon-0.002},{lat-0.002},{lon+0.002},{lat+0.002}",
        "imageDisplay": "800,600,96",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = httpx.get(FUTURE_LAND_USE_URL, params=params, timeout=12)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        attrs = results[0].get("attributes", {})
        lu_raw  = (attrs.get("LU") or attrs.get("lu") or "").strip().upper()
        mu_cat  = attrs.get("MU_Category") or attrs.get("MU_CATEGORY") or ""
        if not lu_raw:
            return None
        # Some parcels return the full label instead of the code — reverse-map it
        lu_code = _FLU_LABEL_TO_CODE.get(lu_raw, lu_raw)
        return {
            "lu_code":        lu_code,
            "lu_label":       LU_LABELS.get(lu_code, lu_code.title()),
            "lu_description": LU_DESCRIPTIONS.get(lu_code, ""),
            "mu_category":    mu_cat or None,
        }
    except Exception as exc:
        logger.warning("FLU query failed at (%.5f, %.5f): %s", lon, lat, exc)
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def lookup_comprehensive_plan(item_text: str, category: str = "") -> dict:
    """
    Returns comp_plan_* fields to merge into the analysis blob.

    Strategy (in order):
      1. Extract ZC/SUP case number → query FW Zoning Cases GIS layer
         → FUTURE_LAN gives the comp plan code directly (fastest, most accurate)
      2. Extract street address / intersection → geocode → query Future Land Use layer
      3. If still no match, mark relevant so the UI section still renders
    """
    from services.zoning_gis_lookup import extract_case_numbers, lookup_zoning_case

    base: dict = {
        "comp_plan_relevant":       False,
        "comp_plan_address":        None,
        "comp_plan_lu_code":        None,
        "comp_plan_lu_label":       None,
        "comp_plan_lu_description": None,
        "comp_plan_mu_category":    None,
        "comp_plan_map_url":        (
            "https://cfw.maps.arcgis.com/apps/webappviewer/index.html"
            "?id=653d3a58efc848a1ad1e7516ee56c509"
        ),
        "comp_plan_lookup_status":  "no_address",
    }

    is_relevant = (
        category in REAL_ESTATE_CATEGORIES
        or bool(REAL_ESTATE_KEYWORDS.search(item_text))
    )
    if not is_relevant:
        return base

    base["comp_plan_relevant"] = True

    # ── Strategy 1: ZC case number → Zoning Cases GIS layer ─────────────────
    for case_num in extract_case_numbers(item_text):
        gis = lookup_zoning_case(case_num)
        if not gis:
            continue

        lu_code = gis.get("future_land_use_code", "").upper()
        address = gis.get("address", "")

        if address:
            base["comp_plan_address"] = address
            # Try to geocode the GIS address for a pinned map URL
            coords = geocode(_fw(address))
            if coords:
                lon, lat = coords
                base["comp_plan_map_url"] = (
                    "https://cfw.maps.arcgis.com/apps/webappviewer/index.html"
                    f"?id=653d3a58efc848a1ad1e7516ee56c509&center={lon},{lat}&level=16"
                )

        if lu_code and lu_code in LU_LABELS:
            base.update({
                "comp_plan_lu_code":         lu_code,
                "comp_plan_lu_label":        LU_LABELS[lu_code],
                "comp_plan_lu_description":  LU_DESCRIPTIONS.get(lu_code, ""),
                "comp_plan_lookup_status":   "found",
                "comp_plan_case_number":     case_num,
                "consistent_with_comp_plan": gis.get("consistent_with_comp_plan", ""),
                "zoning_applicant":          gis.get("applicant", ""),
                "zoning_action":             gis.get("action", ""),
            })
            return base

        # GIS record found but no usable FUTURE_LAN — fall through to geocode
        if address:
            break   # use GIS address for geocode strategy below

    # ── Strategy 2: address/intersection → geocode → FLU layer ───────────────
    addr_candidates = extract_location_candidates(item_text)

    # If GIS gave us an address, prepend it as the best candidate
    gis_address = base.get("comp_plan_address")
    if gis_address:
        full = _fw(gis_address)
        if full not in addr_candidates:
            addr_candidates.insert(0, full)

    tried: list[str] = []
    for address in addr_candidates:
        tried.append(address)
        coords = geocode(address)
        if not coords:
            continue

        lon, lat = coords
        base["comp_plan_address"] = address
        base["comp_plan_map_url"] = (
            "https://cfw.maps.arcgis.com/apps/webappviewer/index.html"
            f"?id=653d3a58efc848a1ad1e7516ee56c509&center={lon},{lat}&level=16"
        )

        lu = query_future_land_use(lon, lat)
        if lu:
            base.update({
                "comp_plan_lu_code":        lu["lu_code"],
                "comp_plan_lu_label":       lu["lu_label"],
                "comp_plan_lu_description": lu["lu_description"],
                "comp_plan_mu_category":    lu["mu_category"],
                "comp_plan_lookup_status":  "found",
            })
            return base

    if tried:
        base["comp_plan_address"] = tried[0]
        base["comp_plan_lookup_status"] = "no_match"

    return base


def is_real_estate_item(category: str, title: str, description: str) -> bool:
    if category in REAL_ESTATE_CATEGORIES:
        return True
    return bool(REAL_ESTATE_KEYWORDS.search(f"{title} {description}"))
