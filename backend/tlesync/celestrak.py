"""CelesTrak-specific request and source validation safeguards."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import requests

CELESTRAK_HOST = "celestrak.org"
CELESTRAK_GP_PATH = "/NORAD/elements/gp.php"
CELESTRAK_CSV_FORMAT = "csv"
CELESTRAK_REQUEST_TIMEOUT_SECONDS = 20
CELESTRAK_RATE_LIMIT_SECONDS = 2 * 60 * 60
MAX_ERROR_RESPONSE_CHARS = 500

# CelesTrak's Current GP Element Sets catalogue is intentionally represented
# here rather than accepting a hand-written provider URL.  This lets users
# choose every documented GROUP while ensuring the application only constructs
# canonical GP/CSV requests.  Adding a choice does not enable or download it.
CELESTRAK_GROUPS = {
    "amateur": "Amateur radio",
    "active": "Active satellites",
    "analyst": "Analyst satellites",
    "argos": "ARGOS Data Collection System",
    "beidou": "BeiDou",
    "cosmos-2251-debris": "COSMOS 2251 debris",
    "cubesat": "CubeSats",
    "dmc": "Disaster Monitoring",
    "education": "Education",
    "engineering": "Engineering",
    "eutelsat": "Eutelsat",
    "fengyun-1c-debris": "Chinese ASAT Test Debris (FENGYUN 1C)",
    "galileo": "Galileo",
    "geodetic": "Geodetic",
    "geo": "Active geosynchronous",
    "globalstar": "Globalstar",
    "glo-ops": "GLONASS operational",
    "gnss": "GNSS",
    "gps-ops": "GPS operational",
    "hulianwang": "Hulianwang Digui",
    "intelsat": "Intelsat",
    "iridium-33-debris": "IRIDIUM 33 debris",
    "iridium-next": "Iridium NEXT",
    "kuiper": "Kuiper",
    "last-30-days": "Last 30 Days' Launches",
    "military": "Miscellaneous military",
    "oneweb": "OneWeb",
    "orbcomm": "ORBCOMM",
    "other-comm": "Other communications",
    "planet": "Planet",
    "qianfan": "Qianfan",
    "radar": "Radar calibration",
    "resource": "Earth resources",
    "sar": "Synthetic aperture radar",
    "satnogs": "SatNOGS",
    "sarsat": "Search & Rescue (SARSAT)",
    "sbas": "Satellite-based augmentation system (SBAS)",
    "science": "Space & Earth science",
    "ses": "SES",
    "spire": "Spire",
    "starlink": "Starlink",
    "stations": "Space stations",
    "tdrss": "Tracking and Data Relay Satellite System (TDRSS)",
    "telesat": "Telesat",
    "visual": "100 (or so) Brightest",
    "weather": "Weather",
    "x-comm": "Experimental communications",
}


class CelestrakRequestError(requests.RequestException):
    """A CelesTrak response that must suspend further automated requests."""

    def __init__(self, url: str, status_code: int, response_text: str = ""):
        self.url = url
        self.status_code = status_code
        self.response_summary = " ".join(response_text.split())[:MAX_ERROR_RESPONSE_CHARS]
        detail = f"CelesTrak returned HTTP {status_code} for {url}"
        if self.response_summary:
            detail = f"{detail}: {self.response_summary}"
        super().__init__(detail)


def is_celestrak_url(url: Any) -> bool:
    """Return whether a URL targets CelesTrak, including legacy host aliases."""
    hostname = (urlparse(str(url or "")).hostname or "").lower()
    return hostname in {
        "celestrak.org",
        "www.celestrak.org",
        "celestrak.com",
        "www.celestrak.com",
    }


def build_celestrak_gp_url(group: str) -> str:
    """Build the one canonical GP/CSV endpoint for an allowed source group."""
    normalized_group = str(group or "").strip().lower()
    if normalized_group not in CELESTRAK_GROUPS:
        raise ValueError(
            "Choose a supported CelesTrak group: " + ", ".join(sorted(CELESTRAK_GROUPS))
        )
    return f"https://{CELESTRAK_HOST}{CELESTRAK_GP_PATH}?" + urlencode(
        {"GROUP": normalized_group, "FORMAT": "CSV"}
    )


def celestrak_group_from_url(url: str) -> Optional[str]:
    """Return the allowlisted group encoded by a canonical CelesTrak URL."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    group = query.get("GROUP", [""])[0].strip().lower()
    if group in CELESTRAK_GROUPS:
        return group
    return None


def validate_celestrak_source(url: str, source_format: str, adapter: str) -> None:
    """Reject CelesTrak source settings that violate the documented GP contract."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or hostname != CELESTRAK_HOST:
        raise ValueError("CelesTrak sources must use https://celestrak.org")
    if parsed.path.lower() != CELESTRAK_GP_PATH.lower():
        raise ValueError("CelesTrak sources must use the documented GP gp.php endpoint")

    query = parse_qs(parsed.query, keep_blank_values=True)
    group = celestrak_group_from_url(url)
    if group is None:
        raise ValueError(
            "CelesTrak sources must use a supported group selected in the source editor"
        )
    if query.get("FORMAT", [""])[0].lower() != CELESTRAK_CSV_FORMAT:
        raise ValueError("CelesTrak sources must request FORMAT=CSV")
    if url != build_celestrak_gp_url(group):
        raise ValueError("CelesTrak sources must use the canonical GP/CSV URL")
    if source_format.lower() != "omm" or adapter.lower() != "http_omm":
        raise ValueError("CelesTrak CSV sources must use the OMM-compatible parser")


def get_celestrak_gp(url: str) -> requests.Response:
    """Fetch one GP response without following redirects or accepting non-200s."""
    response = requests.get(
        url,
        timeout=CELESTRAK_REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    if response.status_code != 200:
        raise CelestrakRequestError(url, response.status_code, response.text)
    return response


def celestrak_error_details(error: BaseException) -> Dict[str, Any]:
    """Produce UI-safe persistent error data for an intercepted CelesTrak failure."""
    if isinstance(error, CelestrakRequestError):
        return {
            "http_status": error.status_code,
            "reason": str(error),
        }
    return {"http_status": None, "reason": str(error)}
