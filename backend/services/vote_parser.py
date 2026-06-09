"""
Fort Worth City Council vote parser.

Fort Worth minutes use the format:
  "Council Member Nettles made a motion, seconded by Council Member Crain,
   that [item] be approved. Motion passed 10-0, Mayor Pro tem Bivens absent."

Districts appear inline in case refs: SP-23-009 (CD 8), ZC-23-127 (CD 10),
M&C 23-1036 (CD 2 and CD 9), or (ALL).
"""

import re
from typing import Optional

# ── Council member → district lookup (updated through 2026) ───────────────────
# Source: Fort Worth City Charter; updated periodically via minutes attendance
_MEMBER_DISTRICT: dict[str, str] = {
    "mattie parker": "Mayor",
    "parker": "Mayor",
    "gyna bivens": "5",
    "bivens": "5",
    "carlos flores": "2",
    "flores": "2",
    "michael crain": "3",
    "crain": "3",
    "charlie lauersdorf": "4",
    "lauersdorf": "4",
    "jared williams": "6",
    "williams": "6",
    "macy hill": "7",
    "hill": "7",
    "chris nettles": "8",
    "nettles": "8",
    "elizabeth beck": "9",
    "beck": "9",
    "alan blaylock": "10",
    "blaylock": "10",
    "jeanette martinez": "11",
    "martinez": "11",
    # Older members (2021-2023)
    "dennis shingleton": "7",
    "shingleton": "7",
    "kelly allen gray": "3",
    "allen gray": "3",
    "leonard firestone": "7",
    "firestone": "7",
    "brian byrd": "6",
    "byrd": "6",
    "cary moon": "4",
    "moon": "4",
    "ann zadeh": "9",
    "zadeh": "9",
    "frank moss": "8",
    "moss": "8",
}


# ── Regexes ───────────────────────────────────────────────────────────────────

# Case/M&C reference with optional district annotation
_CASE_REF_RE = re.compile(
    r'\b(?:'
    r'(?:M&?C|M\.C\.)\s+(?:[A-Z]-\d{4,6}|\d{2}-\d{4,6})|'
    r'(?:ZC|SP|AX|FP|PP|RP|PD|CUP)-\d{2}-\d{3,6}'
    r')'
    r'(?:\s*\((?:Future\s+)?(?:CD\s*\d+(?:\s+and\s+CD\s*\d+)*|ALL)\))?',
    re.IGNORECASE,
)

# District annotation: "(CD 8)", "(CD 2 and CD 9)", "(ALL)", "(Future CD 10)"
_CD_RE = re.compile(
    r'\((?:Future\s+)?(?:(ALL)|(CD\s*\d+(?:\s+and\s+CD\s*\d+)*))\)',
    re.IGNORECASE,
)

# Attendance header: "Council Member Carlos Flores, District 2"
_ATTENDANCE_RE = re.compile(
    r'(?:Council\s+Member|Mayor(?:\s+Pro\s+[Tt]em)?)\s+'
    r'((?:[A-Z][a-z]+\s+){1,4}(?:[A-Z][a-z]+))'
    r'(?:,\s+District\s+(\d+))?',
)

# Motion result: "Motion passed 10-0, Mayor Pro tem Bivens absent."
# Also: "Motion passed 9-1, Council Member Hill voting no, Bivens absent."
_MOTION_RESULT_RE = re.compile(
    r'Motion\s+(?:passed|carried|failed|approved|denied)\s+'
    r'(\d+)\s*[-–]\s*(\d+)'
    r'([^.]*\.?)',
    re.IGNORECASE,
)

# Voting-no pattern within the tail of a motion result
_VOTING_NO_RE = re.compile(
    r'(?:Council\s+Member\s+|CM\s+)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'
    r'voting\s+(?:no|against|nay)',
    re.IGNORECASE,
)

# Absent pattern within motion result tail
_ABSENT_RE = re.compile(
    r'(?:Council\s+Member\s+|CM\s+|Mayor(?:\s+Pro\s+[Tt]em)?\s+)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+absent',
    re.IGNORECASE,
)

