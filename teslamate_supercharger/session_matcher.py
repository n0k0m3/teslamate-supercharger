"""Match Tesla API charging sessions to TeslaMate charging_processes rows."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Fleet API field name constants.
_FIELD_SESSION_ID = "sessionId"
_FIELD_STOP_TIME = "chargeStopDateTime"
_FIELD_START_TIME = "chargeStartDateTime"
_FIELD_SITE_NAME = "siteLocationName"
_FIELD_VIN = "vin"
_FIELD_FEES = "fees"
_FIELD_FEE_TYPE = "feeType"
_FIELD_FEE_TOTAL = "totalDue"
_FIELD_FEE_CURRENCY = "currencyCode"
_FIELD_FEE_USAGE = "usageBase"
_FIELD_FEE_UOM = "uom"

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


def extract_energy_kwh(session: dict) -> Optional[float]:
    """Return kWh delivered, summed from CHARGING fee usageBase."""
    total = 0.0
    for fee in session.get(_FIELD_FEES, []):
        if fee.get(_FIELD_FEE_TYPE) == "CHARGING" and fee.get(_FIELD_FEE_UOM) == "kwh":
            total += fee.get(_FIELD_FEE_USAGE, 0.0)
    return total if total > 0 else None


def extract_session_fields(session: dict) -> dict:
    """Extract structured fields from a raw Fleet API session dict."""
    stop = _parse_dt(session.get(_FIELD_STOP_TIME))
    start = _parse_dt(session.get(_FIELD_START_TIME))
    duration = None
    if start and stop:
        duration = int((stop - start).total_seconds() / 60)

    cost_amount, cost_currency = extract_cost(session)

    return {
        "tesla_session_id": str(session.get(_FIELD_SESSION_ID)) if session.get(_FIELD_SESSION_ID) else None,
        "session_date": stop,
        "supercharger_name": session.get(_FIELD_SITE_NAME),
        "supercharger_location_id": None,
        "energy_kwh": extract_energy_kwh(session),
        "cost_amount": cost_amount,
        "cost_currency": cost_currency,
        "duration_minutes": duration,
    }
