"""
Rule-based fiscal impact analyzer for Fort Worth City Council agenda items.

Methodology: Fate TX 40-year revenue-to-cost analysis, adapted from:
  - Fort Worth Comprehensive Plan Appendix F (annexation framework)
  - Fate TX Forward Fate Comprehensive Plan (2021) per-zoning-case tool
  - Charlotte NC 2040 Plan (EPS scenario-based methodology)

No external APIs required. All parameters are embedded below and can be
adjusted in PARAMETERS to reflect updated Fort Worth data.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Fort Worth Fiscal Parameters
# ---------------------------------------------------------------------------
PARAMETERS = {
    # Tax rates
    "property_tax_rate": 0.7125 / 100,   # $0.7125 per $100 assessed value
    "city_sales_tax_rate": 0.01,          # 1% city portion of sales tax

    # Projection assumptions
    "analysis_years": 40,
    "annual_growth_rate": 0.025,          # 2.5% annual revenue/cost escalation
    "discount_rate": 0.03,                # 3% NPV discount rate

    # Fate TX fiscal health target
    "rc_ratio_target": 1.0,              # >= 1.0 is fiscally positive

    # Service costs (annual, per capita)
    "police_cost_per_capita": 350,
    "fire_ems_cost_per_capita": 180,
    "public_works_per_lane_mile": 800,
    "parks_per_acre": 12000,
    "admin_overhead_pct": 0.15,           # 15% overhead on direct costs

    # Average assessed values (for property tax revenue estimates)
    "avg_sfr_value": 280000,             # single-family home
    "avg_mf_unit_value": 140000,         # multifamily unit
    "avg_commercial_per_sqft": 85,       # commercial building $/sqft
    "avg_industrial_per_sqft": 45,       # industrial $/sqft
}

# ---------------------------------------------------------------------------
# Land-Use Prototype Parameters
# Per-acre annual revenue and cost estimates — derived from Fort Worth
# annexation analyses, Fate TX disclosures, and Charlotte EPS study.
# Single-family produces ~0.72 R/C; commercial produces ~2.4 R/C
# (Charlotte finding: SFR generates 2x the per-unit property tax of MF,
# but compact patterns have lower per-acre cost-to-serve)
# ---------------------------------------------------------------------------
LAND_USE_PROTOTYPES = {
    "Single-Family Residential": {
        "description": "Low-density detached homes, ~2–4 units/acre",
        "revenue_per_acre_yr1": 2_100,
        "cost_per_acre_yr1":    2_900,
        "rc_ratio":             0.72,
        "population_per_acre":  5.0,
        "lane_miles_per_acre":  0.08,
        "parks_acres_per_acre": 0.05,
    },
    "Multifamily Residential": {
        "description": "Apartments / townhomes, ~12–20 units/acre",
        "revenue_per_acre_yr1": 3_800,
        "cost_per_acre_yr1":    3_900,
        "rc_ratio":             0.97,
        "population_per_acre":  22.0,
        "lane_miles_per_acre":  0.04,
        "parks_acres_per_acre": 0.03,
    },
    "Commercial Retail": {
        "description": "Retail, restaurants, strip centers",
        "revenue_per_acre_yr1": 14_000,
        "cost_per_acre_yr1":     5_200,
        "rc_ratio":              2.7,
        "population_per_acre":   0,
        "lane_miles_per_acre":   0.10,
        "parks_acres_per_acre":  0,
    },
    "Office / Business Park": {
        "description": "Office buildings, professional services",
        "revenue_per_acre_yr1":  9_500,
        "cost_per_acre_yr1":     4_200,
        "rc_ratio":              2.26,
        "population_per_acre":   0,
        "lane_miles_per_acre":   0.06,
        "parks_acres_per_acre":  0,
    },
    "Industrial / Warehouse": {
        "description": "Manufacturing, distribution, logistics",
        "revenue_per_acre_yr1":  6_500,
        "cost_per_acre_yr1":     2_800,
        "rc_ratio":              2.32,
        "population_per_acre":   0,
        "lane_miles_per_acre":   0.12,
        "parks_acres_per_acre":  0,
    },
    "Mixed-Use": {
        "description": "Blend of residential + commercial/office",
        "revenue_per_acre_yr1":  8_000,
        "cost_per_acre_yr1":     4_600,
        "rc_ratio":              1.74,
        "population_per_acre":   10.0,
        "lane_miles_per_acre":   0.06,
        "parks_acres_per_acre":  0.02,
    },
    "Public / Institutional": {
        "description": "Schools, churches, government facilities",
        "revenue_per_acre_yr1":    200,
        "cost_per_acre_yr1":     3_000,
        "rc_ratio":              0.07,
        "population_per_acre":   0,
        "lane_miles_per_acre":   0.05,
        "parks_acres_per_acre":  0,
    },
    "Open Space / Park": {
        "description": "Parks, greenways, floodplain",
        "revenue_per_acre_yr1":     50,
        "cost_per_acre_yr1":     1_800,
        "rc_ratio":              0.03,
        "population_per_acre":   0,
        "lane_miles_per_acre":   0.01,
        "parks_acres_per_acre":  1.0,
    },
    "Unknown / Not Applicable": {
        "description": "Land use type not determinable from agenda text",
        "revenue_per_acre_yr1": None,
        "cost_per_acre_yr1":    None,
        "rc_ratio":             None,
        "population_per_acre":  None,
        "lane_miles_per_acre":  None,
        "parks_acres_per_acre": None,
    },
}

# ---------------------------------------------------------------------------
# Category classification keyword maps
# ---------------------------------------------------------------------------
_CATEGORY_KEYWORDS = {
    "Annexation": [
        "annex", "annexation", "ax-",
    ],
    "Zoning Change": [
        "rezone", "rezoning", "zoning change", "zc-", "planned development",
        "pd-", "spd-", "form-based", "mixed use district", "mu-",
        "zoning district", "text amendment to the zoning",
    ],
    "Development Agreement": [
        "development agreement", "tax increment", "tirz", "380 agreement",
        "economic development", "incentive agreement", "public improvement district",
        "pid",
    ],
    "Site Plan / Plat": [
        "site plan", "sp-", "final plat", "preliminary plat", "replat",
        "subdivision", "vacate", "right-of-way dedication",
    ],
    "Contract / Procurement": [
        "authorize", "authorizing", "award", "contract", "purchase",
        "agreement with", "professional services", "sole source",
        "cooperative purchase", "piggyback",
    ],
    "Budget Amendment": [
        "budget", "appropriat", "transfer of funds", "supplemental",
        "reserve fund", "bond fund", "capital improvement",
    ],
    "Infrastructure Project": [
        "street", "road", "bridge", "drainage", "water main", "sewer",
        "wastewater", "utility extension", "traffic signal", "sidewalk",
        "paving", "reconstruction", "rehabilitation", "improvement project",
        "cip project",
    ],
    "Policy / Ordinance": [
        "ordinance", "code amendment", "comprehensive plan", "flum",
        "future land use", "policy", "regulation", "text amendment",
        "fee schedule", "rate",
    ],
    "Personnel": [
        "appoint", "appointment", "confirm", "employment", "position",
        "salary", "compensation", "benefit",
    ],
    "Administrative": [
        "accept", "acknowledge", "receive", "report", "presentation",
        "annual report", "quarterly", "minutes",
    ],
}

_LAND_USE_KEYWORDS = {
    "Single-Family Residential": [
        "single-family", "single family", "sfr", "residential", "homes",
        "housing", "subdivision", "r1", "r-1", "r2", "low density",
        "detached",
    ],
    "Multifamily Residential": [
        "multifamily", "multi-family", "apartment", "townhome", "townhouse",
        "condo", "mf", "high density", "mixed residential",
    ],
    "Commercial Retail": [
        "retail", "commercial", "shopping", "restaurant", "grocery",
        "strip center", "c-1", "c-2", "general commercial", "neighborhood commercial",
    ],
    "Office / Business Park": [
        "office", "business park", "professional", "medical office",
        "corporate", "o-1", "o-2",
    ],
    "Industrial / Warehouse": [
        "industrial", "warehouse", "manufacturing", "logistics", "distribution",
        "i-1", "i-2", "light industrial", "heavy industrial",
    ],
    "Mixed-Use": [
        "mixed-use", "mixed use", "mu-", "town center", "urban village",
        "transit-oriented", "tod", "live-work", "walkable",
    ],
    "Public / Institutional": [
        "school", "church", "hospital", "government", "civic", "park",
        "public facility", "institutional", "cf-",
    ],
    "Open Space / Park": [
        "open space", "greenway", "floodplain", "park land", "nature",
        "preserve",
    ],
}


# ---------------------------------------------------------------------------
# Dollar amount extraction
# ---------------------------------------------------------------------------
_DOLLAR_PATTERN = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(?:(million|billion|thousand|M|B|K))?',
    re.IGNORECASE
)
_ACREAGE_PATTERN = re.compile(
    r'([\d,]+(?:\.\d+)?)\s*(?:[-–]?\s*acre|ac\.)',
    re.IGNORECASE
)


def _extract_dollar(text: str) -> Optional[float]:
    for m in _DOLLAR_PATTERN.finditer(text):
        raw = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        if suffix in ("million", "m"):
            raw *= 1_000_000
        elif suffix in ("billion", "b"):
            raw *= 1_000_000_000
        elif suffix in ("thousand", "k"):
            raw *= 1_000
        return raw
    return None


def _extract_acreage(text: str) -> Optional[float]:
    for m in _ACREAGE_PATTERN.finditer(text):
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
def _classify_category(title: str, description: str) -> str:
    text = (title + " " + description).lower()
    scores = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score:
            scores[cat] = score
    if not scores:
        return "Other"
    return max(scores, key=scores.get)


def _classify_land_use(title: str, description: str) -> str:
    text = (title + " " + description).lower()
    scores = {}
    for lu, keywords in _LAND_USE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score:
            scores[lu] = score
    if not scores:
        return "Unknown / Not Applicable"
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# 40-year projection (Fate TX methodology)
# ---------------------------------------------------------------------------
def _project_40yr(
    yr1_revenue: float,
    yr1_cost: float,
    growth_rate: float = PARAMETERS["annual_growth_rate"],
    discount_rate: float = PARAMETERS["discount_rate"],
    years: int = PARAMETERS["analysis_years"],
) -> dict:
    """
    Compute:
      - Cumulative 40-year net (undiscounted)
      - 40-year NPV
      - Break-even year (when cumulative net turns positive)
      - Years to repay road liabilities (Fate metric)
    """
    cumulative = 0.0
    npv = 0.0
    break_even_year = None

    for yr in range(1, years + 1):
        factor = (1 + growth_rate) ** (yr - 1)
        rev = yr1_revenue * factor
        cost = yr1_cost * factor
        net = rev - cost
        cumulative += net
        npv += net / ((1 + discount_rate) ** yr)
        if break_even_year is None and cumulative >= 0:
            break_even_year = yr

    return {
        "cumulative_40yr": round(cumulative),
        "npv_40yr": round(npv),
        "break_even_year": break_even_year,
    }


# ---------------------------------------------------------------------------
# Fort Worth zoning analysis helpers
# ---------------------------------------------------------------------------

# Regex to pull "From: "CODE" description To: "CODE" description" out of the text.
#
# Handles these Fort Worth patterns:
#   Standard:     From: "A-43" One-Family   To: "E" Neighborhood Commercial
#   PD amendment: From: "PD894" desc        To: Amend "PD894" new desc
#   Same zone+CUP:From: "K" Heavy Ind.      To: "K" Heavy Ind. with CUP
#   Curly quotes: From: “A-5” ... To: “PD/E” ...
#
# The (?:Amend\s+)? group makes the word "Amend" optional after "To:" so
# PD amendment items parse correctly even though the zone code isn't first.
# Character class [“”‘’"] matches straight AND curly quotes.
_Q = r'[“”‘’"]'  # any open/close quote variant

_ZC_FROM_TO = re.compile(
    r'From:\s*' + _Q + r'([^"“”‘’]+)' + _Q + r'\s*(.*?)'
    r'\s+To:\s*(?:Amend\s+)?'
    + _Q + r'([^"“”‘’]+)' + _Q + r'\s*(.*?)'
    r'(?=\s*(?:\(Recommended|Recommended|Speaker|\Z)|(?=\n\n)|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# Fallback: no quotes at all — match bare zone code (letters, digits, /, -)
# Used when the PDF strips quote characters entirely.
_ZC_FROM_TO_BARE = re.compile(
    r'From:\s+([A-Z][A-Z0-9/\-]*(?:-\d+)?)\s+(.*?)'
    r'\s+To:\s+(?:Amend\s+)?([A-Z][A-Z0-9/\-]*(?:-\d+)?)\s+(.*?)'
    r'(?=\s*(?:\(Recommended|Recommended|Speaker|\Z)|(?=\n\n)|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# Third fallback: PD amendment — "To: Amend PD[number] ..." with no From: clause.
# Fort Worth uses this pattern when amending an existing Planned Development (e.g. ZC-26-040, ZC-26-041).
_ZC_PD_AMEND = re.compile(
    r'To:\s+Amend\s+' + _Q + r'?(PD\d+)' + _Q + r'?\s+(.*?)'
    r'(?=\s*(?:\(Recommended|Recommended|Speaker|\Z)|(?=\n\n)|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# Fourth fallback: "change from CODE description to CODE description"
# Matches informal phrasing without colons or quotes, e.g.:
#   "rezone from A-5 One-Family to E Neighborhood Commercial"
#   "change from AG Agricultural to PD/MU-1 Mixed Use"
_ZC_CHANGE_FROM_TO = re.compile(
    r'(?:change|rezone|rezoning|zoning\s+change)\s+from\s+'
    r'([A-Z][A-Z0-9/\-]*(?:-\d+)?)\s*(.*?)\s+'
    r'to\s+([A-Z][A-Z0-9/\-]*(?:-\d+)?)\s*(.*?)'
    r'(?=\s*(?:,|\.|on\s+property|located|approximately|\(Recommended|\Z))',
    re.IGNORECASE | re.DOTALL,
)

# Fifth fallback: simple "from CODE to CODE" anywhere in text
_ZC_FROM_TO_SIMPLE = re.compile(
    r'\bfrom\s+' + _Q + r'?([A-Z][A-Z0-9/\-]*(?:-\d+)?)' + _Q + r'?\s*([\w\s\-/]*?)\s+'
    r'to\s+' + _Q + r'?([A-Z][A-Z0-9/\-]*(?:-\d+)?)' + _Q + r'?\s*([\w\s\-/]*?)'
    r'(?=\s*(?:,|\.|on\s+property|located|approximately|\(Recommended|\Z))',
    re.IGNORECASE | re.DOTALL,
)

# Map Fort Worth zone codes to plain-English land-use labels.
# Covers all zone codes seen across FW agendas as of 2026.
_FW_ZONE_MAP = {
    # Single-family residential
    "A":    "Single-Family Residential",
    "A-5":  "Single-Family Residential",
    "A-43": "Single-Family Residential",
    "R1":   "Zero-Lot-Line / Cluster Residential",
    "UR":   "Urban Residential (Medium Density)",
    "GR":   "General Residential",
    # Agricultural / rural
    "AG":   "Agricultural",
    "AN":   "Agricultural / Natural",
    "AR":   "Agricultural Residential",
    # Two-family / small multi
    "B":    "Two-Family Residential",
    # Multifamily
    "C":    "Low-Rise Multifamily Residential",
    "D":    "High-Density Multifamily Residential",
    "D-HR": "High-Rise Multifamily Residential",
    "D-HR1":"High-Rise Multifamily Residential",
    # Commercial
    "E":    "Neighborhood Commercial",
    "ER":   "Neighborhood Commercial Restricted",
    "F":    "General Commercial",
    "G":    "Intensive Commercial",
    "H":    "Central Business District",
    "NS":   "Neighborhood Service Commercial",
    # Industrial
    "I":    "Light Industrial",
    "J":    "Medium Industrial",
    "K":    "Heavy Industrial",
    # Special / civic
    "CF":   "Community Facilities / Institutional",
    "O-1":  "Floodplain / Open Space",
    "PD":   "Planned Development",
    # Special districts
    "PI-UL-2":   "Panther Island Urban District",
    "MU-1":      "Mixed-Use",
    "MU-2":      "Mixed-Use (Higher Intensity)",
    "MU":        "Mixed-Use",
    "TL-N":      "Trinity Lakes Neighborhood District",
    "SY-TSA":    "Stockyards Transition District",
    "SY-HCO":    "Stockyards Historic Core District",
    "UNZONED":   "Unzoned / ETJ",
}

# Which land-use prototype to use when the FW code is known
_FW_ZONE_TO_PROTOTYPE = {
    # Residential
    "Single-Family Residential":             "Single-Family Residential",
    "Zero-Lot-Line / Cluster Residential":   "Single-Family Residential",
    "Urban Residential (Medium Density)":    "Multifamily Residential",
    "General Residential":                   "Single-Family Residential",
    "Agricultural Residential":              "Single-Family Residential",
    "Trinity Lakes Neighborhood District":   "Single-Family Residential",
    "Two-Family Residential":                "Multifamily Residential",
    "Low-Rise Multifamily Residential":      "Multifamily Residential",
    "High-Density Multifamily Residential":  "Multifamily Residential",
    "High-Rise Multifamily Residential":     "Multifamily Residential",
    # Commercial
    "Neighborhood Commercial":               "Commercial Retail",
    "Neighborhood Commercial Restricted":    "Commercial Retail",
    "Neighborhood Service Commercial":       "Commercial Retail",
    "General Commercial":                    "Commercial Retail",
    "Intensive Commercial":                  "Commercial Retail",
    "Central Business District":             "Commercial Retail",
    "Stockyards Transition District":        "Mixed-Use",
    "Stockyards Historic Core District":     "Mixed-Use",
    # Industrial
    "Light Industrial":                      "Industrial / Warehouse",
    "Medium Industrial":                     "Industrial / Warehouse",
    "Heavy Industrial":                      "Industrial / Warehouse",
    # Civic / open space
    "Community Facilities / Institutional":  "Public / Institutional",
    "Floodplain / Open Space":               "Open Space / Park",
    "Agricultural":                          "Open Space / Park",
    "Agricultural / Natural":                "Open Space / Park",
    "Unzoned / ETJ":                         "Open Space / Park",
    # Mixed / special
    "Mixed-Use":                             "Mixed-Use",
    "Mixed-Use (Higher Intensity)":          "Mixed-Use",
    "Panther Island Urban District":         "Mixed-Use",
    "Planned Development":                   None,   # inferred from description
}


def _fw_zone_label(code: str, description: str) -> str:
    """Turn a Fort Worth zone code into a readable label."""
    code_clean = code.strip().upper()

    # 1. Exact match
    label = _FW_ZONE_MAP.get(code_clean)
    if label:
        return label

    # 2. Strip overlay suffix (A-5/HC → A-5, H/DD → H, UR/SSO → UR)
    base = code_clean.split("/")[0]
    label = _FW_ZONE_MAP.get(base)
    if label:
        return label

    # 3. Pattern-based families for codes with numeric suffixes
    #    (SY-TSA-130 → "SY-TSA" family, TL-N → "TL-N" exact, PD1354 → PD family)
    if code_clean.startswith("SY-TSA"):
        return "Stockyards Transition District"
    if code_clean.startswith("SY-HCO") or code_clean.startswith("SY-HC"):
        return "Stockyards Historic Core District"
    if code_clean.startswith("SY-"):
        return "Stockyards Historic District"
    if code_clean.startswith("PI-"):
        return "Panther Island Urban District"
    if code_clean.startswith("TL-"):
        return "Trinity Lakes Neighborhood District"
    if code_clean.startswith("PD") and any(c.isdigit() for c in code_clean):
        return "Planned Development"

    # 4. Fall back to the first clause of the description
    if description:
        label = description.strip().split(";")[0].split(".")[0].split("(")[0].strip()[:80]
        if label:
            return label

    return code_clean


def _parse_zoning_request(text: str) -> Optional[dict]:
    """
    Extract From/To zoning info from a Fort Worth ZC item description.
    Tries five patterns in order from most to least specific.
    """
    # 1. Quoted From: / To: (canonical Fort Worth format)
    m = _ZC_FROM_TO.search(text)
    if not m:
        # 2. Bare From: / To: (no quotes)
        m = _ZC_FROM_TO_BARE.search(text)
    if not m:
        # 3. PD amendment with no From: clause
        m3 = _ZC_PD_AMEND.search(text)
        if m3:
            pd_code = m3.group(1).strip()
            to_desc = m3.group(2).strip().rstrip(";,")
            proto   = _classify_land_use("", to_desc) or "Unknown / Not Applicable"
            return {
                "from_code":  pd_code,
                "from_label": "Planned Development",
                "from_desc":  "Existing conditions",
                "from_proto": proto,
                "to_code":    pd_code,
                "to_label":   "Planned Development",
                "to_desc":    to_desc[:200],
                "to_proto":   proto,
            }
        # 4. Informal "change/rezone from CODE to CODE"
        m = _ZC_CHANGE_FROM_TO.search(text)
    if not m:
        # 5. Simple "from CODE to CODE" anywhere in text
        m = _ZC_FROM_TO_SIMPLE.search(text)
    if not m:
        return None

    from_code = m.group(1).strip()
    from_desc = m.group(2).strip().rstrip(";,")
    to_code   = m.group(3).strip()
    to_desc   = m.group(4).strip().rstrip(";,")

    from_label = _fw_zone_label(from_code, from_desc)
    to_label   = _fw_zone_label(to_code, to_desc)

    from_proto = _FW_ZONE_TO_PROTOTYPE.get(from_label)
    to_proto   = _FW_ZONE_TO_PROTOTYPE.get(to_label)

    # If PD, try to infer prototype from the description text
    if from_proto is None:
        from_proto = _classify_land_use("", from_desc) or "Unknown / Not Applicable"
    if to_proto is None:
        to_proto = _classify_land_use("", to_desc) or "Unknown / Not Applicable"

    return {
        "from_code":  from_code,
        "from_label": from_label,
        "from_desc":  from_desc[:200],
        "from_proto": from_proto,
        "to_code":    to_code,
        "to_label":   to_label,
        "to_desc":    to_desc[:200],
        "to_proto":   to_proto,
    }


def _assess_vacancy(text: str) -> tuple[str, str]:
    """
    Return (status, rationale) for the parcel.
    status = 'Likely Vacant' | 'Likely Occupied' | 'Unknown'
    """
    t = text.lower()
    vacant_signals = [
        "vacant lot", "vacant land", "vacant parcel", "undeveloped",
        "raw land", "unimproved", "greenfield", "bare land", "empty lot",
        "no existing structure", "currently undeveloped",
    ]
    occupied_signals = [
        "existing building", "existing structure", "existing facility",
        "existing warehouse", "existing use", "currently used",
        "currently operates", "existing business", "operating",
        "currently houses", "occupied by",
    ]
    for sig in vacant_signals:
        if sig in t:
            return ("Likely Vacant", f'Phrase "{sig}" found in agenda description.')
    for sig in occupied_signals:
        if sig in t:
            return ("Likely Occupied", f'Phrase "{sig}" found in agenda description.')
    return (
        "Unknown",
        "The agenda text does not specify whether the parcel is currently vacant or improved. "
        "Check the staff report for site photos and existing-use details.",
    )


def _zoning_revenue_explanation(
    from_label: str,
    to_label: str,
    from_proto: str,
    to_proto: str,
) -> str:
    """Plain-English explanation of why the rezoning affects city revenue."""
    # Prototype revenue-to-cost ratios for reference
    rc = {p: LAND_USE_PROTOTYPES[p]["rc_ratio"] for p in LAND_USE_PROTOTYPES if LAND_USE_PROTOTYPES[p]["rc_ratio"]}

    from_rc = rc.get(from_proto)
    to_rc   = rc.get(to_proto)

    if from_rc is None and to_rc is None:
        return (
            "Fiscal impact could not be estimated because neither the current nor proposed "
            "zoning type has a standard revenue model. Review the M&C staff report for the "
            "fiscal impact note."
        )

    lines = []

    # Direction of change
    if to_rc and from_rc:
        direction = "improve" if to_rc > from_rc else ("worsen" if to_rc < from_rc else "not change")
        lines.append(
            f"This rezoning is expected to {direction} the city's fiscal position. "
            f"The current zoning ({from_label}) has an estimated revenue-to-cost ratio of "
            f"{from_rc:.2f}, meaning the city {'recovers' if from_rc >= 1 else 'loses'} "
            f"${from_rc:.2f} for every $1.00 it spends serving this land. "
            f"The proposed zoning ({to_label}) has a ratio of {to_rc:.2f}."
        )

    # Explain the main revenue mechanism for the proposed use
    mechanisms = {
        "Commercial Retail":       "Commercial uses generate sales tax revenue (Fort Worth keeps 1 cent of every dollar spent at retail and restaurants) plus property tax at typically higher assessed values per acre than residential.",
        "Industrial / Warehouse":  "Industrial uses generate property tax revenue from buildings and equipment, and impose low service costs (no schools, parks, or daily police calls). The city typically nets $2+ for every $1 spent serving industrial land.",
        "Single-Family Residential": "Single-family homes generate property tax revenue but also require police, fire, parks, and school-related infrastructure. Fort Worth's own annexation analyses show residential uses often cost more to serve than they generate.",
        "Multifamily Residential": "Multifamily housing generates property tax and utility fees. Higher density means more revenue per acre than single-family, though service costs are also higher.",
        "Mixed-Use":               "Mixed-use development blends residential (property tax, utility fees) and commercial (sales tax) revenue streams, generally producing a stronger fiscal return than purely residential development.",
        "Public / Institutional":  "Institutional uses (schools, government, churches) are typically tax-exempt, generating little direct city revenue while requiring city services. Fiscally this is the least favorable category.",
        "Open Space / Park":       "Open space generates minimal direct revenue. Its fiscal value is indirect — property value uplift for nearby parcels that do pay taxes.",
    }
    explanation = mechanisms.get(to_proto)
    if explanation:
        lines.append(explanation)

    return " ".join(lines) if lines else "See M&C staff report for fiscal impact detail."


def _estimate_zoning_economic_impact(
    to_proto: str,
    from_proto: str,
    acreage: float,
) -> dict:
    """
    Estimate the incremental economic impact of the rezoning over 40 years.
    Returns a dict with summary numbers and a plain-English rationale.
    """
    to_data   = LAND_USE_PROTOTYPES.get(to_proto,   LAND_USE_PROTOTYPES["Unknown / Not Applicable"])
    from_data = LAND_USE_PROTOTYPES.get(from_proto, LAND_USE_PROTOTYPES["Unknown / Not Applicable"])

    to_rev   = to_data.get("revenue_per_acre_yr1")
    to_cost  = to_data.get("cost_per_acre_yr1")
    from_rev = from_data.get("revenue_per_acre_yr1")
    from_cost= from_data.get("cost_per_acre_yr1")

    if to_rev is None:
        return {
            "annual_incremental_revenue": None,
            "annual_incremental_cost": None,
            "annual_net_change": None,
            "projected_40yr_impact": None,
            "rationale": "Estimated economic impact unavailable — proposed land use prototype not determinable from agenda text.",
        }

    # Incremental = (what it will be) minus (what it currently is)
    from_rev  = from_rev  or 0
    from_cost = from_cost or 0

    inc_rev  = (to_rev  - from_rev)  * acreage
    inc_cost = (to_cost - from_cost) * acreage
    inc_net  = inc_rev - inc_cost

    proj = _project_40yr(
        max(inc_rev,  0),
        max(inc_cost, 0),
    )
    net_40yr = round(inc_net * sum(
        (1 + PARAMETERS["annual_growth_rate"]) ** yr / (1 + PARAMETERS["discount_rate"]) ** yr
        for yr in range(1, PARAMETERS["analysis_years"] + 1)
    ))

    # Jobs estimate (rough): commercial ~15 jobs/acre, industrial ~8, residential ~0
    jobs_map = {
        "Commercial Retail":       15,
        "Industrial / Warehouse":  8,
        "Office / Business Park":  20,
        "Mixed-Use":               10,
        "Single-Family Residential": 0,
        "Multifamily Residential": 0,
        "Public / Institutional":  3,
        "Open Space / Park":       0,
    }
    est_jobs = round((jobs_map.get(to_proto, 0)) * acreage)

    # Build rationale
    rationale_parts = []

    if inc_net > 0:
        rationale_parts.append(
            f"The rezoning is projected to generate an additional ${inc_net:,.0f} per year "
            f"in net fiscal benefit to the city (${inc_rev:,.0f} new revenue minus "
            f"${inc_cost:,.0f} in additional service costs), based on {acreage:.1f} acres "
            f"of {to_proto.lower()}."
        )
    elif inc_net < 0:
        rationale_parts.append(
            f"The rezoning is projected to increase city service costs by ${abs(inc_net):,.0f} "
            f"per year above what the current zoning would require — the proposed use "
            f"demands more services than it generates in revenue."
        )
    else:
        rationale_parts.append("The rezoning is expected to have a roughly neutral annual fiscal impact.")

    if net_40yr != 0:
        rationale_parts.append(
            f"Over 40 years (discounted at 3%), the cumulative fiscal impact is estimated at "
            f"${net_40yr:,.0f}."
        )

    if est_jobs > 0:
        rationale_parts.append(
            f"{to_proto} development of this size typically supports approximately "
            f"{est_jobs} direct jobs."
        )

    rationale_parts.append(
        "These estimates are based on Fort Worth per-acre prototype values and assume "
        "full build-out. Actual impact depends on what gets built, market conditions, "
        "and the development timeline."
    )

    return {
        "annual_incremental_revenue": round(inc_rev),
        "annual_incremental_cost":    round(inc_cost),
        "annual_net_change":          round(inc_net),
        "projected_40yr_impact":      net_40yr,
        "estimated_jobs":             est_jobs if est_jobs > 0 else None,
        "rationale":                  " ".join(rationale_parts),
    }


def _enrich_zoning_analysis(result: dict, title: str, description: str, acreage: Optional[float]) -> dict:
    """
    For Zoning Change items, parse the From/To request and add enriched fields to result.
    Called from analyze_fiscal_impact after the base analysis is complete.
    """
    from services.zoning_uses import (
        detect_applicant_use,
        detect_approval_type,
        get_by_right_scenarios,
        compute_use_fiscal,
    )

    text = title + " " + description
    zr = _parse_zoning_request(text)
    if not zr:
        result["zoning_request_parsed"] = False
        return result

    assumed_acres = acreage or 1.0

    result["zoning_request_parsed"] = True
    result["zoning_from_code"]  = zr["from_code"]
    result["zoning_from_label"] = zr["from_label"]
    result["zoning_from_desc"]  = zr["from_desc"]
    result["zoning_to_code"]    = zr["to_code"]
    result["zoning_to_label"]   = zr["to_label"]
    result["zoning_to_desc"]    = zr["to_desc"]

    # Vacancy
    vacancy_status, vacancy_rationale = _assess_vacancy(text)
    result["vacancy_status"]    = vacancy_status
    result["vacancy_rationale"] = vacancy_rationale

    # Revenue explanation (prototype-level)
    result["revenue_explanation"] = _zoning_revenue_explanation(
        zr["from_label"], zr["to_label"],
        zr["from_proto"], zr["to_proto"],
    )

    # Prototype-level 40yr impact (baseline)
    impact = _estimate_zoning_economic_impact(zr["to_proto"], zr["from_proto"], assumed_acres)
    result["zoning_annual_net_change"]  = impact["annual_net_change"]
    result["zoning_40yr_impact"]        = impact["projected_40yr_impact"]
    result["zoning_estimated_jobs"]     = impact.get("estimated_jobs")
    result["zoning_economic_rationale"] = impact["rationale"]

    if impact["annual_incremental_revenue"] is not None:
        result["year1_revenue_estimate"] = impact["annual_incremental_revenue"]
        result["year1_cost_estimate"]    = impact["annual_incremental_cost"]
        result["year1_net_impact"]       = impact["annual_net_change"]
        result["projection_40yr_net"]    = impact["projected_40yr_impact"]

    # ── Approval type ────────────────────────────────────────────────────
    approval = detect_approval_type(zr["to_code"], zr["to_desc"])
    result["approval_type"]       = approval["type"]
    result["approval_label"]      = approval["label"]
    result["approval_short"]      = approval["short_label"]
    result["approval_color"]      = approval["color"]
    result["approval_explanation"]= approval["explanation"]

    # ── Applicant / stated use detection ─────────────────────────────────
    stated_use, confidence = detect_applicant_use(title, description)
    result["stated_use"]            = stated_use
    result["stated_use_confidence"] = confidence

    if stated_use:
        stated_fiscal = compute_use_fiscal(stated_use, assumed_acres, zr["to_code"])
        result["stated_use_fiscal"] = stated_fiscal
    else:
        result["stated_use_fiscal"] = None

    # ── By-right use scenarios ────────────────────────────────────────────
    scenarios = get_by_right_scenarios(zr["to_code"], assumed_acres)
    result["by_right_scenarios"] = scenarios

    # ── Fix fiscal_impact_rating to reflect direction of change ───────────
    # The base analysis rates the TO zone in isolation (e.g. any commercial =
    # POSITIVE). But a rezoning FROM a higher-value zone TO a lower-value zone
    # WORSENS the city's fiscal position even if the destination is still OK.
    # Override the rating based on the incremental from→to RC comparison.
    from_rc = LAND_USE_PROTOTYPES.get(zr["from_proto"] or "", {}).get("rc_ratio")
    to_rc   = LAND_USE_PROTOTYPES.get(zr["to_proto"]   or "", {}).get("rc_ratio")

    if from_rc is not None and to_rc is not None:
        if to_rc > from_rc + 0.05:
            result["fiscal_impact_rating"] = "POSITIVE"
        elif to_rc < from_rc - 0.05:
            result["fiscal_impact_rating"] = "NEGATIVE"
        else:
            result["fiscal_impact_rating"] = "NEUTRAL"
    elif impact.get("annual_net_change") is not None:
        net = impact["annual_net_change"]
        if net > 500:
            result["fiscal_impact_rating"] = "POSITIVE"
        elif net < -500:
            result["fiscal_impact_rating"] = "NEGATIVE"
        else:
            result["fiscal_impact_rating"] = "NEUTRAL"

    return result


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------
def analyze_fiscal_impact(item: dict) -> dict:
    """
    Produce a fiscal impact analysis for one agenda item using rule-based logic.

    Returns a dict matching the same schema the frontend expects, so no
    frontend changes are needed.
    """
    title = item.get("title", "")
    description = item.get("description", "")
    text = title + " " + description

    category = _classify_category(title, description)
    land_use = _classify_land_use(title, description)
    acreage = _extract_acreage(text)
    dollar_amount = _extract_dollar(text)

    # Determine the analysis path by category
    result = _dispatch(
        category=category,
        land_use=land_use,
        acreage=acreage,
        dollar_amount=dollar_amount,
        title=title,
        description=description,
    )

    result["category"] = category
    result["land_use_type"] = land_use if land_use != "Unknown / Not Applicable" else "N/A"
    result["acreage_estimate"] = acreage
    result["departments_impacted"] = _infer_departments(category, land_use, description)

    # Ensure rating exists
    if "fiscal_impact_rating" not in result:
        result["fiscal_impact_rating"] = "UNKNOWN"

    # For zoning cases, add enriched From/To analysis
    if category == "Zoning Change":
        try:
            result = _enrich_zoning_analysis(result, title, description, acreage)
        except Exception as _exc:
            import traceback, pathlib
            log = pathlib.Path(__file__).parent.parent / "zoning_error.log"
            log.write_text(traceback.format_exc())
            result["zoning_error"] = str(_exc)

    return result


def _is_annexation_hearing(title: str, description: str) -> bool:
    """
    Return True when the item is the PROCEDURAL public hearing step required
    before an annexation, not the actual annexation decision/ordinance.
    Texas Local Government Code requires one or two public hearings before
    annexation — these hearings have zero direct fiscal impact.
    """
    text = (title + " " + description).lower()
    hearing_phrases = [
        "conduct public hearing",
        "conduct a public hearing",
        "hold a public hearing",
        "holding a public hearing",
        "notice of public hearing",
        "notice of intent to annex",
        "set a date for",
        "set the date for",
        "first public hearing",
        "second public hearing",
        "schedule a hearing",
    ]
    has_hearing = any(phrase in text for phrase in hearing_phrases)
    has_annex   = "annex" in text
    return has_hearing and has_annex


def _annexation_hearing_result() -> dict:
    return {
        "fiscal_impact_rating": "NEUTRAL",
        "confidence": "HIGH",
        "year1_revenue_estimate": None,
        "year1_cost_estimate":    None,
        "year1_net_impact":       None,
        "revenue_to_cost_ratio":  None,
        "projection_40yr_net":    None,
        "break_even_year":        None,
        "key_revenue_sources":    [],
        "key_cost_drivers":       [],
        "infrastructure_requirements": None,
        "units_or_sqft_estimate": None,
        "analysis_narrative": (
            "This item conducts or schedules the public hearing required by Texas law "
            "(Local Gov't Code Ch. 43) before an annexation can be finalized. "
            "The hearing itself has no direct fiscal impact — it is a procedural notice "
            "step only. The actual fiscal impact applies to the subsequent annexation "
            "ordinance or resolution, which will appear as a separate agenda item."
        ),
        "caveats": (
            "Public hearing items are procedural. Look for the annexation ordinance "
            "or resolution item for the actual fiscal impact analysis."
        ),
        "annexation_hearing": True,
    }


def _site_plan_analysis(
    land_use: str,
    acreage: Optional[float],
    title: str,
    description: str,
) -> dict:
    """
    Two-tier analysis for Site Plan / Plat items.

    Tier 1 — Direct parcel impact: what THIS specific property generates once built.
    Tier 2 — Broader development potential: what surrounding development could be
              catalyzed (speculative; requires separate approvals and market conditions).
    """
    text = (title + " " + description).lower()

    # Classify action type
    is_replat     = "replat" in text or "re-plat" in text
    is_row_action = any(kw in text for kw in ["vacation", "vacating", "alley", "right-of-way"]) \
                    and any(kw in text for kw in ["right-of-way", "row", "alley", "street"])
    is_final      = "final plat" in text
    is_prelim     = "preliminary plat" in text

    if is_replat:
        action_type = "Replat"
    elif is_row_action:
        action_type = "Right-of-Way Vacation / Dedication"
    elif is_final:
        action_type = "Final Plat"
    elif is_prelim:
        action_type = "Preliminary Plat"
    else:
        action_type = "Site Plan"

    # ── Tier 1: direct parcel fiscal impact ──────────────────────────────
    assumed_acres = acreage or 1.0
    base = _land_use_analysis("Site Plan / Plat", land_use, acreage, title, description)
    base["site_plan_type"] = action_type

    if is_replat or is_row_action:
        # Reorganisation — no new development, no new fiscal impact
        base["site_plan_is_reorganization"] = True
        base["fiscal_impact_rating"]        = "NEUTRAL"
        base["analysis_narrative"] = (
            f"This {action_type.lower()} reorganises existing property boundaries or "
            f"adjusts a right-of-way. It does not create new development by itself. "
            f"No new assessed value or tax revenue is generated by the filing alone — "
            f"fiscal changes only occur if and when construction follows."
        )
        base["broader_development"] = None
        return base

    # Non-reorganisation plat — show direct impact note
    base["site_plan_is_reorganization"] = False
    direct_note = (
        f"Direct parcel impact: once built out, this {action_type.lower()} on "
        f"{'approximately ' + str(round(assumed_acres, 1)) + ' acres of ' if acreage else ''}"
        f"{land_use.lower()} would generate the revenue and cost estimates shown above. "
        f"The {action_type.lower()} approval itself is a regulatory step — fiscal "
        f"impact materialises only when building permits are issued and structures are completed."
    )
    base["analysis_narrative"] = direct_note

    # ── Tier 2: broader development potential ────────────────────────────
    bd = _estimate_broader_development(land_use, assumed_acres)
    base["broader_development"] = bd

    # ── Overall rating: the approval is always neutral as a regulatory step.
    # Upgrade to POSITIVE when broader development creates meaningful fiscal gain.
    if bd and (bd.get("estimated_annual_net") or 0) > 500:
        base["fiscal_impact_rating"] = "POSITIVE"
    else:
        base["fiscal_impact_rating"] = "NEUTRAL"

    return base


def _estimate_broader_development(land_use: str, acreage: float) -> Optional[dict]:
    """
    Estimate the speculative fiscal impact of surrounding development that this
    site plan / plat could catalyse. Always flagged LOW confidence.
    """
    proto = LAND_USE_PROTOTYPES

    if "Single-Family" in land_use or ("Residential" in land_use and "Multi" not in land_use):
        units  = max(1, round(acreage * 4))
        c_ac   = max(0.5, round(acreage / 12, 1))
        c_net  = round(c_ac * (proto["Commercial Retail"]["revenue_per_acre_yr1"]
                               - proto["Commercial Retail"]["cost_per_acre_yr1"]))
        return {
            "scenario_label":        "If neighborhood commercial follows these rooftops",
            "scenario_description":  (
                f"New residential subdivisions typically attract neighborhood commercial. "
                f"~{units} homes here could support approximately {c_ac:.1f} acres of "
                f"nearby retail, restaurants, and services on adjacent parcels."
            ),
            "catalyst_acres":        c_ac,
            "catalyst_land_use":     "Commercial Retail",
            "estimated_annual_net":  c_net,
            "estimated_jobs":        round(c_ac * 15),
            "estimated_40yr_npv":    round(c_net * 22),
            "confidence":            "LOW",
            "timeline":              "5–15 years after residential build-out",
            "caveat": (
                "This broader scenario requires neighboring property owners to develop, "
                "separate zoning and plat approvals, and favorable market conditions. "
                "This plat approval alone does not trigger any of it."
            ),
        }

    if "Commercial" in land_use:
        adj_ac  = round(acreage * 1.5, 1)
        adj_net = round(adj_ac * (proto["Commercial Retail"]["revenue_per_acre_yr1"]
                                  - proto["Commercial Retail"]["cost_per_acre_yr1"]))
        return {
            "scenario_label":        "Adjacent commercial node development potential",
            "scenario_description":  (
                f"Commercial uses tend to cluster. This site could help catalyse "
                f"approximately {adj_ac} additional acres of commercial or mixed-use "
                f"development on neighbouring parcels over time."
            ),
            "catalyst_acres":        adj_ac,
            "catalyst_land_use":     "Commercial Retail",
            "estimated_annual_net":  adj_net,
            "estimated_jobs":        round(adj_ac * 15),
            "estimated_40yr_npv":    round(adj_net * 22),
            "confidence":            "LOW",
            "timeline":              "3–10 years",
            "caveat": (
                "Adjacent development requires separate owner decisions, zoning changes, "
                "and plat approvals. Not guaranteed by this site plan."
            ),
        }

    if "Industrial" in land_use:
        adj_ac  = round(acreage * 0.75, 1)
        adj_net = round(adj_ac * (proto["Industrial / Warehouse"]["revenue_per_acre_yr1"]
                                  - proto["Industrial / Warehouse"]["cost_per_acre_yr1"]))
        return {
            "scenario_label":        "Adjacent industrial / logistics campus potential",
            "scenario_description":  (
                f"Industrial users cluster near shared infrastructure. This site could "
                f"attract approximately {adj_ac} additional acres of adjacent industrial "
                f"or warehouse development."
            ),
            "catalyst_acres":        adj_ac,
            "catalyst_land_use":     "Industrial / Warehouse",
            "estimated_annual_net":  adj_net,
            "estimated_jobs":        round(adj_ac * 5),
            "estimated_40yr_npv":    round(adj_net * 22),
            "confidence":            "LOW",
            "timeline":              "2–8 years",
            "caveat": (
                "Industrial clustering depends on infrastructure capacity, access, "
                "and neighboring landowner decisions. Not guaranteed by this plat."
            ),
        }

    if "Multifamily" in land_use:
        c_ac  = max(0.3, round(acreage / 8, 1))
        c_net = round(c_ac * (proto["Commercial Retail"]["revenue_per_acre_yr1"]
                               - proto["Commercial Retail"]["cost_per_acre_yr1"]))
        return {
            "scenario_label":        "Ground-floor or adjacent commercial potential",
            "scenario_description":  (
                f"Multifamily developments attract supporting commercial. This site could "
                f"support approximately {c_ac} acres of associated retail or services nearby."
            ),
            "catalyst_acres":        c_ac,
            "catalyst_land_use":     "Commercial Retail",
            "estimated_annual_net":  c_net,
            "estimated_jobs":        round(c_ac * 15),
            "estimated_40yr_npv":    round(c_net * 22),
            "confidence":            "LOW",
            "timeline":              "2–8 years",
            "caveat": (
                "Associated commercial requires separate approvals and market demand. "
                "Not guaranteed by this plat."
            ),
        }

    return None  # No meaningful broader scenario


def _dispatch(
    category: str,
    land_use: str,
    acreage: Optional[float],
    dollar_amount: Optional[float],
    title: str,
    description: str,
) -> dict:

    if category == "Annexation":
        if _is_annexation_hearing(title, description):
            return _annexation_hearing_result()
        return _land_use_analysis(category, land_use, acreage, title, description)

    if category in ("Zoning Change", "Development Agreement"):
        return _land_use_analysis(category, land_use, acreage, title, description)

    if category == "Site Plan / Plat":
        return _site_plan_analysis(land_use, acreage, title, description)

    if category == "Contract / Procurement":
        return _contract_analysis(dollar_amount, title, description)

    if category == "Budget Amendment":
        return _budget_analysis(dollar_amount, title, description)

    if category == "Infrastructure Project":
        return _infrastructure_analysis(dollar_amount, acreage, title, description)

    if category == "Policy / Ordinance":
        return _policy_analysis(title, description)

    # Personnel, Administrative, Other — minimal fiscal impact
    return {
        "fiscal_impact_rating": "UNKNOWN",
        "confidence": "HIGH",
        "year1_revenue_estimate": None,
        "year1_cost_estimate": None,
        "year1_net_impact": None,
        "revenue_to_cost_ratio": None,
        "projection_40yr_net": None,
        "break_even_year": None,
        "key_revenue_sources": [],
        "key_cost_drivers": [],
        "infrastructure_requirements": None,
        "units_or_sqft_estimate": None,
        "analysis_narrative": (
            "This item is administrative or personnel in nature and does not "
            "carry a direct land-use fiscal impact. Standard M&C fiscal certification applies."
        ),
        "caveats": "No land-use or dollar-value signals found in this item.",
    }


# ---------------------------------------------------------------------------
# Land-use analysis (Annexation / Zoning / Development)
# ---------------------------------------------------------------------------
def _land_use_analysis(
    category: str,
    land_use: str,
    acreage: Optional[float],
    title: str,
    description: str,
) -> dict:
    proto = LAND_USE_PROTOTYPES.get(land_use, LAND_USE_PROTOTYPES["Unknown / Not Applicable"])

    if proto["revenue_per_acre_yr1"] is None:
        return {
            "fiscal_impact_rating": "UNKNOWN",
            "confidence": "LOW",
            "year1_revenue_estimate": None,
            "year1_cost_estimate": None,
            "year1_net_impact": None,
            "revenue_to_cost_ratio": None,
            "projection_40yr_net": None,
            "break_even_year": None,
            "key_revenue_sources": [],
            "key_cost_drivers": [],
            "infrastructure_requirements": None,
            "units_or_sqft_estimate": None,
            "analysis_narrative": (
                f"This {category.lower()} item could not be classified by land-use type from "
                "the agenda text alone. A full fiscal analysis requires the proposed use, "
                "acreage, and development program from the staff report."
            ),
            "caveats": "Land use type undetermined. Provide acreage and proposed use for a quantitative estimate.",
        }

    # Assume 1 acre if none detected, flag as low confidence
    assumed_acreage = acreage if acreage else 1.0
    confidence = "MEDIUM" if acreage else "LOW"

    yr1_rev = proto["revenue_per_acre_yr1"] * assumed_acreage
    yr1_cost = proto["cost_per_acre_yr1"] * assumed_acreage
    yr1_net = yr1_rev - yr1_cost
    rc = yr1_rev / yr1_cost if yr1_cost > 0 else None

    # 40-year Fate TX projection
    proj = _project_40yr(yr1_rev, yr1_cost)

    # Rating based on R/C ratio
    if rc is None:
        rating = "UNKNOWN"
    elif rc >= PARAMETERS["rc_ratio_target"]:
        rating = "POSITIVE"
    elif rc >= 0.85:
        rating = "NEUTRAL"
    else:
        rating = "NEGATIVE"

    # Revenue sources and cost drivers by land use
    rev_sources, cost_drivers = _land_use_revenue_costs(land_use)

    # Infrastructure note for annexations
    infra = None
    if category == "Annexation":
        infra = (
            f"City must provide full municipal services to annexed area. "
            f"Typical obligations: fire station coverage within 4-minute response, "
            f"street lighting, water/wastewater connections, solid waste pickup."
        )
    elif category == "Zoning Change":
        infra = (
            f"Rezoning triggers infrastructure analysis in staff report. "
            f"Check traffic impact study and utility capacity assessment."
        )

    pop = proto["population_per_acre"] * assumed_acreage if proto["population_per_acre"] else None
    units_est = round(pop / 2.4) if pop and "Residential" in land_use and "Multi" not in land_use else None

    narrative = (
        f"This {category.lower()} involves approximately {assumed_acreage:,.0f} acres of "
        f"{land_use.lower()} development. "
        f"Based on Fort Worth fiscal parameters and the Fate TX 40-year methodology, "
        f"the estimated Year 1 net fiscal impact is "
        f"{'a surplus of' if yr1_net >= 0 else 'a deficit of'} "
        f"${abs(yr1_net):,.0f} (R/C ratio: {rc:.2f}). "
        f"Over 40 years, the cumulative net impact is estimated at "
        f"${proj['cumulative_40yr']:,.0f}."
    )
    if not acreage:
        narrative += " Note: acreage not detected in agenda text — estimate assumes 1 acre."

    return {
        "fiscal_impact_rating": rating,
        "confidence": confidence,
        "year1_revenue_estimate": round(yr1_rev),
        "year1_cost_estimate": round(yr1_cost),
        "year1_net_impact": round(yr1_net),
        "revenue_to_cost_ratio": round(rc, 2) if rc else None,
        "projection_40yr_net": proj["cumulative_40yr"],
        "break_even_year": proj["break_even_year"],
        "key_revenue_sources": rev_sources,
        "key_cost_drivers": cost_drivers,
        "infrastructure_requirements": infra,
        "units_or_sqft_estimate": units_est,
        "analysis_narrative": narrative,
        "caveats": (
            "Estimates use per-acre prototype values calibrated to Fort Worth conditions. "
            "Actual fiscal impact depends on final development program, market value at "
            "build-out, and adopted service levels. "
            + ("Acreage was not detected in the agenda text and was assumed to be 1 acre. " if not acreage else "")
        ),
    }


def _land_use_revenue_costs(land_use: str):
    defaults = {
        "Single-Family Residential": (
            ["Property tax (ad valorem)", "Utility fees (water/wastewater)", "Solid waste fees"],
            ["Police services", "Fire / EMS services", "Street maintenance", "Parks maintenance"],
        ),
        "Multifamily Residential": (
            ["Property tax (ad valorem)", "Utility fees", "Solid waste fees"],
            ["Police services", "Fire / EMS services", "Street maintenance"],
        ),
        "Commercial Retail": (
            ["Sales tax (1% city share)", "Property tax", "Permit / license fees", "Franchise fees"],
            ["Police services", "Fire / EMS services", "Street maintenance"],
        ),
        "Office / Business Park": (
            ["Property tax", "Permit fees", "Utility fees"],
            ["Fire / EMS services", "Street maintenance"],
        ),
        "Industrial / Warehouse": (
            ["Property tax", "Permit fees", "Utility fees (water)"],
            ["Street / heavy truck maintenance", "Fire / EMS services"],
        ),
        "Mixed-Use": (
            ["Property tax", "Sales tax", "Utility fees", "Permit fees"],
            ["Police services", "Fire / EMS services", "Street maintenance", "Parks maintenance"],
        ),
        "Public / Institutional": (
            ["Intergovernmental transfers (limited)"],
            ["Street maintenance", "Fire / EMS services", "Utility subsidies"],
        ),
        "Open Space / Park": (
            ["Grants (limited)", "Recreation fees (minimal)"],
            ["Parks maintenance", "Trail maintenance"],
        ),
    }
    return defaults.get(land_use, (["Various"], ["Various"]))


# ---------------------------------------------------------------------------
# Contract / Procurement analysis
# ---------------------------------------------------------------------------
def _contract_analysis(
    dollar_amount: Optional[float],
    title: str,
    description: str,
) -> dict:
    text = (title + " " + description).lower()

    # Is it a revenue contract or a cost contract?
    is_revenue = any(kw in text for kw in [
        "receive", "grant", "reimburse", "revenue", "collection", "fee for service",
    ])
    is_recurring = any(kw in text for kw in [
        "annual", "per year", "monthly", "recurring", "ongoing", "maintenance",
    ])

    if dollar_amount is None:
        return {
            "fiscal_impact_rating": "UNKNOWN",
            "confidence": "LOW",
            "year1_revenue_estimate": None,
            "year1_cost_estimate": None,
            "year1_net_impact": None,
            "revenue_to_cost_ratio": None,
            "projection_40yr_net": None,
            "break_even_year": None,
            "key_revenue_sources": [],
            "key_cost_drivers": ["Contract expenditure (amount not specified in agenda text)"],
            "infrastructure_requirements": None,
            "units_or_sqft_estimate": None,
            "analysis_narrative": (
                "This contract or procurement item does not include a dollar amount "
                "in the agenda text. Review the M&C report for the contract value."
            ),
            "caveats": "Dollar amount not found in agenda text.",
        }

    yr1_rev = dollar_amount if is_revenue else 0
    yr1_cost = 0 if is_revenue else dollar_amount

    if is_revenue:
        rating = "POSITIVE"
        narrative = (
            f"This item authorizes receipt of approximately ${dollar_amount:,.0f} in revenue "
            f"{'on an ongoing annual basis' if is_recurring else '(one-time)'}."
        )
    else:
        rating = "NEGATIVE" if dollar_amount > 500_000 else "NEUTRAL"
        narrative = (
            f"This contract authorizes expenditure of approximately ${dollar_amount:,.0f} "
            f"{'annually' if is_recurring else '(one-time)'}. "
            f"{'Large contracts (>$500K) are flagged as fiscally significant.' if dollar_amount > 500_000 else ''}"
        )

    proj_net = None
    if is_recurring:
        proj = _project_40yr(yr1_rev, yr1_cost)
        proj_net = proj["cumulative_40yr"]

    return {
        "fiscal_impact_rating": rating,
        "confidence": "HIGH" if dollar_amount else "LOW",
        "year1_revenue_estimate": round(yr1_rev) if yr1_rev else None,
        "year1_cost_estimate": round(yr1_cost) if yr1_cost else None,
        "year1_net_impact": round(yr1_rev - yr1_cost),
        "revenue_to_cost_ratio": None,
        "projection_40yr_net": proj_net,
        "break_even_year": None,
        "key_revenue_sources": (["Contract revenue / reimbursement"] if is_revenue else []),
        "key_cost_drivers": ([] if is_revenue else ["Contract payment"]),
        "infrastructure_requirements": None,
        "units_or_sqft_estimate": None,
        "analysis_narrative": narrative,
        "caveats": (
            "Contract fiscal analysis is based on the dollar amount extracted from the agenda title/description. "
            "Review the full M&C report for payment schedule, term, and any contingencies."
        ),
    }


# ---------------------------------------------------------------------------
# Budget Amendment analysis
# ---------------------------------------------------------------------------
def _budget_analysis(
    dollar_amount: Optional[float],
    title: str,
    description: str,
) -> dict:
    text = (title + " " + description).lower()
    is_increase = any(kw in text for kw in ["increase", "supplemental", "additional appropriation"])
    is_decrease = any(kw in text for kw in ["decrease", "reduce", "rescind"])

    if dollar_amount:
        yr1_net = -dollar_amount if is_increase else (dollar_amount if is_decrease else -dollar_amount)
        rating = "NEUTRAL" if abs(yr1_net) < 1_000_000 else ("NEGATIVE" if yr1_net < 0 else "POSITIVE")
        narrative = (
            f"Budget {'increase' if is_increase else 'amendment'} of ${dollar_amount:,.0f}. "
            f"{'This increases appropriations, reducing available fund balance.' if is_increase else ''}"
        )
        return {
            "fiscal_impact_rating": rating,
            "confidence": "HIGH",
            "year1_revenue_estimate": None,
            "year1_cost_estimate": round(dollar_amount) if is_increase else None,
            "year1_net_impact": round(yr1_net),
            "revenue_to_cost_ratio": None,
            "projection_40yr_net": None,
            "break_even_year": None,
            "key_revenue_sources": [],
            "key_cost_drivers": ["Budget appropriation"],
            "infrastructure_requirements": None,
            "units_or_sqft_estimate": None,
            "analysis_narrative": narrative,
            "caveats": "Budget amendments affect the current fiscal year appropriations only unless recurring.",
        }

    return {
        "fiscal_impact_rating": "UNKNOWN",
        "confidence": "LOW",
        "year1_revenue_estimate": None,
        "year1_cost_estimate": None,
        "year1_net_impact": None,
        "revenue_to_cost_ratio": None,
        "projection_40yr_net": None,
        "break_even_year": None,
        "key_revenue_sources": [],
        "key_cost_drivers": [],
        "infrastructure_requirements": None,
        "units_or_sqft_estimate": None,
        "analysis_narrative": "Budget amendment — amount not detected in agenda text. Review the M&C report.",
        "caveats": "Dollar amount not found.",
    }


# ---------------------------------------------------------------------------
# Infrastructure project analysis
# ---------------------------------------------------------------------------
def _infrastructure_analysis(
    dollar_amount: Optional[float],
    acreage: Optional[float],
    title: str,
    description: str,
) -> dict:
    text = (title + " " + description).lower()

    capital_cost = dollar_amount
    # Estimate annual maintenance from capital cost (typical 1.5% of capital/yr for roads)
    annual_maintenance = round(capital_cost * 0.015) if capital_cost else None

    # Determine if project generates ongoing service cost or is one-time
    is_new_infra = any(kw in text for kw in ["new", "construction", "build", "install", "extend"])

    rating = "NEUTRAL"
    if capital_cost and capital_cost > 5_000_000:
        rating = "NEGATIVE"  # Large capital projects reduce fund balance

    narrative_parts = []
    if capital_cost:
        narrative_parts.append(f"Capital cost of approximately ${capital_cost:,.0f}.")
    if annual_maintenance:
        narrative_parts.append(
            f"Estimated ongoing maintenance cost: ~${annual_maintenance:,.0f}/year "
            f"(at 1.5% of capital, per ASCE standard)."
        )
    if not narrative_parts:
        narrative_parts.append("Infrastructure project — dollar amount not detected in agenda text.")

    proj_net = None
    if annual_maintenance:
        proj = _project_40yr(0, annual_maintenance)
        proj_net = proj["cumulative_40yr"]

    return {
        "fiscal_impact_rating": rating,
        "confidence": "MEDIUM" if capital_cost else "LOW",
        "year1_revenue_estimate": None,
        "year1_cost_estimate": round(capital_cost) if capital_cost else None,
        "year1_net_impact": round(-capital_cost) if capital_cost else None,
        "revenue_to_cost_ratio": None,
        "projection_40yr_net": proj_net,
        "break_even_year": None,
        "key_revenue_sources": [],
        "key_cost_drivers": [
            "Capital construction cost",
            "Ongoing maintenance (est. 1.5%/yr of capital)",
        ],
        "infrastructure_requirements": (
            "New infrastructure creates long-term maintenance obligations. "
            "Confirm funding source (CIP, bond, developer contribution, or operating budget)."
        ),
        "units_or_sqft_estimate": None,
        "analysis_narrative": " ".join(narrative_parts),
        "caveats": (
            "Infrastructure lifecycle cost estimates use 1.5% annual maintenance assumption. "
            "Actual costs depend on material type, usage, and maintenance schedule."
        ),
    }


# ---------------------------------------------------------------------------
# Policy / Ordinance analysis
# ---------------------------------------------------------------------------
def _policy_analysis(title: str, description: str) -> dict:
    text = (title + " " + description).lower()

    # Fee changes affect revenue
    has_fee = any(kw in text for kw in ["fee", "rate", "charge", "assessment"])
    # Development standards affect future fiscal trajectory
    has_development_standard = any(kw in text for kw in [
        "setback", "height", "density", "parking", "far", "floor area",
        "minimum lot", "maximum", "impervious",
    ])

    if has_fee:
        rating = "POSITIVE"
        narrative = (
            "This ordinance or policy change involves fees or rates. "
            "Fee changes directly affect city revenue but amounts depend on volume of permits/applications. "
            "Review the fiscal note in the M&C report."
        )
    elif has_development_standard:
        rating = "NEUTRAL"
        narrative = (
            "This ordinance modifies development standards (setbacks, height, density, parking, etc.). "
            "While it does not have a direct immediate fiscal impact, changes to development standards "
            "shape the long-term land-use pattern and the city's future fiscal capacity. "
            "Per the Fate TX and Charlotte models, more compact/dense allowances generally improve "
            "revenue-per-acre ratios."
        )
    else:
        rating = "UNKNOWN"
        narrative = (
            "Policy or ordinance item with no direct fiscal signal detected in the agenda text. "
            "Review the M&C report for a fiscal certification."
        )

    return {
        "fiscal_impact_rating": rating,
        "confidence": "LOW",
        "year1_revenue_estimate": None,
        "year1_cost_estimate": None,
        "year1_net_impact": None,
        "revenue_to_cost_ratio": None,
        "projection_40yr_net": None,
        "break_even_year": None,
        "key_revenue_sources": (["Fee revenue"] if has_fee else []),
        "key_cost_drivers": [],
        "infrastructure_requirements": None,
        "units_or_sqft_estimate": None,
        "analysis_narrative": narrative,
        "caveats": (
            "Policy items require review of the full staff report and M&C fiscal certification "
            "for an accurate impact assessment."
        ),
    }


# ---------------------------------------------------------------------------
# Department inference
# ---------------------------------------------------------------------------
def _infer_departments(category: str, land_use: str, description: str) -> list[str]:
    depts = set()
    text = description.lower()

    if any(kw in text for kw in ["police", "law enforcement", "crime", "security"]):
        depts.add("Police")
    if any(kw in text for kw in ["fire", "ems", "emergency", "hazmat"]):
        depts.add("Fire / EMS")
    if any(kw in text for kw in ["water", "wastewater", "sewer", "utility"]):
        depts.add("Water / Wastewater")
    if any(kw in text for kw in ["street", "road", "paving", "traffic", "drainage"]):
        depts.add("Transportation & Public Works")
    if any(kw in text for kw in ["park", "recreation", "trail", "open space"]):
        depts.add("Parks & Recreation")
    if any(kw in text for kw in ["planning", "zoning", "development", "land use"]):
        depts.add("Planning & Development")
    if any(kw in text for kw in ["budget", "finance", "fund", "appropriat", "contract", "purchase"]):
        depts.add("Finance")

    # Default by category
    if not depts:
        defaults = {
            "Annexation": {"Police", "Fire / EMS", "Transportation & Public Works", "Water / Wastewater"},
            "Zoning Change": {"Planning & Development"},
            "Infrastructure Project": {"Transportation & Public Works"},
            "Contract / Procurement": {"Finance"},
            "Budget Amendment": {"Finance"},
        }
        depts = defaults.get(category, set())

    # Default by land use
    if "Residential" in land_use:
        depts.update({"Police", "Fire / EMS"})
    if "Commercial" in land_use or "Industrial" in land_use:
        depts.add("Fire / EMS")

    return sorted(depts)


# ---------------------------------------------------------------------------
# Batch extraction entry point (called from router)
# ---------------------------------------------------------------------------
def extract_agenda_items(agenda_text: str) -> list[dict]:
    """Delegate to pdf_parser's item extraction."""
    from services.pdf_parser import extract_agenda_items as _parse
    return _parse(agenda_text)
