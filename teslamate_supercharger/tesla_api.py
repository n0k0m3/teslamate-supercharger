"""Tesla charging history API client with token refresh support."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_HISTORY_URL = "https://www.tesla.com/teslaaccount/charging/api/history"
_TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "X-Tesla-User-Agent": "TeslaApp/4.36.0",
    "Content-Type": "application/json",
    "Origin": "https://www.tesla.com",
    "Referer": "https://www.tesla.com/teslaaccount/charging",
}


class TokenExpiredError(Exception):
    pass


class TeslaAPIError(Exception):
    pass


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Return (new_access_token, new_refresh_token)."""
    resp = requests.post(
        _TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "client_id": "ownerapi",
            "refresh_token": refresh_token,
            "scope": "openid email offline_access",
        },
        headers=_HEADERS,
        timeout=30,
    )
    if not resp.ok:
        raise TeslaAPIError(f"Token refresh failed: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    new_access = data["access_token"]
    new_refresh = data.get("refresh_token", refresh_token)
    logger.info("Access token refreshed successfully")
    return new_access, new_refresh


def fetch_charging_history(
    access_token: str,
    vin: str,
    page_size: int = 5,
) -> list[dict]:
    """
    Fetch the most recent charging sessions for the given VIN.

    Returns a list of raw session dicts from the API. Field names are logged
    on first call so callers can verify the schema against session_matcher.py.
    Raises TokenExpiredError on 401 so callers can refresh and retry.
    """
    resp = requests.get(
        _HISTORY_URL,
        params={"vin": vin, "pageNo": 1, "pageSize": page_size},
        headers={**_HEADERS, "Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    if resp.status_code == 401:
        raise TokenExpiredError("Access token is expired")

    if resp.status_code == 404:
        logger.warning(
            "Charging history endpoint returned 404. "
            "The endpoint URL may have changed — check for a GraphQL alternative."
        )
        return []

    if not resp.ok:
        raise TeslaAPIError(f"Charging history fetch failed: {resp.status_code} {resp.text[:200]}")

    payload = resp.json()
    logger.debug("Raw charging history response: %s", payload)

    sessions = payload.get("data", payload if isinstance(payload, list) else [])
    if sessions:
        logger.debug("Charging session keys: %s", list(sessions[0].keys()))

    return sessions


def fetch_charging_history_with_refresh(
    access_token: str,
    refresh_token: str,
    vin: str,
) -> tuple[list[dict], str, str]:
    """
    Fetch charging history, transparently refreshing the access token on 401.

    Returns (sessions, current_access_token, current_refresh_token).
    The returned tokens may differ from the inputs if a refresh occurred.
    """
    try:
        sessions = fetch_charging_history(access_token, vin)
        return sessions, access_token, refresh_token
    except TokenExpiredError:
        logger.info("Access token expired, refreshing...")
        new_access, new_refresh = refresh_access_token(refresh_token)
        sessions = fetch_charging_history(new_access, vin)
        return sessions, new_access, new_refresh
