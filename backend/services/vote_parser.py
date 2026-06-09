"""
Fort Worth City Council vote parser.

Extracts per-councilmember votes from meeting minutes text.
Fort Worth has 9 council districts + the Mayor.

Typical minutes vote format:
  AYES: Mayor Parker, Councilmember Flores (2), Councilmember Crain (3),
        Councilmember Moon (4), Councilmember Bivens (5), Councilmember
        Jordan (6), Councilmember Bonds (8), Councilmember Zadeh (9) - 8
  NAYS: None - 0
  ABSENT: Councilmember Shingleton (7) - 1

Or the simpler summary form:
  Motion passed 8-0
  Yeas - 8; Nays - 0
"""

import re
from typing import Optional


# Regex: captures AYES/NAYS/ABSTAIN/ABSENT blocks followed by member names
_VOTE_SECTION_RE = re.compile(
    r'\b(AYES?|NAYS?|NOES?|ABSTAIN(?:ED)?|ABSENT)\s*[:\-]\s*(.{0,400}?)(?=\n\s*(?:AYES?|NAYS?|NOES?|ABSTAIN|ABSENT|Motion|$))',
    re.IGNORECASE | re.DOTALL
)

# Member name followed by optional district in parens:
#   "Councilmember Bonds (8)" or "Mayor Parker" or "Councilmember Kelly Allen Gray (3)"
_MEMBER_RE = re.compile(
    r'(?:(?:Councilmember|Council\s+Member|Councilwoman|Councilman)\s+)?'
    r'((?:Mayor\s+)?[A-Z][a-zA-Z\-\']+(?:\s+[A-Z][a-zA-Z\-\']+){0,3})'
    r'(?:\s*\(\s*(?:District\s*)?(\d+)\s*\))?',
    re.IGNORECASE
)

# Simple tally: "Motion passed 7-0" or "Yeas - 8 ; Nays - 1"
_TALLY_RE = re.compile(
    r'(?:Motion\s+(?:passed|carried|approved|failed)|Yeas?|Ayes?)\s*[-–]\s*(\d+)\s*[;,]\s*(?:Nays?|Noes?)\s*[-–]\s*(\d+)',
    re.IGNORECASE
)

# Item reference patterns found in minutes that signal a new action item
_ITEM_REF_RE = re.compile(
    r'\b(?:'
    r'(?:M&?C|M\.C\.)\s+(?:[A-Z]-\d{4,6}|\d{2}-\d{4,6})|'
    r'ZC-\d{2}-\d{3,6}|'
    r'SP-\d{2}-\d{3,6}|'
    r'AX-\d{2}-\d{3,6}|'
    r'FP-\d{2}-\d{3,6}|'
    r'PP-\d{2}-\d{3,6}|'
    r'RP-\d{2}-\d{3,6}'
    r')',
    re.IGNORECASE
)

# Words that indicate the name is not an actual councilmember name
_SKIP_NAMES = {
    "none", "none-", "motion", "seconded", "second", "passed", "carried",
    "approved", "failed", "abstained", "all", "unanimous",
}


def _normalize_vote(raw: str) -> str:
    raw = raw.upper().strip()
    if raw.startswith("AYE") or raw.startswith("YEA"):
        return "AYE"
    if raw.startswith("NAY") or raw.startswith("NO"):
        return "NAY"
    if raw.startswith("ABSTAIN"):
        return "ABSTAIN"
    if raw.startswith("ABSENT"):
        return "ABSENT"
    return raw


