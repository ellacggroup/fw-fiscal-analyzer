"""
Claude API integration for Fort Worth fiscal impact analysis.

Runs after the rule-based analyzer to add qualitative analysis:
  - plain-English summary
  - fiscal impact rating (may override rule-based when Claude has a stronger signal)
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

from services.zoning_gis_lookup import lookup_zoning_case
from services.comprehensive_plan import lookup_comprehensive_plan

_client: Optional[anthropic.Anthropic] = None
BATCH_SIZE = 6  # smaller batches = more attention per item from Claude
MODEL = "claude-sonnet-5"
MAX_TOOL_ROUNDS = 3  # cap agentic back-and-forth so one batch can't run away


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
    rule_analyses: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Return one claude_analysis dict per item (same order as input).
    Falls back to empty stubs if the API is unavailable.
    Accepts optional rule_analyses so Claude can see what the rule engine found.
    """
    client = _get_client()
    if client is None:
        return [_empty() for _ in items]

    rule_analyses = rule_analyses or [{} for _ in items]

    results: list[dict] = []
    for i in range(0, len(items), BATCH_SIZE):
        batch_items = items[i : i + BATCH_SIZE]
        batch_rules = rule_analyses[i : i + BATCH_SIZE]
        results.extend(_analyze_batch(client, batch_items, batch_rules, meeting_date))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a municipal fiscal analyst specializing in Fort Worth, Texas city government.
You produce concise, accurate fiscal impact assessments for a non-technical civic audience.

## Fort Worth Context
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

## Fiscal Performance by Land Use (Fate TX 40-year methodology)
| Land Use              | R/C Ratio | Fiscal Character |
|-----------------------|-----------|-----------------|
| Commercial Retail     | 2.70      | Strongly positive |
| Industrial/Warehouse  | 2.32      | Positive |
| Office/Business Park  | 2.26      | Positive |
| Mixed-Use             | 1.74      | Positive |
| Multifamily           | 0.97      | Roughly neutral |
| Single-Family         | 0.72      | Net cost to city |
| Public/Institutional  | 0.07      | Significant net cost |

## CRITICAL RULES — FOLLOW WITHOUT EXCEPTION

### Rule 1: Rating and Summary Must Be Consistent
Your `fiscal_impact_rating` MUST match your `summary`. It is an error to rate an item
POSITIVE while the summary says it "worsens the city's fiscal position" or "costs the
city money." It is an error to rate an item NEGATIVE while the summary describes a net
benefit. If you find a contradiction, fix the rating to match the summary.

### Rule 2: Public Hearings Are Always NEUTRAL
A public hearing on annexation, zoning, or any other matter is a PROCEDURAL step
required by law. It has NO direct fiscal impact — it is not an approval or denial.
ALWAYS rate public hearings as NEUTRAL with impact_type = none.
Example: "Conduct a public hearing on annexation of [property]" → NEUTRAL.
"Approve annexation of [property]" → analyze normally.

### Rule 3: Zoning Changes — Rate the Direction of Change
For zoning items, rate based on whether the FROM→TO change IMPROVES or WORSENS
the city's fiscal position using the R/C ratio table above:
- If proposed use has higher R/C than current use → POSITIVE
- If proposed use has lower R/C than current use → NEGATIVE
- If roughly equivalent → NEUTRAL
Do NOT rate simply because the destination zone is "commercial" (positive) without
considering what is being rezoned FROM.

### Rule 4: Site Plans and Plats
A plat or site plan APPROVAL is a regulatory step. The approval itself is NEUTRAL.
Describe what development it enables and its fiscal implications. Do not rate the
approval as NEGATIVE just because the underlying land use has a low R/C ratio.
The broader development context matters.

## Tools
Most items already include a [Context: ...] block with zoning and Comprehensive Plan
data the city's own GIS lookup already ran for you — use that first, it's authoritative.
Only call a tool when a case number or address is mentioned in the item text that is
NOT already covered by the provided context (e.g. the item references a second, related
case number, or no context block is present for an item that clearly needs one). Do not
call a tool "just to check" on items that already have context — that wastes time and
money for no benefit. Never call a tool more than once for the same case/address.
"""

_TOOLS = [
    {
        "name": "lookup_zoning_case",
        "description": (
            "Look up an official Fort Worth zoning case (ZC-, SP-, etc.) in the City's "
            "GIS system. Returns current/proposed zoning codes, acreage, applicant, "
            "requested action, and Comprehensive Plan consistency. Only use this for a "
            "specific case number mentioned in the item that isn't already covered by "
            "the item's provided [Context] block."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "case_number": {
                    "type": "string",
                    "description": "The zoning case number, e.g. 'ZC-24-015' or 'SP-23-009'",
                },
            },
            "required": ["case_number"],
        },
    },
    {
        "name": "lookup_comp_plan",
        "description": (
            "Look up the Fort Worth Comprehensive Plan's Future Land Use designation for "
            "an address or intersection, to check whether a proposed action is consistent "
            "with the adopted plan. Only use this when an address is mentioned that isn't "
            "already covered by the item's provided [Context] block."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address_or_text": {
                    "type": "string",
                    "description": "A street address or intersection to look up",
                },
            },
            "required": ["address_or_text"],
        },
    },
]

_ITEM_SCHEMA = """\
For EACH item return a JSON object with these exact keys:
  "summary"                  : string  — 2-3 sentence plain-English explanation of what the
                                         item does and its net fiscal impact. MUST match the
                                         fiscal_impact_rating (no contradictions).
  "fiscal_impact_rating"     : string  — one of: "POSITIVE", "NEUTRAL", "NEGATIVE", "UNKNOWN"
                                         Must be consistent with the summary above.
  "risk_level"               : string  — one of: "LOW", "MEDIUM", "HIGH"
  "is_recurring"             : boolean or null  — true = ongoing annual obligation;
                                                   false = one-time; null = unclear
  "one_time_vs_recurring_note": string — brief phrase (e.g. "One-time capital expenditure",
                                          "Annual maintenance contract", "Grant; expires FY2027")
  "key_concerns"             : array of strings — 0-3 brief fiscal flags or watch-items;
                                empty array [] if none
