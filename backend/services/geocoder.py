"""
Address geocoder using the US Census Bureau's free geocoding API.
No API key required. Returns lat/lng for US addresses.
"""
import logging
import math
import re
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/address"
_TIMEOUT = 10.0

# In-memory cache for the current process session
_cache: dict[str, Optional[Tuple[float, float]]] = {}


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Geocode an address string to (lat, lng) using the Census Bureau geocoder.
    Returns None if the address cannot be geocoded.
    """
    if not address or not address.strip():
        return None

    clean = _clean_for_census(address)
    if clean in _cache:
        return _cache[clean]

    result = _query_census(clean)
    _cache[clean] = result
    return result


def _clean_for_census(address: str) -> str:
    """Strip trailing Fort Worth/TX/zip if present; Census takes structured or freeform."""
    # Normalize whitespace
    addr = re.sub(r"\s+", " ", address.strip())
    return addr


def _query_census(address: str) -> Optional[Tuple[float, float]]:
    """Query Census geocoder. Returns (lat, lng) or None."""
    try:
        # Try to split into street / city / state
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 2:
            street = parts[0]
            city = parts[1] if len(parts) > 1 else "Fort Worth"
            state = "TX"
        else:
            street = address
            city = "Fort Worth"
            state = "TX"

        params = {
            "street": street,
            "city": city,
            "state": state,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        resp = httpx.get(_CENSUS_URL, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json()
        matches = (
            data.get("result", {})
                .get("addressMatches", [])
        )
        if not matches:
            # Retry with freeform
            return _query_census_freeform(address)

        coords = matches[0].get("coordinates", {})
        lat = coords.get("y")
        lng = coords.get("x")
        if lat is not None and lng is not None:
            return (float(lat), float(lng))
        return None
    except Exception as exc:
        logger.debug("Census geocoder failed for %s: %s", address, exc)
        return None


def _query_census_freeform(address: str) -> Optional[Tuple[float, float]]:
    """Freeform Census geocoder endpoint."""
    try:
        params = {
            "address": f"{address}, Fort Worth, TX",
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        resp = httpx.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params=params,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        coords = matches[0].get("coordinates", {})
        lat = coords.get("y")
        lng = coords.get("x")
        if lat is not None and lng is not None:
            return (float(lat), float(lng))
        return None
    except Exception as exc:
        logger.debug("Census freeform geocoder failed for %s: %s", address, exc)
        return None


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two lat/lng points in miles using the Haversine formula.
    """
    R = 3_958.8  # Earth radius in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
