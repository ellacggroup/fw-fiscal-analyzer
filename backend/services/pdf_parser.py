import pdfplumber
import re
from typing import Optional


def extract_text_from_pdf(file_bytes: bytes) -> str:
    import io
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)


def detect_meeting_date(text: str) -> Optional[str]:
    patterns = [
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
        r"\d{1,2}/\d{1,2}/\d{4}",
    ]
    for pattern in patterns:
        m = re.search(pattern, text[:3000])
        if m:
            return m.group(0)
    return None


# Sections we want to skip entirely
_SKIP_SECTION_KEYWORDS = {
    "call to order", "invocation", "pledge of allegiance",
    "public comment", "citizen comment", "open forum",
    "adjournment", "executive session", "closed session",
    "roll call", "approval of minutes", "announcements",
}

# Keywords that signal the start of substantive agenda sections
_SUBSTANTIVE_SECTIONS = {
    "consent agenda", "general consent", "action items",
    "planning and zoning", "zoning cases", "individual items",
    "regular agenda", "new business", "old business",
    "public hearing", "presentations", "mayor and council",
    "miscellaneous", "general",
}

# Patterns for Fort Worth M&C references and similar
_MC_PATTERN = re.compile(
    r'\bM&?C\s+([A-Z]-\d{4,6})\b', re.IGNORECASE
)
_ZC_PATTERN = re.compile(
    r'\b(ZC-\d{2}-\d{3,4})\b', re.IGNORECASE
)
_SP_PATTERN = re.compile(
    r'\b(SP-\d{2}-\d{3,4})\b', re.IGNORECASE
)

# Item number patterns — matches "1.", "2.", "A.", "B.", "1.1.", "Item 5"
_ITEM_START = re.compile(
    r'^'
    r'(?:'
    r'(?:ITEM\s+)?(\d{1,3}[\.\)](?:\d+[\.\)])?)'  # "1." "2." "1.1." "2)"
    r'|'
    r'([A-Z][\.\)](?:\s+\d+[\.\)])?)'              # "A." "B." "A.1."
    r')'
    r'\s+(.+)',
    re.IGNORECASE
)


def extract_agenda_items(text: str) -> list[dict]:
    """
    Parse a Fort Worth City Council agenda PDF text into structured items.

    Strategy:
    1. Split into lines, track which section we're in
    2. Identify item boundaries by numbered/lettered prefixes and M&C refs
    3. Accumulate multi-line descriptions
    4. Skip ceremonial / procedural sections
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    items = []
    current_item = None
    current_section = ""
    in_skip_section = False
    item_counter = 0

    def flush():
        nonlocal current_item
        if current_item and current_item.get("title"):
            items.append(current_item)
        current_item = None

    def is_section_header(line: str) -> bool:
        stripped = line.strip()
        # All-caps lines with no trailing period are often headers
        if len(stripped) > 4 and stripped == stripped.upper() and not stripped.endswith("."):
            return True
        # Lines that end with a colon
        if stripped.endswith(":") and len(stripped) < 80:
            return True
        return False

    def section_is_skippable(section_text: str) -> bool:
        sl = section_text.lower().strip().rstrip(":")
        return any(kw in sl for kw in _SKIP_SECTION_KEYWORDS)

    def section_is_substantive(section_text: str) -> bool:
        sl = section_text.lower().strip().rstrip(":")
        return any(kw in sl for kw in _SUBSTANTIVE_SECTIONS)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detect section headers
        if is_section_header(stripped):
            if section_is_skippable(stripped):
                flush()
                in_skip_section = True
                current_section = stripped
                continue
            elif section_is_substantive(stripped):
                flush()
                in_skip_section = False
                current_section = stripped
                continue
            else:
                # Ambiguous header — keep current skip state, update section label
                current_section = stripped

        if in_skip_section:
            continue

        # Check for M&C reference (Fort Worth specific)
        mc_match = _MC_PATTERN.search(stripped)
        zc_match = _ZC_PATTERN.search(stripped)
        sp_match = _SP_PATTERN.search(stripped)
        item_match = _ITEM_START.match(stripped)

        if mc_match or zc_match or sp_match or item_match:
            flush()
            item_counter += 1

            if mc_match:
                ref = "M&C " + mc_match.group(1).upper()
            elif zc_match:
                ref = zc_match.group(1).upper()
            elif sp_match:
                ref = sp_match.group(1).upper()
            else:
                ref = None

            if item_match:
                num = (item_match.group(1) or item_match.group(2) or "").rstrip(".")
                title_text = item_match.group(3).strip()
                if ref and ref not in title_text:
                    title_text = f"{ref} — {title_text}"
                item_num = num
            else:
                title_text = stripped
                item_num = str(item_counter)

            current_item = {
                "item_number": item_num,
                "title": _clean_title(title_text),
                "description": stripped,
                "section": current_section,
            }
        else:
            # Continuation line — append to current item description
            if current_item:
                current_item["description"] = current_item["description"] + " " + stripped
                # If the title is very short, extend it slightly
                if len(current_item["title"]) < 60 and len(stripped) < 120:
                    current_item["title"] = _clean_title(
                        current_item["title"] + " " + stripped
                    )[:120]

    flush()

    # Deduplicate and clean up
    seen = set()
    unique = []
    for item in items:
        key = item["title"][:80].lower()
        if key not in seen and len(item["title"].strip()) > 5:
            seen.add(key)
            item["description"] = item["description"][:2000]
            unique.append(item)

    # If we found almost nothing, fall back to a simpler line-based approach
    if len(unique) < 2:
        return _fallback_extraction(text)

    return unique


def _clean_title(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    text = text[:150]
    return text


def _fallback_extraction(text: str) -> list[dict]:
    """
    Fallback: grab any line that looks substantive (20-200 chars, not all caps header).
    Used when the primary parser finds too few items.
    """
    items = []
    counter = 0
    for line in text.splitlines():
        stripped = line.strip()
        if 20 < len(stripped) < 200:
            if stripped == stripped.upper():
                continue  # skip all-caps headers
            if any(kw in stripped.lower() for kw in _SKIP_SECTION_KEYWORDS):
                continue
            counter += 1
            items.append({
                "item_number": str(counter),
                "title": stripped[:120],
                "description": stripped,
                "section": "",
            })
        if counter >= 40:
            break
    return items