"""


def _build_prompt(
    items: list[dict],
    rule_analyses: list[dict],
    meeting_date: Optional[str],
) -> str:
    date_line = f"Meeting date: {meeting_date}\n\n" if meeting_date else ""

    item_blocks = []
    for idx, (item, rule) in enumerate(zip(items, rule_analyses), 1):
        section = f" [{item.get('section', '')}]" if item.get("section") else ""
        category = rule.get("category", "")
        rule_rating = rule.get("fiscal_impact_rating", "")
        is_hearing = rule.get("annexation_hearing", False)
        zoning_parsed = rule.get("zoning_request_parsed", False)

        context_lines = []
        if category:
            context_lines.append(f"Category: {category}")
        if is_hearing:
            context_lines.append("NOTE: This is an annexation public hearing (procedural) — must be rated NEUTRAL")
        elif rule_rating and not zoning_parsed:
            context_lines.append(f"Rule-based rating: {rule_rating}")
        if zoning_parsed:
            from_label = rule.get("zoning_from_label", "")
            to_label   = rule.get("zoning_to_label", "")
            net_change = rule.get("zoning_annual_net_change")
            if from_label and to_label:
                context_lines.append(f"Zoning: {rule.get('zoning_from_code')} ({from_label}) → {rule.get('zoning_to_code')} ({to_label})")
            if net_change is not None:
                direction = "improves" if net_change > 0 else "worsens"
                context_lines.append(f"R/C analysis: rezoning {direction} city fiscal position by ~${abs(net_change):,}/yr")
            if rule.get("zoning_gis_source"):
                context_lines.append("(zoning codes verified against City GIS, not just agenda text)")

        comp_plan_status = rule.get("comp_plan_lookup_status")
        if comp_plan_status == "found":
            lu_label = rule.get("comp_plan_lu_label", "")
            consistent = rule.get("consistent_with_comp_plan", "")
            context_lines.append(f"Comprehensive Plan future land use: {lu_label}" + (f" — {consistent}" if consistent else ""))

        context_block = ""
        if context_lines:
            context_block = "\n[Context: " + "; ".join(context_lines) + "]"

        item_blocks.append(
            f"### Item {idx}{section}{context_block}\n"
            f"Title: {item.get('title', '(no title)')}\n"
            f"Description: {(item.get('description') or '')[:800]}"
        )

    return (
        f"{date_line}"
        f"Analyze the following {len(items)} Fort Worth City Council agenda item(s).\n\n"
        f"{_ITEM_SCHEMA}\n\n"
        "Respond with a JSON array — one object per item, in the same order as the input. "
        "Return ONLY the JSON array, no markdown fencing, no explanatory text.\n\n"
        + "\n\n".join(item_blocks)
    )


def _execute_tool(name: str, tool_input: dict) -> str:
    """Run a tool the model asked for and return its result as a JSON string."""
    try:
        if name == "lookup_zoning_case":
            result = lookup_zoning_case(str(tool_input.get("case_number", "")).strip())
            return json.dumps(result) if result else json.dumps(
                {"error": "No GIS record found for this case number"}
            )
        if name == "lookup_comp_plan":
            # category="Zoning Change" bypasses the relevance gate inside
            # lookup_comprehensive_plan — Claude already judged this relevant
            # by choosing to call the tool.
            result = lookup_comprehensive_plan(
                str(tool_input.get("address_or_text", "")), category="Zoning Change",
            )
            return json.dumps(result)
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _analyze_batch(
    client: anthropic.Anthropic,
    items: list[dict],
    rule_analyses: list[dict],
    meeting_date: Optional[str],
) -> list[dict]:
    prompt = _build_prompt(items, rule_analyses, meeting_date)
    messages: list = [{"role": "user", "content": prompt}]
    try:
        msg = None
        for _ in range(MAX_TOOL_ROUNDS):
            msg = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )
            if msg.stop_reason != "tool_use":
                break

            messages.append({"role": "assistant", "content": msg.content})
            tool_results = []
            for block in msg.content:
                if block.type == "tool_use":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _execute_tool(block.name, block.input),
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            # Exceeded MAX_TOOL_ROUNDS while still asking for tools — force
            # one last plain-text attempt with no tools offered.
            msg = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=messages,
            )

        text_blocks = [b.text for b in msg.content if b.type == "text"]
        raw = "".join(text_blocks).strip()

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
