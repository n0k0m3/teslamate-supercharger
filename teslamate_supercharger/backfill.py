"""
One-shot backfill of all Fleet API charging history into TeslaMate DB.

Usage:
    uv run python -m teslamate_supercharger.backfill

Fetches every page of charging history for all vehicles on the account and
upserts into supercharger_sessions + charging_processes.cost. Safe to re-run.
"""

from __future__ import annotations

import logging

from . import db, session_matcher
from .config import Config, ConfigError
from .tesla_api import TeslaAPIError, fetch_all_charging_history, get_fleet_access_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run(cfg: Config) -> None:
    db.init_pool(cfg)
    db.ensure_schema()

    access_token = get_fleet_access_token(
        cfg.tesla_client_id, cfg.tesla_client_secret, cfg.tesla_fleet_region
    )

    with db.get_conn() as conn:
        car_vins = db.get_car_vins(conn)
    vin_to_car_id = {vin: car_id for car_id, vin in car_vins.items()}
    logger.info("Cars: %s", {car_id: vin[:8] + "***" for car_id, vin in car_vins.items()})

    try:
        sessions = fetch_all_charging_history(access_token, cfg.tesla_fleet_region)
    except TeslaAPIError as exc:
        logger.error("Failed to fetch charging history: %s", exc)
        raise SystemExit(1)

    logger.info("Processing %d sessions...", len(sessions))

    written = skipped = 0
    for session in sessions:
        vin = session.get("vin")
        car_id = vin_to_car_id.get(vin)
        if car_id is None:
            logger.debug("No car found for VIN %s, skipping", vin)
            skipped += 1
            continue

        fields = session_matcher.extract_session_fields(session)
        if fields["session_date"] is None:
            skipped += 1
            continue

        with db.get_conn() as conn:
            cp_id = db.find_charging_process(
                conn, car_id, fields["session_date"], cfg.session_match_window_minutes
            )
            db.upsert_supercharger_session(
                conn,
                car_id=car_id,
                charging_process_id=cp_id,
                raw_data=session,
                **fields,
            )
            if fields["cost_amount"] is not None and cp_id is not None:
                db.update_charging_process_cost(conn, cp_id, fields["cost_amount"])

        written += 1

    logger.info("Backfill complete: %d written, %d skipped", written, skipped)


def main() -> None:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1)

    run(cfg)


if __name__ == "__main__":
    main()
