"""
M&C (Mayor and Council Communication) staff report parser.
Extracts deal terms from Fort Worth M&C PDFs for economic incentive items.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Dollar amount extraction ─────────────────────────────────────────────────

_DOLLAR_RE = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|M\b|B\b)?',
    re.IGNORECASE,
)

def _extract_dollars(text: str) -> list[int]:
    results = []
    for m in _DOLLAR_RE.finditer(text):
        try:
            val = float(m.group(1).replace(",", ""))
            suffix = (m.group(2) or "").lower()
            if suffix in ("million", "m"):
                val *= 1_000_000
            elif suffix in ("billion", "b"):
                val *= 1_000_000_000
            if val >= 1_000:
                results.append(int(val))
        except ValueError:
            pass
    return results


# ── Specific field extractors ────────────────────────────────────────────────

def _extract_investment(text: str) -> Optional[int]:
    """Total development cost / investment commitment."""
    patterns = [
        r'(?:total\s+development\s+costs?\s+of|minimum\s+total\s+development\s+costs?\s+of|'
        r'total\s+investment\s+of|invest\s+(?:a\s+)?minimum\s+of|investment\s+of\s+at\s+least)'
        r'\s*\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|M\b|B\b)?',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                suffix = (m.group(2) or "").lower()
                if suffix in ("million", "m"):
                    val *= 1_000_000
                elif suffix in ("billion", "b"):
                    val *= 1_000_000_000
                return int(val)
            except (ValueError, IndexError):
                pass
    # Fallback: largest dollar amount in the document near "cost" or "invest"
    invest_ctx = re.findall(
        r'(?:cost|invest|construction|development).{0,80}\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|M\b|B\b)?',
        text, re.IGNORECASE
    )
    amounts = []
    for v, suf in invest_ctx:
        try:
            val = float(v.replace(",", ""))
            if (suf or "").lower() in ("million", "m"):
                val *= 1_000_000
            elif (suf or "").lower() in ("billion", "b"):
                val *= 1_000_000_000
            amounts.append(int(val))
        except ValueError:
            pass
    return max(amounts) if amounts else None


def _extract_abatement_pct(text: str) -> Optional[float]:
    """Abatement percentage (e.g. '75%' or '85 percent')."""
    m = re.search(
        r'(\d{1,3})\s*%\s*(?:of\s+)?(?:tax\s+)?abatement|'
        r'abatement\s+of\s+(\d{1,3})\s*(?:%|percent)',
        text, re.IGNORECASE
    )
    if m:
        val = m.group(1) or m.group(2)
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return None


def _extract_rebate_pct(text: str) -> Optional[float]:
    """Chapter 380 rebate percentage (e.g. '85% of new incremental ... taxes')."""
    m = re.search(
        r'(\d{1,3})\s*%\s*of\s+(?:new\s+)?(?:incremental\s+)?(?:city\s+)?(?:ad\s+valorem|property|sales)\s+tax',
        text, re.IGNORECASE
    )
    if m:
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            pass
    return None


def _extract_rebate_cap(text: str) -> Optional[int]:
    """Total grant/rebate cap (e.g. 'not to exceed $80,000,000')."""
    m = re.search(
        r'(?:not\s+to\s+exceed|total\s+(?:amount\s+)?(?:not\s+to\s+exceed|of(?:\s+up\s+to)?)|'
        r'program\s+cap(?:\s+of)?|maximum\s+(?:grant|rebate|incentive))\s*\$\s*([\d,]+(?:\.\d+)?)\s*(million|M\b)?',
        text, re.IGNORECASE
    )
    if m:
        try:
            val = float(m.group(1).replace(",", ""))
            if (m.group(2) or "").lower() in ("million", "m"):
                val *= 1_000_000
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def _extract_term_years(text: str) -> Optional[int]:
    """Incentive term in years."""
    m = re.search(
        r'(?:for|over|a)\s+(\d+)[-\s]*year\s+(?:term|period|agreement|abatement|grant)|'
        r'(\d+)[-\s]*year\s+(?:tax\s+)?abatement|'
        r'up\s+to\s+(\d+)\s+annual\s+grants',
        text, re.IGNORECASE
    )
    if m:
        val = m.group(1) or m.group(2) or m.group(3)
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def _extract_jobs(text: str) -> Optional[int]:
    """Job creation commitment."""
    m = re.search(
        r'(?:create|retain|maintain|provide|minimum\s+of)\s+(?:at\s+least\s+)?(\d[\d,]*)\s+'
        r'(?:full.time|FTE|permanent|new|direct)?\s*(?:jobs?|positions?|employees?)',
        text, re.IGNORECASE
    )
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except (ValueError, TypeError):
            pass
    return None


def _extract_mc_number(text: str) -> Optional[str]:
    """Extract M&C file number from the report header."""
    m = re.search(r'M&?C\s+(?:FILE\s+NUMBER:?\s*)?(\d{2}-\d{4,6})', text, re.IGNORECASE)
    if m:
        return f"M&C {m.group(1)}"
    return None


# ── Main entry point ─────────────────────────────────────────────────────────

def parse_mc_report(text: str) -> dict:
    """
    Extract all deal terms from an M&C staff report text.
    Returns a dict suitable for merging into an AgendaItem's analysis.
    """
    result = {
        "mc_number":        _extract_mc_number(text),
        "mc_investment":    _extract_investment(text),
        "mc_abatement_pct": _extract_abatement_pct(text),
        "mc_rebate_pct":    _extract_rebate_pct(text),
        "mc_rebate_cap":    _extract_rebate_cap(text),
        "mc_term_years":    _extract_term_years(text),
        "mc_jobs":          _extract_jobs(text),
        "mc_enriched":      True,
    }

    # Build a human-readable summary of what was found
    found = []
    if result["mc_investment"]:
        found.append(f"Total investment: ${result['mc_investment']:,.0f}")
    if result["mc_rebate_cap"]:
        found.append(f"Grant/rebate cap: ${result['mc_rebate_cap']:,.0f}")
    if result["mc_abatement_pct"]:
        found.append(f"Abatement rate: {result['mc_abatement_pct']:.0f}%")
    if result["mc_rebate_pct"]:
        found.append(f"Rebate rate: {result['mc_rebate_pct']:.0f}% of incremental taxes")
    if result["mc_term_years"]:
        found.append(f"Term: {result['mc_term_years']} years")
    if result["mc_jobs"]:
        found.append(f"Jobs committed: {result['mc_jobs']:,}")

    result["mc_summary"] = " · ".join(found) if found else "M&C staff report uploaded — no structured deal terms extracted."
    return result
