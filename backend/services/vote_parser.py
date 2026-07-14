"""
Fort Worth City Council vote parser.

pdfplumber (used on the server) produces clean line-by-line text within each page,
with double-newlines only at page breaks.  The parser walks line by line.

Non-unanimous vote format:
  "Motion passed 9-2, Mayor Parker, Mayor Pro tem Flores, and Council Members
   Crain, Peoples, Hall, Nettles, Beck, Blaylock, and Martinez voted in support.
   Council Members Lauersdorf and Hill voted in opposition."

Unanimous vote format (11-0):  reconstruct all-present members as AYE.

District codes appear inline: SP-23-009 (CD 8), ZC-23-127 (CD 10), (ALL).
"""

import re
from typing import Optional

# ── Council member → district lookup ─────────────────────────────────────────
_MEMBER_DISTRICT: dict[str, str] = {
    # Current (2025–)
    "mattie parker": "Mayor",  "parker": "Mayor",
    "carlos flores": "2",      "flores": "2",
    "michael crain": "3",      "crain": "3",      "michael d. crain": "3",
    "charlie lauersdorf": "4", "lauersdorf": "4",
    "deborah peoples": "5",    "peoples": "5",
    "mia hall": "6",           "hall": "6",
    "dr. mia hall": "6",       "dr mia hall": "6",
    "macy hill": "7",          "hill": "7",
    "chris nettles": "8",      "nettles": "8",
    "elizabeth beck": "9",     "beck": "9",
    "alan blaylock": "10",     "blaylock": "10",
    "jeanette martinez": "11", "martinez": "11",
    # Prior members (2021–2024)
    "gyna bivens": "5",        "bivens": "5",
    "jared williams": "6",     "williams": "6",
    "dennis shingleton": "7",  "shingleton": "7",
    "leonard firestone": "7",  "firestone": "7",
    "kelly allen gray": "3",   "allen gray": "3",
    "brian byrd": "6",         "byrd": "6",
    "cary moon": "4",          "moon": "4",
    "ann zadeh": "9",          "zadeh": "9",
    "frank moss": "8",         "moss": "8",
}

_CURRENT_ROSTER = [
    ("Mattie Parker",      "Mayor"),
    ("Carlos Flores",      "2"),
    ("Michael Crain",      "3"),
    ("Charlie Lauersdorf", "4"),
    ("Deborah Peoples",    "5"),
    ("Mia Hall",           "6"),
    ("Macy Hill",          "7"),
    ("Chris Nettles",      "8"),
    ("Elizabeth Beck",     "9"),
    ("Alan Blaylock",      "10"),
    ("Jeanette Martinez",  "11"),
]

# ── Regexes ───────────────────────────────────────────────────────────────────

# Case reference — M&C, ZC-, SP-, or bare Legistar item IDs (25-XXXX)
_CASE_REF_RE = re.compile(
    r'\b(?:'
    r'(?:M&?C|M\.C\.)\s+(?:[A-Z]-\d{4,6}|\d{2}-\d{4,6})|'
    r'(?:ZC|SP|AX|FP|PP|RP|PD|CUP)-\d{2}-\d{3,6}|'
    r'(?:Item\s+)?(\d{2}-\d{4,6})'
    r')'
    r'(?:\s*\((?:Future\s+)?(?:CD\s*\d+(?:\s+and\s+CD\s*\d+)*|ALL)\))?',
    re.IGNORECASE,
)

_CD_RE = re.compile(
    r'\((?:Future\s+)?(?:(ALL)|(CD\s*\d+(?:\s+and\s+CD\s*\d+)*))\)',
    re.IGNORECASE,
)

_ATTENDANCE_RE = re.compile(
    r'(?:Council\s+Member|Mayor(?:\s+Pro\s+[Tt]em)?)\s+'
    r'((?:Dr\.\s+)?(?:[A-Z][a-zA-Z.]+\s+){1,4}(?:[A-Z][a-zA-Z.]+))'
    r'(?:,\s+District\s+(\d+))?',
)

# Motion tally: "Motion passed 10-0" or "Motion passed 9-2"
_TALLY_RE = re.compile(
    r'Motion\s+(?:passed|carried|failed|approved|denied)\s+(\d+)\s*[-–]\s*(\d+)',
    re.IGNORECASE,
)

