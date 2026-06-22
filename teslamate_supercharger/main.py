"""
teslamate-supercharger daemon entry point.

Startup sequence:
1. Load config from env
2. Init DB pool, run schema migration
3. Acquire Fleet API access token (client_credentials)
4. Load car VINs from TeslaMate DB
5. Backfill any recent missed sessions
6. Start MQTT listener (blocks forever)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from . import db, session_matcher
from .config import Config, ConfigError
from .mqtt_client import MQTTClient
from .tesla_api import TeslaAPIError, TokenExpiredError, fetch_charging_history, get_fleet_access_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.fleet_access_token: Optional[str] = None
        self.car_vins: dict[int, str] = {}
        self._executor = ThreadPoolExecutor(max_workers=2)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _init_fleet_token(self) -> None:
        self.fleet_access_token = get_fleet_access_token(
            self.cfg.tesla_client_id,
            self.cfg.tesla_client_secret,
            self.cfg.tesla_fleet_region,
        )

    def _load_car_vins(self) -> None:
        with db.get_conn() as conn:
            self.car_vins = db.get_car_vins(conn)
        if not self.car_vins:
            logger.warning("No cars found in TeslaMate database")
        else:
            logger.info("Cars loaded: %s", {cid: vin[:8] + "***" for cid, vin in self.car_vins.items()})

    def _backfill(self) -> None:
        """Fetch history for any recent Supercharger sessions still missing cost."""
        with db.get_conn() as conn:
            rows = db.get_uncosted_supercharger_processes(conn, lookback_hours=24)
        if not rows:
            logger.info("Backfill: no uncosted recent sessions found")
            return
        logger.info("Backfill: %d uncosted session(s) found — fetching...", len(rows))
        seen_car_ids: set[int] = set()
        for car_id, cp_id, end_date in rows:
            if car_id not in seen_car_ids:
                seen_car_ids.add(car_id)
                self._fetch_and_store(car_id, trigger_time=end_date, charging_process_hint=cp_id)

    # ------------------------------------------------------------------
    # Session fetch + store (runs in thread pool)
    # ------------------------------------------------------------------

    def _fetch_sessions(self) -> list[dict]:
        """Fetch charging history, re-acquiring the token once on 401."""
        try:
            return fetch_charging_history(self.fleet_access_token, self.cfg.tesla_fleet_region)
        except TokenExpiredError:
            logger.info("Fleet token expired, re-acquiring...")
            self._init_fleet_token()
            return fetch_charging_history(self.fleet_access_token, self.cfg.tesla_fleet_region)

    def _fetch_and_store(
        self,
        car_id: int,
        trigger_time: Optional[datetime] = None,
        charging_process_hint: Optional[int] = None,
    ) -> None:
        if trigger_time is None:
            trigger_time = datetime.now(tz=timezone.utc)

        vin = self.car_vins.get(car_id)
        if not vin:
            logger.error("Car %d: VIN not found, cannot fetch charging history", car_id)
            return

        try:
            all_sessions = self._fetch_sessions()
        except TeslaAPIError as exc:
            logger.error("Car %d: API error fetching charging history: %s", car_id, exc)
            return

        sessions = [s for s in all_sessions if s.get("vin") == vin]
        if not sessions:
            logger.warning("Car %d: no charging sessions found for VIN %s", car_id, vin[:8] + "***")
            return

        session = session_matcher.find_matching_session(
            sessions, trigger_time, self.cfg.session_match_window_minutes
        )
        if session is None:
            return

        fields = session_matcher.extract_session_fields(session)
        logger.info(
            "Car %d: matched session %s at %s (cost=%s %s, energy=%.1f kWh)",
            car_id,
            fields["tesla_session_id"],
            fields["session_date"],
            fields["cost_amount"],
            fields["cost_currency"],
            fields["energy_kwh"] or 0,
        )

        cp_id = charging_process_hint
        if cp_id is None and fields["session_date"]:
            with db.get_conn() as conn:
                cp_id = db.find_charging_process(
                    conn,
                    car_id,
                    fields["session_date"],
                    self.cfg.session_match_window_minutes,
                )

        with db.get_conn() as conn:
            db.upsert_supercharger_session(
                conn,
                car_id=car_id,
                charging_process_id=cp_id,
                raw_data=session,
                **fields,
            )
            if fields["cost_amount"] is not None and cp_id is not None:
                db.update_charging_process_cost(conn, cp_id, fields["cost_amount"])
                logger.info("Car %d: updated charging_processes id=%d with cost=%.2f %s",
                            car_id, cp_id, fields["cost_amount"], fields["cost_currency"])

    def _on_supercharge_complete(self, car_id: int) -> None:
        delay = self.cfg.api_fetch_delay_seconds
        trigger_time = datetime.now(tz=timezone.utc)

        def _work():
            if delay:
                logger.debug("Car %d: waiting %ds before API fetch", car_id, delay)
                time.sleep(delay)
            self._fetch_and_store(car_id, trigger_time=trigger_time)

        self._executor.submit(_work)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        logger.info("teslamate-supercharger starting up")

        db.init_pool(self.cfg)
        db.ensure_schema()

        self._init_fleet_token()
        self._load_car_vins()
        self._backfill()

        mqtt = MQTTClient(
            host=self.cfg.mqtt_host,
            port=self.cfg.mqtt_port,
            username=self.cfg.mqtt_username,
            password=self.cfg.mqtt_password,
            on_supercharge_complete=self._on_supercharge_complete,
        )
        mqtt.start()  # blocks


def main() -> None:
    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1)

    Daemon(cfg).run()


if __name__ == "__main__":
    main()
