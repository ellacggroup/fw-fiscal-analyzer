"""
YouTube transcript vote extractor for Fort Worth City Council meetings.

Fort Worth uses electronic voting — the mayor says "Please vote" then
"Motion carries" or "Motion fails" without announcing the count.
Transcripts give us pass/fail per item and sometimes named dissenters.

Fort Worth YouTube channel: @cityoffortworth
Council meetings playlist: PL6sptIzJVcmpBFr6cSdMRRpT2pV-Bie3c
"""

import logging
import re
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PLAYLIST_ID = "PL6sptIzJVcmpBFr6cSdMRRpT2pV-Bie3c"
_CHANNEL_HANDLE = "@cityoffortworth"

# ── Case reference patterns (spoken / typed in transcript captions) ───────────
_CASE_REF_RE = re.compile(
    r'\b(?:'
    r'(?:M&?C|MNC|M\s+and\s+C)\s*[-\s]?\s*(\d{2}[-\s]\d{4,6})|'  # M&C / MNC 26-0583
    r'(?:ZC|SP|AX|FP|PP|RP)\s*[-\s]?\s*(\d{2}[-\s]\d{3,6})|'      # ZC-25-205
    r'(\d{2}-\d{4,6})'                                               # bare 26-5818
    r')',
    re.IGNORECASE,
)

# Vote outcome phrases
_CARRIES_RE  = re.compile(r'\bmotion\s+(?:carries|passed|passes|approved)\b', re.IGNORECASE)
_FAILS_RE    = re.compile(r'\bmotion\s+(?:fails|failed|denied|does\s+not\s+carry)\b', re.IGNORECASE)
_VOTE_RE     = re.compile(r'\bplease\s+vote\b', re.IGNORECASE)

# Spoken tally: "ten to zero" / "nine to two" / "10 to 0"
_NUMBER_WORDS = {
    'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,
    'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,
}
_SPOKEN_TALLY_RE = re.compile(
    r'(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven)'
    r'\s+(?:to|-)\s+'
    r'(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven)',
    re.IGNORECASE,
)

# Named dissenter: "Council Member Hill voting no" / "Lauersdorf votes against"
_DISSENT_RE = re.compile(
    r'(?:Council\s+Member\s+|Councilmember\s+)?'
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+'
    r'(?:voting?\s+(?:no|against|nay|in\s+opposition)|votes?\s+(?:no|against|nay))',
    re.IGNORECASE,
)


def _normalize_ref(raw: str) -> str:
    """Normalize a case ref to a canonical key: 'M&C 26-0583', 'ZC-25-205', '26-5818'."""
    r = raw.strip().upper()
    r = re.sub(r'\s+', ' ', r)
    # Normalize M&C variants
    r = re.sub(r'^(?:MNC|M\s+AND\s+C|M&C)\s*', 'M&C ', r, flags=re.IGNORECASE)
    # Normalize ZC/SP with spaces to dashes
    r = re.sub(r'^(ZC|SP|AX|FP|PP|RP)\s+', r'\1-', r)
    # Normalize spaces in numbers to dashes: "26 0583" → "26-0583"
    r = re.sub(r'(\d{2})\s+(\d{4,6})', r'\1-\2', r)
    return r.strip()


def _parse_number(s: str) -> int:
    """Parse word or digit number."""
    s = s.strip().lower()
    if s in _NUMBER_WORDS:
        return _NUMBER_WORDS[s]
    try:
        return int(s)
    except ValueError:
        return 0


