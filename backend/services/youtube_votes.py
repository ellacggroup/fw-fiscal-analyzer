"""
YouTube transcript vote extractor for Fort Worth City Council meetings.

Used as a fallback for recent meetings where Legistar minutes aren't published yet.
Fetches auto-generated captions from the Fort Worth YouTube channel and parses
spoken vote records.

Fort Worth channel: @cityoffortworth
Council meetings playlist: PL6sptIzJVcmpBFr6cSdMRRpT2pV-Bie3c
"""

import logging
import re
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_YT_PLAYLIST_ID = "PL6sptIzJVcmpBFr6cSdMRRpT2pV-Bie3c"
_YT_CHANNEL_HANDLE = "@cityoffortworth"

# Matches spoken vote patterns in transcripts:
# "the motion carries 10 to 0" / "8 ayes 1 nay" / "motion passed unanimously"
_SPOKEN_RESULT_RE = re.compile(
    r'(?:'
    r'motion\s+(?:carries|carried|passes|passed|approved|failed)\s+'
    r'(?:unanimously|(?:(\d+)\s+(?:to|-)\s+(\d+)))'
    r'|(\d+)\s+ayes?\s+(?:and\s+)?(\d+)\s+nays?'
    r')',
    re.IGNORECASE,
)

# Spoken dissent: "council member hill voting no" / "hill votes against"
_SPOKEN_NO_RE = re.compile(
    r'(?:council\s+member\s+|cm\s+)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'
    r'(?:voting?\s+(?:no|against|nay)|votes?\s+(?:no|against|nay))',
    re.IGNORECASE,
)

# Case reference spoken aloud: "ZC 23 127" / "M and C 23 0557" / "SP 23 009"
_SPOKEN_REF_RE = re.compile(
    r'\b(?:'
    r'(?:M\s+and\s+C|M\s*&\s*C|MC)\s+(\d{2}[-\s]\d{4,6})|'
    r'(?:ZC|SP|AX|FP|PP|RP)\s*[-\s]?\s*(\d{2}[-\s]\d{3,6})'
    r')',
    re.IGNORECASE,
)


def _get_playlist_videos(playlist_id: str, max_results: int = 50) -> list[dict]:
    """
    Scrape YouTube playlist page for video IDs and titles without requiring API key.
    Returns list of {video_id, title, published_at}.
    """
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            })
        if resp.status_code != 200:
            logger.warning(f"YouTube playlist returned {resp.status_code}")
            return []

        # Extract videoId and title from JSON embedded in the page
        videos = []
        seen = set()

        # Parse videoId entries from ytInitialData
        for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', resp.text):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            # Find nearby title
            start = m.start()
            nearby = resp.text[start:start+500]
            title_m = re.search(r'"text"\s*:\s*"([^"]{10,120})"', nearby)
            title = title_m.group(1) if title_m else ""
            if any(kw in title.lower() for kw in ["city council", "council meeting", "regular meeting", "special meeting"]):
                videos.append({"video_id": vid, "title": title})
            if len(videos) >= max_results:
                break

        return videos
    except Exception as e:
        logger.warning(f"Failed to fetch YouTube playlist: {e}")
        return []


def _get_transcript(video_id: str) -> Optional[str]:
    """
    Fetch auto-generated YouTube captions as plain text.
    Uses the timedtext API endpoint (no API key required).
    """
    # Try to get caption track list
    try:
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            # Get video page to extract caption URL
            resp = client.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
        if resp.status_code != 200:
            return None

        # Extract captionTracks from ytInitialPlayerResponse
        tracks_m = re.search(r'"captionTracks":\s*(\[.*?\])', resp.text, re.DOTALL)
        if not tracks_m:
            return None

        import json
        tracks_raw = tracks_m.group(1)
        # Find first English auto or manual track
        url_m = re.search(r'"baseUrl"\s*:\s*"(https://www\.youtube\.com/api/timedtext[^"]+)"', tracks_raw)
        if not url_m:
            return None

        caption_url = url_m.group(1).replace("\\u0026", "&")
        with httpx.Client(follow_redirects=True, timeout=30.0) as client:
            captions_resp = client.get(caption_url, headers={"User-Agent": "Mozilla/5.0"})
        if captions_resp.status_code != 200:
            return None

        # Strip XML tags to get plain text
        text = re.sub(r'<[^>]+>', ' ', captions_resp.text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&#39;', "'", text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    except Exception as e:
        logger.warning(f"Failed to fetch transcript for {video_id}: {e}")
        return None


def _parse_transcript_votes(transcript: str) -> dict[str, dict]:
    """
    Parse vote records from a YouTube transcript.
    Returns {case_ref: {ayes, nays, passed, by_member, source: "youtube"}}.
    """
    item_votes: dict[str, dict] = {}
    current_ref: Optional[str] = None

    sentences = re.split(r'[.!?]\s+', transcript.lower())

    for sent in sentences:
        # Look for case reference
        ref_m = _SPOKEN_REF_RE.search(sent)
        if ref_m:
            raw = ref_m.group(0).upper()
            raw = re.sub(r'\s+', '-', raw.strip())
            raw = re.sub(r'M\s*AND\s*C|MC', 'M&C', raw, flags=re.IGNORECASE)
            current_ref = raw

        # Look for vote result near current ref
        result_m = _SPOKEN_RESULT_RE.search(sent)
        if result_m and current_ref:
            ayes = result_m.group(1) or result_m.group(3)
            nays = result_m.group(2) or result_m.group(4)

            if ayes is None:
                # "unanimously" or just "carries"
                ayes_int, nays_int = None, 0
            else:
                ayes_int = int(ayes)
                nays_int = int(nays) if nays else 0

            no_voters = [m.group(1) for m in _SPOKEN_NO_RE.finditer(sent)]
            by_member = [{"name": n, "district": "", "vote": "NAY"} for n in no_voters]

            item_votes[current_ref] = {
                "ayes": ayes_int,
                "nays": nays_int,
                "abstain": 0,
                "absent": None,
                "passed": (ayes_int is None) or (ayes_int > nays_int),
                "by_member": by_member,
                "districts": [],
                "source": "youtube",
            }

    return item_votes


def _video_date_from_title(title: str) -> Optional[str]:
    """Extract ISO date from a YouTube video title like 'City Council Meeting 04/08/2025'."""
    # MM/DD/YYYY or Month D, YYYY
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', title)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    m = re.search(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{1,2}),?\s+(\d{4})',
        title, re.IGNORECASE,
    )
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y")
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def get_youtube_votes_for_date(meeting_date: str) -> Optional[dict[str, dict]]:
    """
    Attempt to find a YouTube video for the given meeting date and parse votes from it.
    Returns {case_ref: vote_dict} or None if not found.
    """
    videos = _get_playlist_videos(_YT_PLAYLIST_ID)
    if not videos:
        return None

    target = meeting_date  # "2025-04-08"
    matched_video = None

    for video in videos:
        vdate = _video_date_from_title(video["title"])
        if vdate == target:
            matched_video = video
            break

    if not matched_video:
        logger.info(f"No YouTube video found for {meeting_date}")
        return None

    logger.info(f"Fetching YouTube transcript for {meeting_date}: {matched_video['video_id']}")
    transcript = _get_transcript(matched_video["video_id"])
    if not transcript:
        logger.warning(f"No transcript available for video {matched_video['video_id']}")
        return None

    votes = _parse_transcript_votes(transcript)
    logger.info(f"YouTube transcript parsed {len(votes)} vote records for {meeting_date}")
    return votes if votes else None
