"""
Fort Worth City Council vote parser.

Non-unanimous format (e.g. 9-2):
  "Motion passed 9-2, Mayor Parker, Mayor Pro tem Flores, and Council Members
   Crain, Peoples, Hall, Nettles, Beck, Blaylock, and Martinez voted in support.
   Council Members Lauersdorf and Hill voted in opposition."

Unanimous format (11-0 or 10-0 with 1 absent):
  "Motion passed 11-0."  — reconstruct all present members as AYE.

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
    r'(?:M&?C|M\.C\.)\s+(?:[A-Z]-\d{4,6}|\d{2}-\d{4,6})|'   # M&C 25-0557
    r'(?:ZC|SP|AX|FP|PP|RP|PD|CUP)-\d{2}-\d{3,6}|'           # ZC-25-078
    r'(?:Item\s+)?(\d{2}-\d{4,6})'                             # 25-5257 or Item 25-5257
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

_TALLY_RE = re.compile(
    r'Motion\s+(?:passed|carried|failed|approved|denied)\s+(\d+)\s*[-–]\s*(\d+)',
    re.IGNORECASE,
)

# Named voters in non-unanimous results
_SUPPORT_RE = re.compile(
    r'([A-Z][^.]{5,200}?)\s+voted\s+in\s+(?:support|favor)',
    re.IGNORECASE | re.DOTALL,
)
_OPPOSITION_RE = re.compile(
    r'([A-Z][^.]{3,200}?)\s+voted\s+in\s+opposition',
    re.IGNORECASE | re.DOTALL,
)
_VOTING_NO_RE = re.compile(
    r'(?:Council\s+Member\s+|Mayor\s+(?:Pro\s+[Tt]em\s+)?)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+voting\s+(?:no|against|nay)',
    re.IGNORECASE,
)
_ABSENT_RE = re.compile(
    r'(?:Council\s+Member\s+|Mayor\s+(?:Pro\s+[Tt]em\s+)?)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+absent',
    re.IGNORECASE,
)

_MOTION_LABEL_RE = re.compile(r'^\s*Motion\s*:\s*$', re.IGNORECASE)

_NAME_SEP_RE = re.compile(r',\s*|\s+and\s+', re.IGNORECASE)
_PREFIX_RE = re.compile(
    r'\b(?:Mayor\s+Pro\s+[Tt]em|Mayor|Council\s+Members?|CM|Dr\.)\s+',
    re.IGNORECASE,
)

# Major section headers that signal we've left a motion's scope
_SECTION_HEADER_RE = re.compile(
    r'^\s*(?:CONSENT\s+AGENDA|PUBLIC\s+HEARING|ZONING\s+HEARING|'
    r'PRESENTATIONS?|EXECUTIVE\s+SESSION|ADJOURN|City\s+of\s+Fort\s+Worth)',
    re.IGNORECASE,
)


def _preprocess(text: str) -> str:
    """
    Collapse PDF extraction artifacts: join lines that are clearly
    mid-sentence continuations (no terminal punctuation, short fragments).
    Then collapse runs of 3+ blank lines down to 2.
    """
    lines = text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append('')
            continue
        # Join with previous non-blank line if it ended mid-word or mid-clause
        if (out and out[-1].strip()
                and not out[-1].strip()[-1] in '.!?:'
                and not _MOTION_LABEL_RE.match(out[-1])
                and not _CASE_REF_RE.match(stripped)
                and not _SECTION_HEADER_RE.match(stripped)
                and len(out[-1].strip()) < 120):
            out[-1] = out[-1].rstrip() + ' ' + stripped
        else:
            out.append(line)
    # Collapse 3+ consecutive blanks
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(out))
    return result


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


def _extract_names_from_list(raw: str) -> list[str]:
    """Parse 'Mayor Parker, Mayor Pro tem Flores, and Council Members Crain, Hill' → names."""
    cleaned = _PREFIX_RE.sub('', raw).strip()
    parts = _NAME_SEP_RE.split(cleaned)
    names = []
    for p in parts:
        p = p.strip().rstrip('.,;')
        p = _PREFIX_RE.sub('', p).strip()
        # Strip residual leading "and"
        p = re.sub(r'^\s*and\s+', '', p, flags=re.IGNORECASE).strip()
        if len(p) >= 2 and p.lower() not in ('', 'the', 'a', 'an'):
            # Resolve last-name-only to full name via member district table
            lower = p.lower()
            full = next((k for k in _MEMBER_DISTRICT if k.split()[-1] == lower.split()[-1] and ' ' in k), None)
            names.append(full.title() if full else p)
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
        if re.match(r'^(?:Staff|City\s+Manager|City\s+Attorney|CALL|Absent)', stripped, re.IGNORECASE):
            if 'absent' not in stripped.lower() or len(stripped) > 40:
                break
        m = _ATTENDANCE_RE.search(stripped)
        if m:
            full_name = m.group(1).strip().rstrip(',.')
            district = m.group(2) or ""
            if not district:
                if re.search(r'mayor\s+pro\s+tem', stripped, re.IGNORECASE):
                    district = _MEMBER_DISTRICT.get(full_name.split()[-1].lower(), "")
                elif re.search(r'^\s*mayor\b', stripped, re.IGNORECASE):
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


def _build_unanimous_members(absent_names: list[str], member_map: dict) -> list[dict]:
    absent_lower = {n.lower() for n in absent_names}
    absent_last  = {n.split()[-1].lower() for n in absent_names}
    by_member = []

    if member_map:
        # Only use full-name keys (contain a space) to avoid last-name duplicates
        full_name_entries = {k: v for k, v in member_map.items() if ' ' in k}
        roster = full_name_entries if full_name_entries else member_map
        for name, district in roster.items():
            is_absent = name in absent_lower or name.split()[-1] in absent_last
            by_member.append({
                "name": name.title(),
                "district": district,
                "vote": "ABSENT" if is_absent else "AYE",
            })
    else:
        for full_name, district in _CURRENT_ROSTER:
            last = full_name.split()[-1].lower()
            is_absent = full_name.lower() in absent_lower or last in absent_last
            by_member.append({
                "name": full_name,
                "district": district,
                "vote": "ABSENT" if is_absent else "AYE",
            })
    return by_member


def _parse_motion_block(motion_text: str, member_map: dict) -> Optional[dict]:
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
        support_m  = _SUPPORT_RE.search(tail)
        opposition_m = _OPPOSITION_RE.search(tail)

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

        if not opposition_m:
            for m in _VOTING_NO_RE.finditer(tail):
                name = m.group(1)
                if not any(v["name"].lower() == name.lower() for v in by_member):
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


def associate_votes_to_items(minutes_text: str) -> dict[str, dict]:
    """
    Scan Fort Worth minutes and return {case_ref: vote_summary_dict}.

    Strategy: work on the pre-processed (line-joined) text, then scan paragraph
    by paragraph.  A paragraph is a sequence of non-blank lines.
    """
    member_map = parse_attendance(minutes_text)
    text = _preprocess(minutes_text)

    # Split into paragraphs (blank-line separated blocks)
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    item_votes: dict[str, dict] = {}
    current_ref: Optional[str] = None
    current_districts: list[str] = []
    pending_motion: Optional[str] = None  # motion label hit, next para is body

    for para in paragraphs:
        # Reset on major section headers (prevents speaker comments setting ref too early)
        if _SECTION_HEADER_RE.match(para):
            current_ref = None
            current_districts = []
            pending_motion = None
            continue

        # Case reference — only update current_ref when it looks like an agenda item
        # heading (start of para or after a number) not mid-sentence speaker comments
        case_m = _CASE_REF_RE.search(para)
        if case_m:
            # Only use as current_ref if the ref is near the start of the para
            # or the para is short (item heading), not buried in speaker comment prose
            ref_start = case_m.start()
            pre_text = para[:ref_start].strip()
            is_heading = (
                ref_start < 60                           # near start
                or re.match(r'^\d+\.\s*$', pre_text)    # just a number prefix
                or not pre_text                          # at very start
            )
            if is_heading:
                raw_ref = case_m.group(0)
                ref_key = re.sub(r'\s*\([^)]*\)\s*$', '', raw_ref).strip().upper().replace("M.C.", "M&C")
                ref_key = re.sub(r'^ITEM\s+', '', ref_key)
                current_ref = ref_key
                current_districts = extract_districts_from_ref(para)

        # Check for "Motion:" label (standalone paragraph)
        if _MOTION_LABEL_RE.match(para):
            pending_motion = ""
            continue

        # If previous para was "Motion:", this para is the motion body
        if pending_motion is not None:
            motion_text = para
            pending_motion = None
            if current_ref and motion_text:
                result = _parse_motion_block(motion_text, member_map)
                if result:
                    result["districts"] = current_districts
                    # Overwrite if new result has a non-zero nay count (more specific)
                    existing = item_votes.get(current_ref)
                    if not existing or (result["nays"] > 0 and existing["nays"] == 0):
                        item_votes[current_ref] = result
            continue

        # "Motion:" inline at start of para
        inline_m = re.match(r'^Motion\s*:\s*(.+)', para, re.IGNORECASE | re.DOTALL)
        if inline_m:
            motion_text = inline_m.group(1).strip()
            if current_ref and motion_text:
                result = _parse_motion_block(motion_text, member_map)
                if result:
                    result["districts"] = current_districts
                    existing = item_votes.get(current_ref)
                    if not existing or (result["nays"] > 0 and existing["nays"] == 0):
                        item_votes[current_ref] = result
            continue

        # Para contains a tally inline (no "Motion:" label)
        if _TALLY_RE.search(para) and current_ref:
            result = _parse_motion_block(para, member_map)
            if result:
                result["districts"] = current_districts
                existing = item_votes.get(current_ref)
                if not existing or (result["nays"] > 0 and existing["nays"] == 0):
                    item_votes[current_ref] = result

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