def _get_video_list() -> list[dict]:
    """
    Fetch Fort Worth council meeting video IDs + titles from YouTube.
    Returns [{video_id, title, date_str}] sorted newest-first.
    Only includes regular council meeting videos (not work sessions).
    """
    videos = []
    seen: set[str] = set()

    sources = [
        f"https://www.youtube.com/playlist?list={_PLAYLIST_ID}",
        f"https://www.youtube.com/{_CHANNEL_HANDLE}/videos",
    ]

    for url in sources:
        try:
            with httpx.Client(follow_redirects=True, timeout=30) as client:
                resp = client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                })
            if resp.status_code != 200:
                continue

            # Extract videoId entries
            vid_positions = [(m.start(), m.group(1))
                             for m in re.finditer(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', resp.text)]

            for pos, vid in vid_positions:
                if vid in seen:
                    continue
                # Find nearest title text
                window = resp.text[pos:pos + 600]
                title_m = re.search(r'"text"\s*:\s*"([^"]{10,120})"', window)
                if not title_m:
                    continue
                title = title_m.group(1)

                # Only regular council meetings (skip work sessions, retreats, public comment)
                if not re.search(r'city\s+council\s+meeting', title, re.IGNORECASE):
                    continue
                if re.search(r'work\s+session|retreat|public\s+comment|budget|canvass', title, re.IGNORECASE):
                    continue

                date_str = _date_from_title(title)
                if not date_str:
                    continue

                seen.add(vid)
                videos.append({"video_id": vid, "title": title, "date": date_str})

        except Exception as e:
            logger.warning(f"Failed to fetch YouTube video list from {url}: {e}")

    # Sort newest first
    videos.sort(key=lambda v: v["date"], reverse=True)
    logger.info(f"Found {len(videos)} council meeting videos on YouTube")
    return videos


def _date_from_title(title: str) -> Optional[str]:
    """Extract ISO date from title like 'City Council Meeting | March 10, 2026'."""
    # "Month Day, Year" or "Month Day Year"
    m = re.search(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+(\d{1,2}),?\s+(\d{4})',
        title, re.IGNORECASE,
    )
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    # MM/DD/YYYY
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', title)
    if m:
        try:
            dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _fetch_transcript(video_id: str) -> Optional[list[dict]]:
    """Fetch transcript using youtube-transcript-api. Returns list of {text, start}."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        snippets = list(api.fetch(video_id))
        return [{"text": s.text, "start": s.start} for s in snippets]
    except Exception as e:
        logger.warning(f"Could not fetch transcript for {video_id}: {e}")
        return None


def _parse_transcript_for_votes(snippets: list[dict]) -> dict[str, dict]:
    """
    Walk the transcript and build {case_ref: vote_result} for each item.

    Strategy:
    - Track the most recently mentioned case ref
    - When we see "Please vote" → "Motion carries/fails" within ~30 seconds,
      record a vote for the current ref
    - Also capture spoken tally and named dissenters from surrounding text
    """
    item_votes: dict[str, dict] = {}
    current_ref: Optional[str] = None
    please_vote_time: Optional[float] = None

    # Flatten to (start_time, text) for easy windowing
    entries = [(s["start"], s["text"]) for s in snippets]

    for i, (t, text) in enumerate(entries):
        # Look for case references
        for m in _CASE_REF_RE.finditer(text):
            ref = _normalize_ref(m.group(0))
            if ref and len(ref) >= 5:
                current_ref = ref

        # "Please vote" signals a vote is about to be called
        if _VOTE_RE.search(text):
            please_vote_time = t

        # "Motion carries / fails" — look within 30 seconds of "Please vote"
        carried = _CARRIES_RE.search(text)
        failed  = _FAILS_RE.search(text)

        if (carried or failed) and current_ref:
            # Gather context window: 10 seconds before to 10 seconds after
            window_texts = [
                e_text for e_t, e_text in entries
                if t - 10 <= e_t <= t + 10
            ]
            context = ' '.join(window_texts)

            passed = bool(carried)

            # Try to extract a spoken tally from the context
            ayes, nays = None, None
            tally_m = _SPOKEN_TALLY_RE.search(context)
            if tally_m:
                ayes = _parse_number(tally_m.group(1))
                nays = _parse_number(tally_m.group(2))

            # Named dissenters
            by_member = []
            for dm in _DISSENT_RE.finditer(context):
                name = dm.group(1).strip()
                by_member.append({"name": name, "district": "", "vote": "NAY"})

            # Don't overwrite a better (PDF-sourced) vote with a transcript one
            existing = item_votes.get(current_ref)
            if not existing or existing.get("source") == "youtube":
                item_votes[current_ref] = {
                    "ayes": ayes,
                    "nays": nays,
                    "abstain": 0,
                    "absent": None,
                    "passed": passed,
                    "by_member": by_member,
                    "districts": [],
                    "source": "youtube",
                }

    return item_votes


def get_video_list_for_dates(target_dates: list[str]) -> dict[str, dict]:
    """
    Return {iso_date: {video_id, title}} for each date that has a matching video.
    target_dates: list of ISO date strings "2025-06-24"
    """
    all_videos = _get_video_list()
    date_set = set(target_dates)
    return {
        v["date"]: v
        for v in all_videos
        if v["date"] in date_set
    }


def get_youtube_votes_for_date(meeting_date: str) -> Optional[dict[str, dict]]:
    """
    Find the YouTube video for a meeting date and parse vote data from its transcript.
    Returns {case_ref: vote_dict} or None if no video found.
    """
    videos = _get_video_list()
    video = next((v for v in videos if v["date"] == meeting_date), None)
    if not video:
        logger.info(f"No YouTube video found for {meeting_date}")
        return None

    logger.info(f"Fetching YouTube transcript for {meeting_date}: {video['video_id']} — {video['title']}")
    snippets = _fetch_transcript(video["video_id"])
    if not snippets:
        return None

    votes = _parse_transcript_for_votes(snippets)
    logger.info(f"YouTube transcript: {len(votes)} vote records for {meeting_date}")
    return votes if votes else None


def sync_youtube_votes(meeting_dates: list[str]) -> dict[str, dict]:
    """
    Batch-fetch YouTube transcripts for a list of meeting dates.
    Returns {meeting_date: {case_ref: vote_dict}}.
    """
    results: dict[str, dict] = {}
    video_map = get_video_list_for_dates(meeting_dates)

    for date, video in video_map.items():
        snippets = _fetch_transcript(video["video_id"])
        if snippets:
            votes = _parse_transcript_for_votes(snippets)
            if votes:
                results[date] = votes
                logger.info(f"{date}: {len(votes)} votes from YouTube ({video['video_id']})")

    return results
