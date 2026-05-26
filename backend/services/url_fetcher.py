"""
Fetch a Fort Worth agenda PDF from a public URL.

Uses httpx with a browser-like User-Agent and a 30-second timeout.
Returns raw bytes on success; raises HTTPException on failure.
"""

import httpx
from fastapi import HTTPException

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}

_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
_TIMEOUT = 30.0


def fetch_pdf_from_url(url: str) -> tuple[bytes, str]:
    """
    Download a PDF from *url*.

    Returns (pdf_bytes, suggested_filename).
    Raises fastapi.HTTPException on any error.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
            resp = client.get(url, headers=_HEADERS)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Request timed out fetching: {url}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach URL: {exc}")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Server returned {resp.status_code} for {url}",
        )

    content_type = resp.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"URL does not appear to return a PDF "
                f"(Content-Type: {content_type}). "
                "Paste the direct link to the PDF file."
            ),
        )

    data = resp.content
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="PDF exceeds 50 MB size limit.")
    if len(data) < 1024:
        raise HTTPException(status_code=400, detail="Downloaded file is too small to be a valid PDF.")

    # Derive a filename from the URL path
    path_part = url.rstrip("/").split("/")[-1]
    filename = path_part if path_part.lower().endswith(".pdf") else "agenda.pdf"

    return data, filename
