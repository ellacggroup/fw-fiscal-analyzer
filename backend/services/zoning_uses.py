"""
Fort Worth UDC by-right use fiscal parameters and applicant detection.

Data sources:
  - Fort Worth Unified Development Code (Appendix A, Article 4)
  - Texas Comptroller: taxable vs non-taxable services
  - Tarrant CAD 2024 assessed value benchmarks
  - ICSC, CoStar, BLS employment density benchmarks
  - Fort Worth FY2026 budget (service cost allocations)

Texas sales tax rule: Retail goods are taxable (Fort Worth keeps 1¢/$).
Most services are NOT taxable (gyms, medical offices, law firms, salons, etc.)
Exceptions: auto repair labor IS taxable in Texas; some amusements are taxable.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# City fiscal constants
# ---------------------------------------------------------------------------
FW_PROP_TAX_RATE   = 0.7125 / 100   # $0.7125 per $100 assessed value
FW_SALES_TAX_RATE  = 0.01           # city keeps 1 cent of every taxable dollar
DISCOUNT_RATE      = 0.03
GROWTH_RATE        = 0.025
ANALYSIS_YEARS     = 40

# Typical land values per acre by base zone (Fort Worth 2025, approximate)
LAND_VALUE_PER_ACRE = {
    "E":    500_000,   # Neighborhood Commercial
    "F":    650_000,   # General Commercial
    "G":    700_000,   # Intensive Commercial
    "H":  1_400_000,   # Central Business District
    "I":    200_000,   # Light Industrial
    "J":    175_000,   # Medium Industrial
    "K":    150_000,   # Heavy Industrial
    "A":     80_000,   # Single-Family (all A variants)
    "B":     90_000,   # Two-Family
    "C":    120_000,   # Low-Rise Multifamily
    "D":    180_000,   # High-Density Multifamily
    "UR":   110_000,   # Urban Residential
    "R1":    85_000,   # Zero Lot Line
    "MU":   350_000,   # Mixed-Use
    "NS":   450_000,   # Neighborhood Service
    "CF":    60_000,   # Community Facilities
    "O-1":   20_000,   # Floodplain / Open Space
}

# ---------------------------------------------------------------------------
# Use-type fiscal parameters
# ---------------------------------------------------------------------------
# Each use:
#   building_sqft_per_acre  — typical building footprint (accounts for parking)
#   improvement_value_sqft  — assessed improvement value $/sqft (Tarrant CAD)
#   sales_tax_generating    — True = retail goods sold; False = services only
#   annual_sales_sqft       — taxable retail sales $/sqft/yr (0 if not applicable)
#   jobs_per_acre           — direct employment (BLS/ICSC benchmarks)
#   service_cost_per_acre   — estimated annual city service cost (FW budget)
#   texas_tax_note          — plain-English Texas tax treatment
#   use_category            — broad grouping for UI display

USES = {

    # ── Neighborhood / General Commercial uses ───────────────────────────

    "Fast Food / Quick Service Restaurant": {
        "building_sqft_per_acre":  4_500,
        "improvement_value_sqft":  325,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       620,   # QSR averages $600–700/sqft revenue
        "jobs_per_acre":           32,
        "service_cost_per_acre":   5_200,
        "texas_tax_note":          "Restaurant food and drink sales are taxable in Texas — one of the highest sales tax generators per square foot.",
        "use_category":            "Food & Beverage",
    },
    "Sit-Down Restaurant": {
        "building_sqft_per_acre":  6_500,
        "improvement_value_sqft":  290,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       380,
        "jobs_per_acre":           24,
        "service_cost_per_acre":   5_000,
        "texas_tax_note":          "Dine-in restaurant food and alcohol sales are fully taxable in Texas.",
        "use_category":            "Food & Beverage",
    },
    "General Retail Store": {
        "building_sqft_per_acre":  10_000,
        "improvement_value_sqft":  140,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       280,
        "jobs_per_acre":           15,
        "service_cost_per_acre":   4_800,
        "texas_tax_note":          "Retail merchandise sales are taxable. Sales tax yield depends heavily on product mix and store volume.",
        "use_category":            "Retail",
    },
    "Grocery / Specialty Food Store": {
        "building_sqft_per_acre":  18_000,
        "improvement_value_sqft":  120,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       420,   # high volume, tight margins
        "jobs_per_acre":           18,
        "service_cost_per_acre":   5_400,
        "texas_tax_note":          "Most grocery food is NOT taxable in Texas (unprepared food is exempt). Prepared foods, non-food items, and alcohol ARE taxable — typically 30–40% of grocery revenue is taxable.",
        "use_category":            "Retail",
    },
    "Pharmacy / Drug Store": {
        "building_sqft_per_acre":  9_000,
        "improvement_value_sqft":  150,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       320,
        "jobs_per_acre":           12,
        "service_cost_per_acre":   4_500,
        "texas_tax_note":          "Prescription drugs are NOT taxable in Texas. Over-the-counter drugs, cosmetics, and general merchandise ARE taxable. Taxable portion is typically 50–60% of revenue.",
        "use_category":            "Retail",
    },
    "Auto Parts Store (Retail Only)": {
        "building_sqft_per_acre":  8_000,
        "improvement_value_sqft":  135,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       210,
        "jobs_per_acre":           10,
        "service_cost_per_acre":   4_200,
        "texas_tax_note":          "Auto parts sold at retail are taxable. This is a retail-only use — no repair labor (which would require a Specific Use in zone E).",
        "use_category":            "Retail",
    },
    "Personal Service (Salon, Nail, Laundry)": {
        "building_sqft_per_acre":  5_000,
        "improvement_value_sqft":  130,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           14,
        "service_cost_per_acre":   4_000,
        "texas_tax_note":          "Personal services (hair salons, nail salons, dry cleaning) are NOT taxable in Texas. Revenue to the city comes from property tax only.",
        "use_category":            "Service",
    },
    "Medical / Dental Office": {
        "building_sqft_per_acre":  10_000,
        "improvement_value_sqft":  220,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           18,
        "service_cost_per_acre":   4_200,
        "texas_tax_note":          "Medical and dental services are NOT taxable in Texas. Revenue to the city is property tax only — but medical office buildings carry high assessed values.",
        "use_category":            "Office / Medical",
    },
    "Professional Office (Law, Finance, Insurance)": {
        "building_sqft_per_acre":  12_000,
        "improvement_value_sqft":  180,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           20,
        "service_cost_per_acre":   4_000,
        "texas_tax_note":          "Professional services (legal, accounting, insurance) are NOT taxable in Texas. City revenue is property tax only.",
        "use_category":            "Office / Medical",
    },
    "Bank / Financial Institution": {
        "building_sqft_per_acre":  4_000,
        "improvement_value_sqft":  240,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           10,
        "service_cost_per_acre":   3_800,
        "texas_tax_note":          "Banking and financial services are NOT taxable in Texas. Relatively small footprints but high improvement values generate meaningful property tax.",
        "use_category":            "Office / Medical",
    },
    "Gym / Fitness Center": {
        "building_sqft_per_acre":  16_000,
        "improvement_value_sqft":  110,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           6,
        "service_cost_per_acre":   4_500,
        "texas_tax_note":          "Gym memberships and fitness services are NOT taxable in Texas. Large building footprint but no sales tax revenue — city earns property tax only.",
        "use_category":            "Recreation / Entertainment",
    },
    "Daycare / Child Care Center": {
        "building_sqft_per_acre":  6_000,
        "improvement_value_sqft":  125,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           12,
        "service_cost_per_acre":   3_800,
        "texas_tax_note":          "Child care and educational services are NOT taxable in Texas. Property tax only, with modest building values.",
        "use_category":            "Service",
    },
    "Hotel / Motel": {
        "building_sqft_per_acre":  20_000,
        "improvement_value_sqft":  160,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       180,   # hotel room revenue + ancillary
        "jobs_per_acre":           20,
        "service_cost_per_acre":   5_500,
        "texas_tax_note":          "Hotel room charges are taxable in Texas (sales tax + hotel occupancy tax). Fort Worth also collects a separate hotel occupancy tax (HOT) on top of sales tax.",
        "use_category":            "Hospitality",
    },
    "Car Dealership (New / Used)": {
        "building_sqft_per_acre":  6_000,
        "improvement_value_sqft":  200,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       1_200,  # very high — vehicle prices are large
        "jobs_per_acre":           18,
        "service_cost_per_acre":   5_000,
        "texas_tax_note":          "Vehicle sales are taxable in Texas. Car dealerships are among the highest sales tax generators per acre due to high vehicle prices, though tax is capped per transaction.",
        "use_category":            "Retail",
    },

    # ── Industrial uses ──────────────────────────────────────────────────

    "Warehouse / Distribution Center": {
        "building_sqft_per_acre":  22_000,
        "improvement_value_sqft":  65,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           5,
        "service_cost_per_acre":   3_000,
        "texas_tax_note":          "Warehouse and distribution operations are NOT sales tax generators (goods are stored/moved, not sold to end consumers here). City earns property tax on buildings and equipment.",
        "use_category":            "Industrial",
    },
    "Light Manufacturing / Assembly": {
        "building_sqft_per_acre":  20_000,
        "improvement_value_sqft":  70,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           8,
        "service_cost_per_acre":   3_200,
        "texas_tax_note":          "Manufacturing operations pay property tax on buildings and machinery. Manufactured goods sold to Texas retailers generate sales tax at the point of retail sale, not here.",
        "use_category":            "Industrial",
    },
    "Mini-Storage / Self-Storage": {
        "building_sqft_per_acre":  16_000,
        "improvement_value_sqft":  55,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           2,
        "service_cost_per_acre":   2_500,
        "texas_tax_note":          "Storage unit rental is NOT taxable in Texas. Very low employment and low city service demand — generates property tax only at modest building values.",
        "use_category":            "Industrial",
    },
    "Auto Repair / Body Shop": {
        "building_sqft_per_acre":  8_000,
        "improvement_value_sqft":  90,
        "sales_tax_generating":    True,
        "annual_sales_sqft":       95,
        "jobs_per_acre":           10,
        "service_cost_per_acre":   4_000,
        "texas_tax_note":          "Auto repair LABOR is taxable in Texas (unlike most services). Parts sold are also taxable. This makes auto repair one of the few service uses that generates sales tax.",
        "use_category":            "Industrial",
    },
    "Trade Contractor (Office + Yard)": {
        "building_sqft_per_acre":  5_000,
        "improvement_value_sqft":  80,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           6,
        "service_cost_per_acre":   3_000,
        "texas_tax_note":          "Contractor services (plumbing, electrical, HVAC) are generally NOT taxable. Materials are taxed at point of purchase, not here.",
        "use_category":            "Industrial",
    },
    "Heavy Manufacturing": {
        "building_sqft_per_acre":  18_000,
        "improvement_value_sqft":  75,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           10,
        "service_cost_per_acre":   3_500,
        "texas_tax_note":          "Heavy manufacturing pays property tax on land, buildings, and heavy equipment (business personal property tax). No sales tax generated at this location.",
        "use_category":            "Industrial",
    },
    "Concrete / Asphalt Batch Plant": {
        "building_sqft_per_acre":  5_000,
        "improvement_value_sqft":  60,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           6,
        "service_cost_per_acre":   4_000,
        "texas_tax_note":          "Ready-mix concrete and asphalt sales to contractors may be taxable; however, most batch plant operations involve business-to-business sales which are often tax-exempt under contractor exemptions.",
        "use_category":            "Industrial",
    },
    "Recycling / Processing Facility": {
        "building_sqft_per_acre":  8_000,
        "improvement_value_sqft":  50,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           8,
        "service_cost_per_acre":   3_800,
        "texas_tax_note":          "Recycling operations are not typically sales-tax-generating at the facility level. City revenue is property tax on land and equipment only.",
        "use_category":            "Industrial",
    },

    # ── Residential uses ─────────────────────────────────────────────────

    "Single-Family Residence": {
        "building_sqft_per_acre":  9_600,   # 2,400 sqft home × 4 units/acre
        "improvement_value_sqft":  140,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           0,
        "service_cost_per_acre":   2_900,
        "texas_tax_note":          "Residential properties do not generate sales tax. Property tax is the primary city revenue source — but residential uses cost the city more to serve (police, fire, parks) than they generate.",
        "use_category":            "Residential",
    },
    "Duplex (Two-Family)": {
        "building_sqft_per_acre":  10_000,
        "improvement_value_sqft":  125,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           0,
        "service_cost_per_acre":   3_100,
        "texas_tax_note":          "No sales tax. Property tax only. Slightly higher density than single-family improves the revenue-per-acre ratio but still typically costs more than it generates.",
        "use_category":            "Residential",
    },
    "Garden Apartment Complex": {
        "building_sqft_per_acre":  18_000,   # 3-story garden-style
        "improvement_value_sqft":  130,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           1,
        "service_cost_per_acre":   3_800,
        "texas_tax_note":          "No sales tax. Property tax based on the income approach (rent × cap rate) rather than cost. Multifamily typically has better R/C ratios than single-family due to higher density.",
        "use_category":            "Residential",
    },
    "Urban Row House / Townhome": {
        "building_sqft_per_acre":  12_000,
        "improvement_value_sqft":  160,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           0,
        "service_cost_per_acre":   3_200,
        "texas_tax_note":          "No sales tax. Townhomes are typically individually assessed and taxed like single-family homes at higher per-unit values.",
        "use_category":            "Residential",
    },

    # ── Civic / Special uses ─────────────────────────────────────────────

    "Religious Institution / Church": {
        "building_sqft_per_acre":  8_000,
        "improvement_value_sqft":  0,       # tax-exempt in Texas
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           2,
        "service_cost_per_acre":   2_800,
        "texas_tax_note":          "Religious organizations are property-tax EXEMPT in Texas. The city earns no property tax revenue and receives no sales tax — this is a net cost to the city's fiscal position.",
        "use_category":            "Civic / Institutional",
    },
    "Government / Public Facility": {
        "building_sqft_per_acre":  10_000,
        "improvement_value_sqft":  0,
        "sales_tax_generating":    False,
        "annual_sales_sqft":       0,
        "jobs_per_acre":           15,
        "service_cost_per_acre":   3_000,
        "texas_tax_note":          "Government-owned property is exempt from property tax. No sales tax revenue. Provides public employment but zero direct tax revenue to the city.",
        "use_category":            "Civic / Institutional",
    },
}

# ---------------------------------------------------------------------------
# By-right uses by Fort Worth zone code
# ---------------------------------------------------------------------------
BY_RIGHT_USES = {
    "E": [
        "Fast Food / Quick Service Restaurant",
        "Sit-Down Restaurant",
        "General Retail Store",
        "Grocery / Specialty Food Store",
        "Pharmacy / Drug Store",
        "Auto Parts Store (Retail Only)",
        "Personal Service (Salon, Nail, Laundry)",
        "Medical / Dental Office",
        "Professional Office (Law, Finance, Insurance)",
        "Bank / Financial Institution",
        "Gym / Fitness Center",
        "Daycare / Child Care Center",
    ],
    "F": [
        "Fast Food / Quick Service Restaurant",
        "Sit-Down Restaurant",
        "General Retail Store",
        "Grocery / Specialty Food Store",
        "Pharmacy / Drug Store",
        "Auto Parts Store (Retail Only)",
        "Medical / Dental Office",
        "Professional Office (Law, Finance, Insurance)",
        "Gym / Fitness Center",
        "Hotel / Motel",
        "Car Dealership (New / Used)",
        "Auto Repair / Body Shop",
    ],
    "G": [
        "Fast Food / Quick Service Restaurant",
        "Sit-Down Restaurant",
        "General Retail Store",
        "Hotel / Motel",
        "Car Dealership (New / Used)",
        "Auto Repair / Body Shop",
        "Warehouse / Distribution Center",
    ],
    "H": [
        "Professional Office (Law, Finance, Insurance)",
        "Medical / Dental Office",
        "Sit-Down Restaurant",
        "Fast Food / Quick Service Restaurant",
        "General Retail Store",
        "Bank / Financial Institution",
        "Hotel / Motel",
        "Gym / Fitness Center",
    ],
    "I": [
        "Warehouse / Distribution Center",
        "Light Manufacturing / Assembly",
        "Mini-Storage / Self-Storage",
        "Auto Repair / Body Shop",
        "Trade Contractor (Office + Yard)",
    ],
    "J": [
        "Warehouse / Distribution Center",
        "Light Manufacturing / Assembly",
        "Heavy Manufacturing",
        "Auto Repair / Body Shop",
        "Trade Contractor (Office + Yard)",
    ],
    "K": [
        "Heavy Manufacturing",
        "Concrete / Asphalt Batch Plant",
        "Recycling / Processing Facility",
        "Warehouse / Distribution Center",
    ],
    "A-5": ["Single-Family Residence"],
    "A-43":["Single-Family Residence"],
    "A":   ["Single-Family Residence"],
    "B":   ["Duplex (Two-Family)", "Single-Family Residence"],
    "C":   ["Garden Apartment Complex", "Urban Row House / Townhome"],
    "D":   ["Garden Apartment Complex"],
    "D-HR":["Garden Apartment Complex"],
    "UR":  ["Urban Row House / Townhome", "Garden Apartment Complex"],
    "R1":  ["Urban Row House / Townhome", "Single-Family Residence"],
    "MU-1":["Urban Row House / Townhome", "Professional Office (Law, Finance, Insurance)", "General Retail Store"],
    "MU-2":["Garden Apartment Complex", "Professional Office (Law, Finance, Insurance)", "Sit-Down Restaurant"],
    "NS":  ["General Retail Store", "Personal Service (Salon, Nail, Laundry)", "Medical / Dental Office"],
    "CF":  ["Government / Public Facility", "Religious Institution / Church"],
}

# ---------------------------------------------------------------------------
# Applicant / stated-use detection
# ---------------------------------------------------------------------------
_APPLICANT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Food & Beverage — fast food (named chains)
    (re.compile(
        r"mcdonald|burger king|taco bell|whataburger|chick.fil|wendy|sonic|jack in the box|"
        r"dairy queen|popeyes|raising cane|dutch bros|starbucks|dunkin|panda express|"
        r"chipotle|subway|domino|pizza hut|papa john|little caesar|church.s chicken",
        re.I), "Fast Food / Quick Service Restaurant"),
    # Food & Beverage — general restaurant signals
    (re.compile(r"\brestaurant\b|\bdining\b|\bfood hall\b|\bbrewery\b|\bbar &|\btavern\b|\bpub\b", re.I),
     "Sit-Down Restaurant"),
    # Automotive
    (re.compile(r"autozone|o.reilly|advance auto|napa auto|parts?\s+(store|city)\b", re.I),
     "Auto Parts Store (Retail Only)"),
    (re.compile(r"\bauto\s*(repair|body|service|shop|mechanic)\b|\bcollision\b|\btire\s*(shop|center)\b|\bmuffler\b", re.I),
     "Auto Repair / Body Shop"),
    (re.compile(r"\bcar\s*(dealer|dealership|lot|sales)\b|\bauto\s*dealer|\bford\b|\bchevrolet\b|\btoyota\b|\bhonda dealer|\bkia\s+of\b", re.I),
     "Car Dealership (New / Used)"),
    # Fitness
    (re.compile(
        r"fitness|gym\b|planet\s+fitness|anytime\s+fitness|la\s+fitness|orange\s+theory|"
        r"crunch\s+fitness|snap\s+fitness|f45|crossfit|ymca|\bspa\b|wellness\s+center",
        re.I), "Gym / Fitness Center"),
    # Medical
    (re.compile(r"\bmedical\b|\bclinic\b|\bdental\b|\bdentist\b|\bdoctor\b|\bphysician\b|\borthopedic\b|\burgent\s+care\b|\bhealth\s+(center|system|care)\b", re.I),
     "Medical / Dental Office"),
    # Hotel
    (re.compile(r"\bhotel\b|\bmotel\b|\binn\b|\bsuites?\b|\bmarriott\b|\bhilton\b|\bhyatt\b|\bihr\b|\bwyndham\b|\bsheraton\b", re.I),
     "Hotel / Motel"),
    # Grocery / pharmacy
    (re.compile(r"\bgrocery\b|\bsupermarket\b|\bfood\s+(store|market)\b|\bkroger\b|\btom\s+thumb\b|\bheb\b|\bwhole\s+foods\b|\baldi\b|\bsprouts\b", re.I),
     "Grocery / Specialty Food Store"),
    (re.compile(r"\bpharmacy\b|\bdrug\s+store\b|\bcvs\b|\bwalgreens\b|\brite\s+aid\b", re.I),
     "Pharmacy / Drug Store"),
    # Daycare
    (re.compile(r"\bdaycare\b|\bday\s+care\b|\bchild\s+care\b|\bpreschool\b|\bkindergarten\b|\bmontessori\b|\blearning\s+center\b", re.I),
     "Daycare / Child Care Center"),
    # Industrial
    (re.compile(r"\bwarehouse\b|\bdistribution\s+(center|facility)\b|\blogistics\b|\bfulfillment\b", re.I),
     "Warehouse / Distribution Center"),
    (re.compile(r"\bmanufactur\b|\bassembly\b|\bfabricat\b|\bproduction\s+facility\b", re.I),
     "Light Manufacturing / Assembly"),
    (re.compile(r"\bself.storage\b|\bmini.storage\b|\bstorage\s+(facility|unit)\b|\bcubesmart\b|\bpublic\s+storage\b|\blife\s+storage\b|\bextra\s+space\b", re.I),
     "Mini-Storage / Self-Storage"),
    # Concrete / batch plant
    (re.compile(r"\bconcrete\s+(batch|plant|mix)\b|\basphalt\s+(plant|batch)\b|\bready.mix\b", re.I),
     "Concrete / Asphalt Batch Plant"),
    # Professional office
    (re.compile(r"\boffice\s+(park|building|complex|center|campus)\b|\bprofessional\s+office\b|\blaw\s+office\b|\blaw\s+firm\b|\baccounting\b|\binsurance\s+office\b", re.I),
     "Professional Office (Law, Finance, Insurance)"),
    # Bank
    (re.compile(r"\bbank\b|\bcredit\s+union\b|\bfinancial\s+(center|institution)\b|\bchase\b|\bwells\s+fargo\b|\bbank\s+of\s+america\b", re.I),
     "Bank / Financial Institution"),
    # Church / religious
    (re.compile(r"\bchurch\b|\bchapel\b|\bworship\b|\bcongregation\b|\bministry\b|\bmosque\b|\btemple\b|\bsynagogue\b", re.I),
     "Religious Institution / Church"),
    # Residential
    (re.compile(r"\bapartment\b|\bmultifamily\b|\bmulti.family\b|\bresidential\s+(development|community|complex)\b", re.I),
     "Garden Apartment Complex"),
    (re.compile(r"\btownhome\b|\btownhouse\b|\brow\s+house\b|\bpatio\s+home\b", re.I),
     "Urban Row House / Townhome"),
    (re.compile(r"\bsingle.family\b|\bsingle\s+family\b|\bresidential\s+lot\b|\bsfr\b", re.I),
     "Single-Family Residence"),
]


def detect_applicant_use(title: str, description: str) -> tuple[Optional[str], Optional[str]]:
    """
    Try to identify the specific use from the applicant name or description.
    Returns (use_name, confidence) — confidence is 'HIGH' or 'MEDIUM'.
    use_name is None if no match found.
    """
    # Search applicant names (appears between the CD tag and the semicolon / address)
    applicant_block = ""
    m = re.search(r'\(CD[^)]*\)\s+(.+?);\s*\d+', title + " " + description, re.I)
    if m:
        applicant_block = m.group(1)

    full_text = (applicant_block + " " + title + " " + description)

    for pattern, use_name in _APPLICANT_PATTERNS:
        if pattern.search(full_text):
            # Higher confidence if matched in the applicant block specifically
            confidence = "HIGH" if applicant_block and pattern.search(applicant_block) else "MEDIUM"
            return use_name, confidence

    return None, None


# ---------------------------------------------------------------------------
# Approval type detection
# ---------------------------------------------------------------------------

def detect_approval_type(to_code: str, to_desc: str) -> dict:
    """
    Determine whether the proposed use is by-right or requires additional authorization.
    Returns a dict with type, label, and explanation.
    """
    code_up = to_code.upper()
    desc_up = (to_desc or "").upper()

    # Specific Use Authorization (most common conditional path in FW)
    if "/SU" in code_up or "SPECIFIC USE" in desc_up or "/SU" in desc_up:
        return {
            "type":        "specific_use",
            "label":       "Specific Use Authorization Required",
            "short_label": "Specific Use",
            "color":       "yellow",
            "explanation": (
                "This rezoning includes a Specific Use (SU) designation, meaning the listed use "
                "is NOT allowed by right — it requires individual council authorization and can be "
                "revoked if conditions are violated. The fiscal impact estimate applies only to the "
                "stated use; if the SU is not granted or later revoked, the land reverts to base "
                "zone permitted uses."
            ),
        }

    # Conditional Use Permit
    if "CUP" in desc_up or "CONDITIONAL USE" in desc_up:
        return {
            "type":        "conditional",
            "label":       "Conditional Use Permit Required",
            "short_label": "Conditional Use",
            "color":       "yellow",
            "explanation": (
                "A Conditional Use Permit (CUP) is required for this use. The council may attach "
                "conditions (hours, screening, buffers) that could affect the economic viability "
                "and fiscal projections shown here."
            ),
        }

    # Planned Development — uses defined by the PD ordinance
    if "PD" in code_up:
        return {
            "type":        "planned_development",
            "label":       "Planned Development — Uses Defined by Ordinance",
            "short_label": "Planned Development",
            "color":       "blue",
            "explanation": (
                "This is a Planned Development (PD) zone. The allowed uses are defined specifically "
                "in the PD ordinance rather than a standard zone category. The fiscal impact is "
                "estimated based on the uses listed in the agenda description. Any use not listed "
                "would require a separate PD amendment."
            ),
        }

    # Standard by-right
    return {
        "type":        "by_right",
        "label":       "By Right — No Additional Authorization Needed",
        "short_label": "By Right",
        "color":       "green",
        "explanation": (
            "The proposed zone allows these uses by right — no special permits or council "
            "approval beyond this rezoning are required. Any property owner can develop to "
            "any listed use once the rezoning is approved."
        ),
    }


# ---------------------------------------------------------------------------
# Fiscal computation for a single use type
# ---------------------------------------------------------------------------

def compute_use_fiscal(
    use_name: str,
    acreage: float,
    zone_code: str,
) -> Optional[dict]:
    """
    Compute annual and 40-year fiscal impact for one use type on *acreage* acres.
    Returns None if the use is not in USES.
    """
    use = USES.get(use_name)
    if not use:
        return None

    # Land value (look up by base zone code, strip suffixes like /SU, /HC)
    base_code = zone_code.split("/")[0].upper().rstrip("0123456789").strip("-")
    # Try increasingly shorter matches
    land_val_per_acre = (
        LAND_VALUE_PER_ACRE.get(zone_code.upper()) or
        LAND_VALUE_PER_ACRE.get(base_code) or
        LAND_VALUE_PER_ACRE.get(base_code[:1]) or
        200_000
    )

    building_sqft = use["building_sqft_per_acre"] * acreage
    improvement_val = building_sqft * use["improvement_value_sqft"]
    land_val = land_val_per_acre * acreage
    total_assessed = improvement_val + land_val

    annual_prop_tax = total_assessed / 100 * FW_PROP_TAX_RATE
    annual_sales_tax = (
        building_sqft * use["annual_sales_sqft"] * FW_SALES_TAX_RATE
        if use["sales_tax_generating"] else 0
    )
    annual_gross_revenue = annual_prop_tax + annual_sales_tax
    annual_service_cost  = use["service_cost_per_acre"] * acreage
    annual_net           = annual_gross_revenue - annual_service_cost
    jobs                 = round(use["jobs_per_acre"] * acreage)

    # 40-year NPV of net stream
    npv_40yr = round(sum(
        annual_net * (1 + GROWTH_RATE) ** yr / (1 + DISCOUNT_RATE) ** yr
        for yr in range(1, ANALYSIS_YEARS + 1)
    ))

    return {
        "use_name":              use_name,
        "use_category":          use["use_category"],
        "sales_tax_generating":  use["sales_tax_generating"],
        "texas_tax_note":        use["texas_tax_note"],
        "annual_property_tax":   round(annual_prop_tax),
        "annual_sales_tax":      round(annual_sales_tax),
        "annual_gross_revenue":  round(annual_gross_revenue),
        "annual_service_cost":   round(annual_service_cost),
        "annual_net":            round(annual_net),
        "npv_40yr":              npv_40yr,
        "jobs_estimate":         jobs,
        "acreage":               acreage,
    }


def get_by_right_scenarios(
    to_code: str,
    acreage: float,
) -> list[dict]:
    """
    Return computed fiscal impacts for every by-right use in the target zone,
    sorted best-to-worst annual net.
    """
    # Normalize code: strip overlay suffixes (e.g. /HSE, /HC, /SSO, /DD)
    base = to_code.split("/")[0].upper()

    # Try exact, then strip trailing digits/dashes
    use_names = (
        BY_RIGHT_USES.get(to_code.upper()) or
        BY_RIGHT_USES.get(base) or
        BY_RIGHT_USES.get(re.sub(r"[-\d]+$", "", base))
    )

    if not use_names:
        return []

    results = []
    for name in use_names:
        r = compute_use_fiscal(name, acreage, to_code)
        if r:
            results.append(r)

    return sorted(results, key=lambda x: x["annual_net"], reverse=True)
