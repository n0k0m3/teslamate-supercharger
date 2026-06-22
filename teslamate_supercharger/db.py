"""PostgreSQL connection pool, schema migration, and all query functions."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from .config import Config

logger = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None


def init_pool(cfg: Config) -> None:
    global _pool
    _pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=cfg.db_host,
        port=cfg.db_port,
        dbname=cfg.db_name,
        user=cfg.db_user,
        password=cfg.db_pass,
    )
    logger.info("Database connection pool initialized (%s:%s/%s)", cfg.db_host, cfg.db_port, cfg.db_name)


@contextmanager
def get_conn():
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS supercharger_sessions (
    id                       BIGSERIAL PRIMARY KEY,
    car_id                   INTEGER NOT NULL,
    tesla_session_id         TEXT UNIQUE,
    session_date             TIMESTAMPTZ,
    supercharger_name        TEXT,
    supercharger_location_id TEXT,
    energy_kwh               DOUBLE PRECISION,
    cost_amount              DOUBLE PRECISION,
    cost_currency            TEXT,
    duration_minutes         INTEGER,
    raw_data                 JSONB,
    charging_process_id      INTEGER REFERENCES charging_processes(id),
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE charging_processes
    ADD COLUMN IF NOT EXISTS cost DOUBLE PRECISION;
"""


def ensure_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
    logger.info("Schema verified/migrated")


def get_encrypted_tokens(conn) -> tuple[bytes, bytes]:
    with conn.cursor() as cur:
        cur.execute("SELECT access, refresh FROM private.tokens LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("No token row found in private.tokens")
    return bytes(row[0]), bytes(row[1])


def get_car_vins(conn) -> dict[int, str]:
    """Returns {car_id: vin} for all cars."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, vin FROM cars WHERE vin IS NOT NULL")
        return {row[0]: row[1] for row in cur.fetchall()}


def find_charging_process(
    conn,
    car_id: int,
    end_time: datetime,
    window_minutes: int,
) -> Optional[int]:
    window = timedelta(minutes=window_minutes)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM charging_processes
            WHERE car_id = %s
              AND end_date BETWEEN %s AND %s
            ORDER BY ABS(EXTRACT(EPOCH FROM (end_date - %s)))
            LIMIT 1
            """,
            (car_id, end_time - window, end_time + window, end_time),
        )
        row = cur.fetchone()
    return row[0] if row else None


def upsert_supercharger_session(
    conn,
    *,
    car_id: int,
    tesla_session_id: Optional[str],
    session_date: Optional[datetime],
    supercharger_name: Optional[str],
    supercharger_location_id: Optional[str],
    energy_kwh: Optional[float],
    cost_amount: Optional[float],
    cost_currency: Optional[str],
    duration_minutes: Optional[int],
    raw_data: dict,
    charging_process_id: Optional[int],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO supercharger_sessions (
                car_id, tesla_session_id, session_date, supercharger_name,
                supercharger_location_id, energy_kwh, cost_amount, cost_currency,
                duration_minutes, raw_data, charging_process_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tesla_session_id) DO NOTHING
            """,
            (
                car_id,
                tesla_session_id,
                session_date,
                supercharger_name,
                supercharger_location_id,
                energy_kwh,
                cost_amount,
                cost_currency,
                duration_minutes,
                json.dumps(raw_data),
                charging_process_id,
            ),
        )


def update_charging_process_cost(conn, charging_process_id: int, cost: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE charging_processes SET cost = %s WHERE id = %s",
            (cost, charging_process_id),
        )


def get_uncosted_supercharger_processes(
    conn,
    lookback_hours: int = 24,
) -> list[tuple[int, int, datetime]]:
    """
    Return (car_id, charging_process_id, end_date) for recent fast-charger
    sessions where cost is still NULL. Used for startup backfill.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT car_id, id, end_date
            FROM charging_processes
            WHERE end_date > %s
              AND cost IS NULL
              AND end_date IS NOT NULL
            ORDER BY end_date DESC
            """,
            (cutoff,),
        )
        return cur.fetchall()
