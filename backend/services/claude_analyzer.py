"""
Claude API integration for Fort Worth fiscal impact analysis.

Runs after the rule-based analyzer to add qualitative analysis:
  - plain-English summary
  - fiscal impact rating (overrides rule-based when Claude is available)
  - risk level (LOW / MEDIUM / HIGH)
  - one-time vs recurring flag
  - key concerns

Items are batched to minimise API calls. Falls back gracefully if the
ANTHROPIC_API_KEY env var is not set.
"""

import json
import os
from typing import Optional

import anthropic

_client: Optional[anthropic.Anthropic] = None
BATCH_SIZE = 12  # items per Claude call; keeps each prompt well under 4K tokens


def _get_client() -> Optional[anthropic.Anthropic]:
    global _client
    if _client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return None
        _client = anthropic.Anthropic(api_key=key)
    return _client


def claude_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def analyze_items_with_claude(
    items: list[dict],
    meeting_date: Optional[str] = None,
) -> list[dict]:
    """
    Return one claude_analysis dict per item (same order as input).
    Falls back to empty stubs if the API is unavailable.
    """
    client = _get_client()
    if client is None:
        return [_empty() for _ in items]

    results: list[dict] = []
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        results.extend(_analyze_batch(client, batch, meeting_date))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a municipal fiscal analyst specializing in Fort Worth, Texas city government.
You produce concise, accurate fiscal impact assessments for a non-technical civic audience.

Fort Worth context:
- Property tax rate: $0.7125 per $100 assessed value (FY2026)
- City share of sales tax: 1%
- M&C = Manager & Council report (standard approval mechanism)
- Consent agenda items are routine; non-consent items require individual council action
- CIP = Capital Improvement Program; TPW = Transportation & Public Works
- Dollar thresholds: <$100K = small, $100K–$1M = medium, >$1M = large
- Contracts funded through existing appropriations are typically NEUTRAL unless the
  appropriation itself is new spending
- Tax abatements reduce future property tax revenue — flag as NEGATIVE for long-term impact
- Grants and interlocal reimbursements are POSITIVE (incoming revenue)
"""

_ITEM_SCHEMA = """\
For EACH item return a JSON object with these exact keys:
  "summary"                  : string  — 2-3 sentence plain-English explanation of what the
                                         item does and its net fiscal impact. Write for a
                                         general Fort Worth resident, not a financial expert.
  "fiscal_impact_rating"     : string  — one of: "POSITIVE", "NEUTRAL", "NEGATIVE", "UNKNOWN"
  "risk_level"               : string  — one of: "LOW", "MEDIUM", "HIGH"
  "is_recurring"             : boolean or null  — true = ongoing annual obligation;
                                                   false = one-time; null = unclear
  "one_time_vs_recurring_note": string — brief phrase (e.g. "One-time capital expenditure",
                                          "Annual maintenance contract", "Grant; expires FY2027")
  "key_concerns"             : array of strings — 0-3 brief fiscal flags or watch-items;
                                empty array [] if none
"""


def _build_prompt(items: list[dict], meeting_date: Optional[str]) -> str:
    date_line = f"Meeting date: {meeting_date}\n\n" if meeting_date else ""

    item_blocks = []
    for idx, item in enumerate(items, 1):
        section = f" [{item.get('section', '')}]" if item.get("section") else ""
        item_blocks.append(
            f"### Item {idx}{section}\n"
            f"Title: {item.get('title', '(no title)')}\n"
            f"Description: {(item.get('description') or '')[:600]}"
        )

    return (
        f"{date_line}"
        f"Analyze the following {len(items)} Fort Worth City Council agenda item(s).\n\n"
        f"{_ITEM_SCHEMA}\n\n"
        "Respond with a JSON array — one object per item, in the same order as the input. "
        "Return ONLY the JSON array, no markdown fencing, no explanatory text.\n\n"
        + "\n\n".join(item_blocks)
    )


def _analyze_batch(
    client: anthropic.Anthropic,
    items: list[dict],
    meeting_date: Optional[str],
) -> list[dict]:
    prompt = _build_prompt(items, meeting_date)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()

        # Strip accidental markdown code fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            parsed = [parsed]

        # Pad or trim to match batch length
        results = [_normalize(r) for r in parsed[: len(items)]]
        while len(results) < len(items):
            results.append(_empty())
        return results

    except Exception as exc:
        print(f"[claude_analyzer] batch error: {exc}")
        return [_empty() for _ in items]


def _normalize(r: dict) -> dict:
    rating = r.get("fiscal_impact_rating", "UNKNOWN")
    if rating not in ("POSITIVE", "NEUTRAL", "NEGATIVE", "UNKNOWN"):
        rating = "UNKNOWN"
    risk = r.get("risk_level", "MEDIUM")
    if risk not in ("LOW", "MEDIUM", "HIGH"):
        risk = "MEDIUM"
    return {
        "summary": str(r.get("summary") or ""),
        "fiscal_impact_rating": rating,
        "risk_level": risk,
        "is_recurring": r.get("is_recurring"),
        "one_time_vs_recurring_note": str(r.get("one_time_vs_recurring_note") or ""),
        "key_concerns": [str(c) for c in (r.get("key_concerns") or [])[:3]],
    }


def _empty() -> dict:
    return {
        "summary": "",
        "fiscal_impact_rating": "UNKNOWN",
        "risk_level": "MEDIUM",
        "is_recurring": None,
        "one_time_vs_recurring_note": "",
        "key_concerns": [],
    }