# Motion block delimiter
_MOTION_LABEL_RE = re.compile(r'^\s*Motion\s*:\s*', re.IGNORECASE)


def _lookup_district(name: str) -> str:
    """Resolve a last-name or full-name to a district string."""
    key = name.strip().lower()
    if key in _MEMBER_DISTRICT:
        return _MEMBER_DISTRICT[key]
    # Try last name only
    last = key.split()[-1] if key.split() else key
    return _MEMBER_DISTRICT.get(last, "")


def parse_attendance(text: str) -> dict[str, str]:
    """
    Extract {member_name: district} from the attendance header block.
    Also builds absent set from the text.
    Returns {name_lower: district_str, ...}
    """
    mapping: dict[str, str] = {}
    lines = text.split("\n")
    in_section = False
    for line in lines[:60]:  # attendance is near the top
        stripped = line.strip()
        if re.match(r'^(?:Present|Absent)\s*:', stripped, re.IGNORECASE):
            in_section = True
        if not in_section:
            continue
        m = _ATTENDANCE_RE.search(stripped)
        if m:
            full_name = m.group(1).strip()
            district = m.group(2) or ""
            if not district:
                if "mayor" in stripped.lower() and "pro tem" not in stripped.lower():
                    district = "Mayor"
                elif "mayor pro tem" in stripped.lower():
                    district = "5"  # In Fort Worth, Pro Tem is typically District 5 (Bivens)
            mapping[full_name.lower()] = district
            # Also index by last name
            last = full_name.split()[-1].lower()
            if last not in mapping:
                mapping[last] = district
        # Stop after a blank line following the section start
        if in_section and not stripped and len(mapping) > 3:
            in_section = False
    return mapping


def extract_districts_from_ref(text: str) -> list[str]:
    """
    Pull district numbers from a case reference string like
    'M&C 23-1036 (CD 2 and CD 9)' → ['2', '9']
    'ZC-23-127 (CD 10)' → ['10']
    'M&C 23-1040 (ALL)' → ['ALL']
    """
    m = _CD_RE.search(text)
    if not m:
        return []
    if m.group(1):  # ALL
        return ["ALL"]
    # Parse "CD 2 and CD 9"
    return re.findall(r'\d+', m.group(2))


def _parse_motion_block(
    motion_text: str,
    member_map: dict[str, str],
) -> Optional[dict]:
    """
    Parse a single motion block and return a vote summary dict or None.

    motion_text: everything after 'Motion:' up to next 'Motion:' or item ref
    """
    result_m = _MOTION_RESULT_RE.search(motion_text)
    if not result_m:
        # Check for simple "Approved." without a tally — treat as 10-0 default
        if re.search(r'\bApproved\b', motion_text, re.IGNORECASE):
            return {
                "ayes": None, "nays": 0, "abstain": 0, "absent": None,
                "passed": True,
                "by_member": [],
                "raw": motion_text.strip()[:200],
            }
        return None

    ayes_count = int(result_m.group(1))
    nays_count = int(result_m.group(2))
    tail = result_m.group(3) or ""
    passed = ayes_count > nays_count

    # Detect named "voting no" members
    voting_no = [m.group(1) for m in _VOTING_NO_RE.finditer(tail)]
    absent_names = [m.group(1) for m in _ABSENT_RE.finditer(tail)]

    by_member: list[dict] = []

    # Build per-member records: first add absent members
    for name in absent_names:
        district = member_map.get(name.lower(), "") or _lookup_district(name)
        by_member.append({"name": name, "district": district, "vote": "ABSENT"})

    # Add explicit nay voters
    for name in voting_no:
        district = member_map.get(name.lower(), "") or _lookup_district(name)
        by_member.append({"name": name, "district": district, "vote": "NAY"})

    # Infer the movers as AYE voters if named
    mover_m = re.search(
        r'(?:Council\s+Member|CM)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+made\s+a\s+motion',
        motion_text,
        re.IGNORECASE,
    )
    seconder_m = re.search(
        r'seconded\s+by\s+(?:Council\s+Member|CM)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        motion_text,
        re.IGNORECASE,
    )
    named_no = {n.lower() for n in voting_no}
    named_absent = {n.lower() for n in absent_names}

    for name_match in [mover_m, seconder_m]:
        if not name_match:
            continue
        name = name_match.group(1).strip()
        if name.lower() in named_no or name.lower() in named_absent:
            continue
        district = member_map.get(name.lower(), "") or _lookup_district(name)
        # Avoid duplicates
        if not any(v["name"].lower() == name.lower() for v in by_member):
            by_member.append({"name": name, "district": district, "vote": "AYE"})

    return {
        "ayes": ayes_count,
        "nays": nays_count,
        "abstain": 0,
        "absent": len(absent_names),
        "passed": passed,
        "by_member": by_member,
        "raw": motion_text.strip()[:300],
    }