# Named voters in non-unanimous results
_SUPPORT_RE = re.compile(
    r'([A-Z][^.]{5,300}?)\s+voted\s+in\s+(?:support|favor)',
    re.IGNORECASE | re.DOTALL,
)
_OPPOSITION_RE = re.compile(
    r'([A-Z][^.]{3,300}?)\s+voted\s+in\s+opposition',
    re.IGNORECASE | re.DOTALL,
)
# Alternate Fort Worth phrasing for a lone/small dissent that never lists an
# AYE-side name list at all, e.g. "Motion passed 7-1, Council Member Blaylock
# casting the dissenting vote and Council Member Beck absent."
_DISSENT_RE = re.compile(
    r'([A-Z][^.]{3,300}?)\s+casting\s+the\s+dissenting\s+votes?',
    re.IGNORECASE | re.DOTALL,
)
_ABSENT_RE = re.compile(
    r'(?:Council\s+Member\s+|Mayor\s+(?:Pro\s+[Tt]em\s+)?)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+absent',
    re.IGNORECASE,
)

_NAME_SEP_RE = re.compile(r',\s*|\s+and\s+', re.IGNORECASE)
_PREFIX_RE = re.compile(
    r'\b(?:Mayor\s+Pro\s+[Tt]em|Mayor|Council\s+Members?|CM|Dr\.)\s+',
    re.IGNORECASE,
)

# Lines that signal a new major section — reset case ref context
_SECTION_HEADER_RE = re.compile(
    r'^\s*(?:CONSENT\s+AGENDA|PUBLIC\s+HEARING|ZONING\s+HEARING|'
    r'PRESENTATIONS?\s+BY|EXECUTIVE\s+SESSION|ADJOURN|'
    r'CITY\s+COUNCIL\s+MEETING|Page\s+\d+\s+of\s+\d+)',
    re.IGNORECASE,
)

# Noise lines to skip (page footers, page headers, blank section lines)
_NOISE_RE = re.compile(
    r'^(?:City\s+of\s+Fort\s+Worth\s+Page\s+\d+|Printed\s+on\s+\d|'
    r'Page\s+\d+\s+of\s+\d+)',
    re.IGNORECASE,
)


def _lookup_district(name: str, member_map: dict = None) -> str:
    key = name.strip().lower()
    if member_map:
        if key in member_map:
            return member_map[key]
        last = key.split()[-1]
        if last in member_map:
            return member_map[last]
    if key in _MEMBER_DISTRICT:
        return _MEMBER_DISTRICT[key]
    last = key.split()[-1] if key.split() else key
    return _MEMBER_DISTRICT.get(last, "")


def _normalize_name(name: str) -> str:
    """Strip middle initials and resolve to canonical member name by last name."""
    # Strip middle initials like "M." in "Elizabeth M. Beck"
    stripped = re.sub(r'\b[A-Z]\.\s+', '', name).strip()
    lower = stripped.lower()
    # Look up canonical full name by last name
    last = lower.split()[-1] if lower.split() else lower
    full = next(
        (k for k in _MEMBER_DISTRICT if ' ' in k and k.split()[-1] == last),
        None,
    )
    return full.title() if full else stripped


def _extract_names_from_list(raw: str) -> list[str]:
    """Parse 'Mayor Parker, Mayor Pro tem Flores, and Council Members Crain, Hill' → names."""
    cleaned = _PREFIX_RE.sub('', raw).strip()
    parts = _NAME_SEP_RE.split(cleaned)
    names = []
    for p in parts:
        p = p.strip().rstrip('.,;')
        p = re.sub(r'^\s*and\s+', '', p, flags=re.IGNORECASE).strip()
        p = _PREFIX_RE.sub('', p).strip()
        if len(p) >= 2 and p.lower() not in ('', 'the', 'a', 'an'):
            names.append(_normalize_name(p))
    return names


def parse_attendance(text: str) -> dict[str, str]:
    """Extract {name_lower: district} from the attendance header."""
    mapping: dict[str, str] = {}
    lines = text.split("\n")
    in_section = False
    for line in lines[:100]:
        stripped = line.strip()
        if re.match(r'^(?:Present|Absent)\s*:?\s*$', stripped, re.IGNORECASE):
            in_section = True
            continue
        if not in_section:
            continue
        if re.match(r'^(?:Staff|City\s+Manager|City\s+Attorney|CALL)', stripped, re.IGNORECASE):
            break
        m = _ATTENDANCE_RE.search(stripped)
        if m:
            full_name = m.group(1).strip().rstrip(',.')
            district = m.group(2) or ""
            if not district:
                if re.search(r'mayor\s+pro\s+tem', stripped, re.IGNORECASE):
                    district = _MEMBER_DISTRICT.get(full_name.split()[-1].lower(), "")
                elif re.match(r'^\s*mayor\b', stripped, re.IGNORECASE):
                    district = "Mayor"
            key = full_name.lower()
            last = full_name.split()[-1].lower()
            mapping[key] = district
            if last not in mapping:
                mapping[last] = district
    return mapping