def _parse_members(text: str, vote_type: str) -> list[dict]:
    """Parse individual member votes from a vote section text."""
    members = []
    seen = set()
    text_clean = re.sub(r'\s*-\s*\d+\s*$', '', text.strip())  # remove "- 8" tally at end

    for m in _MEMBER_RE.finditer(text_clean):
        raw_name = m.group(1).strip()
        if not raw_name or raw_name.lower().rstrip('.,;') in _SKIP_NAMES:
            continue
        if len(raw_name) < 3 or raw_name.lower() in ('the', 'and', 'a', 'an'):
            continue
        district = m.group(2) or ""

        # Normalize common name prefixes
        name = re.sub(r'^(?:Mayor\s+)', 'Mayor ', raw_name, flags=re.IGNORECASE)
        name = name.strip().title()

        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        # Detect Mayor role from prefix or "Mayor" in name
        is_mayor = "mayor" in raw_name.lower() or "mayor" in text_clean[:text_clean.find(raw_name)].lower()[-20:]
        if is_mayor and not district:
            district = "Mayor"

        members.append({
            "name": name,
            "district": district,
            "vote": vote_type,
        })

    return members


def extract_votes(text: str) -> list[dict]:
    """
    Parse all vote records in a minutes document.

    Returns a flat list of individual member vote records:
        [{"name": "Bonds", "district": "8", "vote": "AYE"}, ...]
    """
    all_votes = []

    for m in _VOTE_SECTION_RE.finditer(text):
        vote_type = _normalize_vote(m.group(1))
        section_text = m.group(2)
        members = _parse_members(section_text, vote_type)
        all_votes.extend(members)

    return all_votes


def associate_votes_to_items(minutes_text: str) -> dict[str, list[dict]]:
    """
    Scan minutes text and associate vote records with the preceding item reference.

    Returns::

        {
            "ZC-24-123": [{"name": "Bonds", "district": "8", "vote": "AYE"}, ...],
            "M&C 25-0557": [...],
            ...
        }

    Items with no item reference are stored under key "_general_".
    """
    item_votes: dict[str, list[dict]] = {}
    current_ref = "_general_"
    current_block: list[dict] = []

    lines = minutes_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for a new item reference on this line
        ref_match = _ITEM_REF_RE.search(line)
        if ref_match:
            if current_block:
                item_votes.setdefault(current_ref, []).extend(current_block)
                current_block = []
            current_ref = ref_match.group(0).upper().replace("M.C.", "M&C")

        # Check for vote section start on this line
        sec_match = re.match(r'(AYES?|NAYS?|NOES?|ABSTAIN(?:ED)?|ABSENT)\s*[:\-]\s*(.*)', line, re.IGNORECASE)
        if sec_match:
            vote_type = _normalize_vote(sec_match.group(1))
            section_text = sec_match.group(2)

            # Accumulate continuation lines (indented or no new item ref)
            j = i + 1
            while j < len(lines):
                cont = lines[j].strip()
                if not cont:
                    break
                if re.match(r'(AYES?|NAYS?|NOES?|ABSTAIN|ABSENT)\s*[:\-]', cont, re.IGNORECASE):
                    break
                if _ITEM_REF_RE.search(cont):
                    break
                section_text += " " + cont
                j += 1
            i = j - 1  # will be incremented at end of while loop

            members = _parse_members(section_text, vote_type)
            current_block.extend(members)

        i += 1

    if current_block:
        item_votes.setdefault(current_ref, []).extend(current_block)

    return item_votes


def summarize_votes(votes: list[dict]) -> dict:
    """
    Convert a flat list of vote records into a summary dict.

        {
            "ayes": 8, "nays": 0, "abstain": 0, "absent": 1,
            "passed": True,
            "by_member": [{"name": ..., "district": ..., "vote": ...}, ...]
        }
    """
    ayes = sum(1 for v in votes if v["vote"] == "AYE")
    nays = sum(1 for v in votes if v["vote"] == "NAY")
    abstain = sum(1 for v in votes if v["vote"] == "ABSTAIN")
    absent = sum(1 for v in votes if v["vote"] == "ABSENT")

    return {
        "ayes": ayes,
        "nays": nays,
        "abstain": abstain,
        "absent": absent,
        "passed": ayes > nays,
        "by_member": votes,
    }
