"""Tesla Fleet API charging history client."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

_FLEET_BASE = "https://fleet-api.prd.{region}.vn.cloud.tesla.com"
_HISTORY_PATH = "/api/1/dx/charging/history"
_FLEET_AUTH_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
_FLEET_SCOPES = "openid vehicle_device_data vehicle_cmds vehicle_charging_cmds"


class TokenExpiredError(Exception):
    pass


class TeslaAPIError(Exception):
    pass


def get_fleet_access_token(client_id: str, client_secret: str, region: str) -> str:
    """Acquire a Fleet API access token via client_credentials grant."""
    audience = _FLEET_BASE.format(region=region)
    resp = requests.post(
        _FLEET_AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": _FLEET_SCOPES,
            "audience": audience,
        },
        timeout=30,
    )
    if not resp.ok:
        raise TeslaAPIError(f"Fleet token request failed: {resp.status_code} {resp.text[:200]}")
    token = resp.json()["access_token"]
    logger.info("Fleet API access token acquired")
    return token


def fetch_charging_history(
    access_token: str,
    region: str = "na",
    page_no: int = 1,
    page_size: int = 10,
) -> list[dict]:
    """
    Fetch one page of charging sessions via Tesla Fleet API.

    Returns a list of raw session dicts for all vehicles on the account.
    Raises TokenExpiredError on 401 so the caller can re-acquire and retry.
    """
    url = _FLEET_BASE.format(region=region) + _HISTORY_PATH
    resp = requests.get(
        url,
        params={"pageNo": page_no, "pageSize": page_size},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    if resp.status_code == 401:
        raise TokenExpiredError("Fleet access token expired")

    if not resp.ok:
        raise TeslaAPIError(f"Charging history fetch failed: {resp.status_code} {resp.text[:200]}")

    logger.debug("Raw charging history response: %s", resp.text[:500])
    return resp.json().get("data", [])


def fetch_all_charging_history(
    access_token: str,
    region: str = "na",
    page_size: int = 50,
) -> list[dict]:
    """Fetch all pages of charging history, returning every session."""
    all_sessions: list[dict] = []
    page = 1
    while True:
        batch = fetch_charging_history(access_token, region, page_no=page, page_size=page_size)
        if not batch:
            break
        all_sessions.extend(batch)
        logger.info("Fleet API: fetched page %d (%d sessions so far)", page, len(all_sessions))
        if len(batch) < page_size:
            break
        page += 1
    return all_sessions
