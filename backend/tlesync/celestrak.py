"""CelesTrak-specific request and source validation safeguards."""

from __future__ import annotations

from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

import requests

CELESTRAK_HOST = "celestrak.org"
CELESTRAK_GP_PATH = "/norad/elements/gp.php"
CELESTRAK_CSV_FORMAT = "csv"
CELESTRAK_REQUEST_TIMEOUT_SECONDS = 20
CELESTRAK_RATE_LIMIT_SECONDS = 2 * 60 * 60
MAX_ERROR_RESPONSE_CHARS = 500


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


def validate_celestrak_source(url: str, source_format: str, adapter: str) -> None:
    """Reject CelesTrak source settings that violate the documented GP contract."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or hostname != CELESTRAK_HOST:
        raise ValueError("CelesTrak sources must use https://celestrak.org")
    if parsed.path.lower() != CELESTRAK_GP_PATH:
        raise ValueError("CelesTrak sources must use the documented GP gp.php endpoint")

    query = parse_qs(parsed.query, keep_blank_values=True)
    if not {"GROUP", "CATNR", "INTDES", "NAME", "SPECIAL"}.intersection(query):
        raise ValueError("CelesTrak GP sources require a documented query selector")
    if query.get("FORMAT", [""])[0].lower() != CELESTRAK_CSV_FORMAT:
        raise ValueError("CelesTrak sources must request FORMAT=CSV")
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