def extract_districts_from_ref(text: str) -> list[str]:
    m = _CD_RE.search(text)
    if not m:
        return []
    if m.group(1):
        return ["ALL"]
    return re.findall(r'\d+', m.group(2))


def _build_unanimous_members(
    absent_names: list[str], member_map: dict, dissent_names: list[str] = None,
) -> list[dict]:
    """
    Build the full by-member vote list when the minutes never spell out an
    AYE-side name list — either a true unanimous vote (dissent_names empty)
    or Fort Worth's "Council Member X casting the dissenting vote" phrasing,
    where only the dissenter(s) and absences are named and everyone else is
    implicitly AYE.
    """
    dissent_names = dissent_names or []
    absent_lower  = {n.lower() for n in absent_names}
    absent_last   = {n.split()[-1].lower() for n in absent_names}
    dissent_lower = {n.lower() for n in dissent_names}
    dissent_last  = {n.split()[-1].lower() for n in dissent_names}

    def _vote_for(name_lower: str, last: str) -> str:
        if name_lower in dissent_lower or last in dissent_last:
            return "NAY"
        if name_lower in absent_lower or last in absent_last:
            return "ABSENT"
        return "AYE"

    by_member = []
    if member_map:
        full_entries = {k: v for k, v in member_map.items() if ' ' in k}
        roster = full_entries if full_entries else member_map
        for name, district in roster.items():
            by_member.append({
                "name": name.title(),
                "district": district,
                "vote": _vote_for(name, name.split()[-1]),
            })
    else:
        for full_name, district in _CURRENT_ROSTER:
            last = full_name.split()[-1].lower()
            by_member.append({
                "name": full_name,
                "district": district,
                "vote": _vote_for(full_name.lower(), last),
            })
    return by_member


def _parse_motion_text(motion_text: str, member_map: dict) -> Optional[dict]:
    """Parse accumulated motion text into a vote summary dict."""
    tally_m = _TALLY_RE.search(motion_text)

    if not tally_m:
        if re.search(r'\bApproved\b\.?', motion_text, re.IGNORECASE):
            return {"ayes": None, "nays": 0, "abstain": 0, "absent": None,
                    "passed": True, "by_member": [], "raw": motion_text.strip()[:200]}
        return None

    ayes_count = int(tally_m.group(1))
    nays_count = int(tally_m.group(2))
    passed = ayes_count > nays_count
    tail = motion_text[tally_m.end():]

    absent_names = [m.group(1) for m in _ABSENT_RE.finditer(tail)]
    by_member: list[dict] = []

    if nays_count == 0:
        by_member = _build_unanimous_members(absent_names, member_map)
    else:
        support_m    = _SUPPORT_RE.search(tail)
        opposition_m = _OPPOSITION_RE.search(tail)
        dissent_m    = _DISSENT_RE.search(tail) if not opposition_m else None

        if not support_m and not opposition_m and dissent_m:
            # "Council Member X casting the dissenting vote" — the AYE side
            # is never named, so infer it: everyone present who isn't the
            # named dissenter(s) or absent voted AYE.
            dissent_names = _extract_names_from_list(dissent_m.group(1))
            by_member = _build_unanimous_members(absent_names, member_map, dissent_names)
            return {
                "ayes": ayes_count,
                "nays": nays_count,
                "abstain": 0,
                "absent": len(absent_names),
                "passed": passed,
                "by_member": by_member,
                "raw": motion_text.strip()[:300],
            }

        if support_m:
            for name in _extract_names_from_list(support_m.group(1)):
                by_member.append({
                    "name": name,
                    "district": _lookup_district(name, member_map),
                    "vote": "AYE",
                })
        if opposition_m:
            for name in _extract_names_from_list(opposition_m.group(1)):
                by_member.append({
                    "name": name,
                    "district": _lookup_district(name, member_map),
                    "vote": "NAY",
                })
        for name in absent_names:
            if not any(v["name"].lower() == name.lower() for v in by_member):
                by_member.append({
                    "name": name,
                    "district": _lookup_district(name, member_map),
                    "vote": "ABSENT",
                })

    return {
        "ayes": ayes_count,
        "nays": nays_count,
        "abstain": 0,
        "absent": len(absent_names),
        "passed": passed,
        "by_member": by_member,
        "raw": motion_text.strip()[:300],
    }


