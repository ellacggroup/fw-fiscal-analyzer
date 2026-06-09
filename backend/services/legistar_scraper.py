"""
Legistar API client for Fort Worth City Council meeting discovery.

Fetches agenda and minutes PDF URLs for all City Council meetings
over the past N years using the Legistar public REST API.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LEGISTAR_BASE = "https://webapi.legistar.com/v1/fortworthtx"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _get(url: str, params: dict = None, timeout: float = 30.0) -> list | dict:
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url, params=params, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


def get_city_council_body_id() -> Optional[int]:
    """Return the Legistar BodyId for 'City Council'."""
    try:
        bodies = _get(f"{LEGISTAR_BASE}/Bodies")
        for body in bodies:
            name = (body.get("BodyName") or "").lower()
            if name == "city council" or name == "fort worth city council":
                return body["BodyId"]
        # Fallback: first body with "council" in the name
        for body in bodies:
            if "council" in (body.get("BodyName") or "").lower():
                return body["BodyId"]
    except Exception as e:
        logger.error(f"Legistar Bodies API error: {e}")
    return None


def get_council_meetings(years: int = 5) -> list[dict]:
    """
    Return all City Council meetings from the past `years` years.

    Each entry::

        {
            "date": "2024-01-16",
            "event_id": 12345,
            "agenda_url": "https://...",   # may be None
            "minutes_url": "https://...",  # may be None
            "body_name": "City Council",
        }
    """
    body_id = get_city_council_body_id()
    if body_id is None:
        logger.error("Could not resolve City Council body ID from Legistar")
        return []

    since = datetime.now() - timedelta(days=366 * years)
    since_str = since.strftime("%Y-%m-%dT00:00:00")

    try:
        events = _get(
            f"{LEGISTAR_BASE}/Events",
            params={
                "$filter": f"EventBodyId eq {body_id} and EventDate ge datetime'{since_str}'",
                "$orderby": "EventDate desc",
                "$top": 600,
            },
            timeout=45.0,
        )
    except Exception as e:
        logger.error(f"Legistar Events API error: {e}")
        return []

    meetings = []
    for event in events:
        agenda_url = event.get("EventAgendaFile") or None
        minutes_url = event.get("EventMinutesFile") or None

        if not agenda_url and not minutes_url:
            continue

        # Legistar dates are ISO strings like "2024-01-16T00:00:00"
        date_raw = event.get("EventDate", "")
        date = date_raw[:10] if date_raw else ""

        meetings.append({
            "date": date,
            "event_id": event.get("EventId"),
            "agenda_url": _normalize_legistar_url(agenda_url),
            "minutes_url": _normalize_legistar_url(minutes_url),
            "body_name": event.get("EventBodyName", "City Council"),
        })

    logger.info(f"Legistar returned {len(meetings)} meetings with documents")
    return meetings


def _normalize_legistar_url(url: Optional[str]) -> Optional[str]:
    """
    Legistar may return relative or malformed URLs for PDF files.
    Normalize them to absolute URLs, or return None if not usable.
    """
    if not url:
        return None
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://fortworthtexas.legistar.com{url}"
    return None


def fetch_pdf_bytes_lenient(url: str) -> Optional[bytes]:
    """
    Download a PDF from a URL, lenient about content-type headers.
    Returns raw bytes or None on failure.
    """
    try:
        with httpx.Client(follow_redirects=True, timeout=45.0) as client:
            resp = client.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/pdf,*/*",
                },
            )
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} fetching {url}")
            return None
        data = resp.content
        # Accept if it looks like a PDF (magic bytes) OR is large enough to be one
        if len(data) < 512:
            logger.warning(f"File too small ({len(data)} bytes): {url}")
            return None
        if not (data[:4] == b'%PDF' or b'%PDF' in data[:20]):
            logger.warning(f"Not a PDF (wrong magic bytes): {url}")
            return None
        if len(data) > 50 * 1024 * 1024:
            logger.warning(f"File too large (>{50}MB): {url}")
            return None
        return data
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None
