"""Match Tesla API charging sessions to TeslaMate charging_processes rows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Field name constants — adjust here if the API returns different names.
# Log the raw response on first run (tesla_api.py does this at DEBUG level).
_FIELD_SESSION_ID = "chargeSessionId"
_FIELD_STOP_TIME = "chargeStopDateTime"
_FIELD_START_TIME = "chargeStartDateTime"
_FIELD_SITE_NAME = "siteLocationName"
_FIELD_LOCATION_ID = "siteId"
_FIELD_FEES = "fees"
_FIELD_FEE_TYPE = "feeType"
_FIELD_FEE_TOTAL = "totalDue"
_FIELD_FEE_CURRENCY = "currencyCode"
_FIELD_PACKAGE = "chargingPackage"
_FIELD_ENERGY = "energyKwh"

_BILLABLE_FEE_TYPES = {"CHARGING", "PARKING"}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def find_matching_session(
    sessions: list[dict],
    trigger_time: datetime,
    window_minutes: int,
) -> Optional[dict]:
    """
    Return the session whose stop time falls within window_minutes of trigger_time.
    Picks the session with the stop time closest to trigger_time.
    """
    if trigger_time.tzinfo is None:
        trigger_time = trigger_time.replace(tzinfo=timezone.utc)

    window = timedelta(minutes=window_minutes)
    best = None
    best_delta = None

    for s in sessions:
        stop = _parse_dt(s.get(_FIELD_STOP_TIME))
        if stop is None:
            continue
        delta = abs((stop - trigger_time).total_seconds())
        if delta <= window.total_seconds():
            if best_delta is None or delta < best_delta:
                best = s
                best_delta = delta

    if best is None:
        logger.warning(
            "No matching charging session found within %d minutes of %s "
            "(checked %d sessions)",
            window_minutes,
            trigger_time.isoformat(),
            len(sessions),
        )
    return best


def extract_cost(session: dict) -> tuple[Optional[float], Optional[str]]:
    """Return (total_cost, currency_code) summing CHARGING + PARKING fees."""
    total = 0.0
    currency: Optional[str] = None
    for fee in session.get(_FIELD_FEES, []):
        if fee.get(_FIELD_FEE_TYPE) in _BILLABLE_FEE_TYPES:
            total += fee.get(_FIELD_FEE_TOTAL, 0.0)
            if currency is None:
                currency = fee.get(_FIELD_FEE_CURRENCY)
    return (total if total > 0 else None, currency)


def extract_session_fields(session: dict) -> dict:
    """Extract structured fields from a raw API session dict."""
    stop = _parse_dt(session.get(_FIELD_STOP_TIME))
    start = _parse_dt(session.get(_FIELD_START_TIME))
    duration = None
    if start and stop:
        duration = int((stop - start).total_seconds() / 60)

    cost_amount, cost_currency = extract_cost(session)

    pkg = session.get(_FIELD_PACKAGE) or {}
    energy_kwh = pkg.get(_FIELD_ENERGY)

    return {
        "tesla_session_id": session.get(_FIELD_SESSION_ID),
        "session_date": stop,
        "supercharger_name": session.get(_FIELD_SITE_NAME),
        "supercharger_location_id": str(session.get(_FIELD_LOCATION_ID)) if session.get(_FIELD_LOCATION_ID) else None,
        "energy_kwh": energy_kwh,
        "cost_amount": cost_amount,
        "cost_currency": cost_currency,
        "duration_minutes": duration,
    }