def _store_result(item_votes, current_ref, current_districts, result):
    """Store a vote result, preferring non-zero-nay results (more specific)."""
    if not result or not current_ref:
        return
    result["districts"] = current_districts
    existing = item_votes.get(current_ref)
    if not existing or (result.get("nays", 0) > 0 and existing.get("nays", 0) == 0):
        item_votes[current_ref] = result


def associate_votes_to_items(minutes_text: str) -> dict[str, dict]:
    """
    Walk the minutes line-by-line (pdfplumber produces one line per text row).
    Accumulate motion text from "Motion:" until a blank line or new section,
    then parse and associate with the most recent case reference.
    """
    member_map = parse_attendance(minutes_text)
    item_votes: dict[str, dict] = {}

    current_ref: Optional[str] = None
    current_districts: list[str] = []
    motion_lines: list[str] = []
    in_motion: bool = False

    # pdfplumber joins pages with \n\n but lines within a page with \n
    # Normalize: treat \n\n as a separator but process line by line
    lines = minutes_text.replace('\n\n', '\n').split('\n')

    def flush_motion():
        nonlocal in_motion, motion_lines
        if motion_lines and current_ref:
            text = ' '.join(motion_lines)
            result = _parse_motion_text(text, member_map)
            _store_result(item_votes, current_ref, current_districts, result)
        motion_lines = []
        in_motion = False

    for raw_line in lines:
        line = raw_line.strip()

        # Skip noise / page footers
        if _NOISE_RE.match(line):
            continue

        # Blank line ends a motion block
        if not line:
            if in_motion:
                flush_motion()
            continue

        # Section headers reset context (prevents speaker-comment refs stealing motions)
        if _SECTION_HEADER_RE.match(line):
            if in_motion:
                flush_motion()
            # Don't reset current_ref on these — next item may still belong here
            continue

        # "Motion:" at start of line
        motion_start = re.match(r'^Motion\s*:\s*(.*)', line, re.IGNORECASE)
        if motion_start:
            if in_motion:
                flush_motion()
            in_motion = True
            rest = motion_start.group(1).strip()
            if rest:
                motion_lines = [rest]
            else:
                motion_lines = []
            continue

        # Accumulate motion continuation
        if in_motion:
            # Stop if we hit a new item reference line at the start of the line
            is_new_item = (
                re.match(r'^\d+\.\s+', line)          # numbered item
                or re.match(r'^[A-Z]\.\s+', line)      # lettered section
                or re.match(r'^(?:M&?C|ZC-|SP-|AX-|FP-)\s*', line, re.IGNORECASE)
                or re.match(r'^ZONING\s+HEARING', line, re.IGNORECASE)
                or re.match(r'^PUBLIC\s+HEARING', line, re.IGNORECASE)
            )
            if is_new_item and _TALLY_RE.search(' '.join(motion_lines)):
                flush_motion()
                # Fall through to process this line as a new item
            elif is_new_item:
                flush_motion()
                # Fall through
            else:
                motion_lines.append(line)
                continue

        # Case reference detection — only when line looks like an item heading
        case_m = _CASE_REF_RE.search(line)
        if case_m:
            ref_pos = case_m.start()
            # Accept if near start of line or line starts with number/letter prefix
            pre = line[:ref_pos].strip()
            is_item_line = (
                ref_pos < 40
                or re.match(r'^\d+\.?\s*$', pre)
                or re.match(r'^[A-Z]-?\d*\.?\s*$', pre)
                or not pre
            )
            if is_item_line:
                raw_ref = case_m.group(0)
                ref_key = re.sub(r'\s*\([^)]*\)\s*$', '', raw_ref).strip().upper().replace("M.C.", "M&C")
                ref_key = re.sub(r'^ITEM\s+', '', ref_key).strip()
                ref_key = re.sub(r'\s+', ' ', ref_key)
                current_ref = ref_key
                current_districts = extract_districts_from_ref(line)

    # Flush any trailing motion
    if in_motion:
        flush_motion()

    return item_votes


def summarize_votes(vote_result: dict) -> dict:
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