def associate_votes_to_items(minutes_text: str) -> dict[str, dict]:
    """
    Scan Fort Worth minutes and associate vote summaries with each case reference.

    Returns::
        {
            "ZC-23-127": {"ayes": 10, "nays": 0, ..., "districts": ["10"], "by_member": [...]},
            "M&C 23-1036": {...},
        }
    """
    # Build member→district map from attendance header
    member_map = parse_attendance(minutes_text)

    item_votes: dict[str, dict] = {}
    current_ref: Optional[str] = None
    current_districts: list[str] = []

    lines = minutes_text.split("\n")
    i = 0
    motion_buffer: list[str] = []
    in_motion = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect case reference line
        case_m = _CASE_REF_RE.search(stripped)
        if case_m:
            # Flush any pending motion
            if in_motion and motion_buffer and current_ref:
                block_text = " ".join(motion_buffer)
                result = _parse_motion_block(block_text, member_map)
                if result:
                    result["districts"] = current_districts
                    item_votes[current_ref] = result
            motion_buffer = []
            in_motion = False

            raw_ref = case_m.group(0)
            # Normalize ref: strip the (CD X) annotation for the key
            key = _CASE_REF_RE.search(raw_ref)
            ref_key = (key.group(0) if key else raw_ref).upper().replace("M.C.", "M&C")
            # Strip trailing (CD...) from key
            ref_key = re.sub(r'\s*\([^)]*\)\s*$', '', ref_key).strip()

            current_ref = ref_key
            current_districts = extract_districts_from_ref(stripped)
            i += 1
            continue

        # Detect "Motion:" label
        if _MOTION_LABEL_RE.match(stripped) or stripped.lower().startswith("motion:"):
            # Flush previous motion if any
            if in_motion and motion_buffer and current_ref:
                block_text = " ".join(motion_buffer)
                result = _parse_motion_block(block_text, member_map)
                if result:
                    result["districts"] = current_districts
                    item_votes[current_ref] = result
            motion_buffer = [re.sub(r'^Motion\s*:\s*', '', stripped, flags=re.IGNORECASE)]
            in_motion = True
            i += 1
            continue

        # Accumulate motion text
        if in_motion:
            if not stripped:
                # Blank line ends the motion block
                if motion_buffer and current_ref:
                    block_text = " ".join(motion_buffer)
                    result = _parse_motion_block(block_text, member_map)
                    if result:
                        result["districts"] = current_districts
                        item_votes[current_ref] = result
                motion_buffer = []
                in_motion = False
            else:
                motion_buffer.append(stripped)

        i += 1

    # Flush any trailing motion
    if in_motion and motion_buffer and current_ref:
        block_text = " ".join(motion_buffer)
        result = _parse_motion_block(block_text, member_map)
        if result:
            result["districts"] = current_districts
            item_votes[current_ref] = result

    return item_votes


def summarize_votes(vote_result: dict) -> dict:
    """
    Normalize a vote result dict (already in summary form from associate_votes_to_items)
    to the standard schema expected by the database.
    """
    if not vote_result:
        return {}
    return {
        "ayes": vote_result.get("ayes"),
        "nays": vote_result.get("nays", 0),
        "abstain": vote_result.get("abstain", 0),
        "absent": vote_result.get("absent"),
        "passed": vote_result.get("passed", True),
        "districts": vote_result.get("districts", []),
        "by_member": vote_result.get("by_member", []),
    }
