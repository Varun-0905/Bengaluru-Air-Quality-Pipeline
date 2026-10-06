"""Database helpers: connection with retry (Neon cold starts), schema init, run log."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import psycopg2
from psycopg2.extras import Json, execute_values
from sqlalchemy import create_engine

from . import config

log = logging.getLogger(__name__)


def connect(attempts: int = 3):
    """Neon pauses idle compute; the first connection can be slow or fail once."""
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return psycopg2.connect(config.database_url(), connect_timeout=30)
        except psycopg2.OperationalError as exc:
            last = exc
            log.warning("DB connect attempt %d/%d failed", attempt, attempts)
            time.sleep(3 * attempt)
    raise last  # type: ignore[misc]


def engine():
    url = config.database_url().replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)


def init_schema(conn) -> None:
    """Idempotent: every statement is CREATE ... IF NOT EXISTS."""
    with conn.cursor() as cur:
        cur.execute((config.SQL_DIR / "create_tables.sql").read_text())
    conn.commit()


def sync_locations(conn) -> None:
    rows = [(l["location_id"], l["name"], l["latitude"], l["longitude"]) for l in config.LOCATIONS]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO locations (location_id, name, latitude, longitude) VALUES %s
               ON CONFLICT (location_id) DO UPDATE
               SET name = EXCLUDED.name, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude""",
            rows,
        )
    conn.commit()


def start_run(conn, started: datetime) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_runs (started_at, status) VALUES (%s, 'running') RETURNING run_id",
            (started,),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str, stats: dict, error: str | None, checks: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE pipeline_runs
               SET finished_at = now(), status = %s, rows_fetched = %s, rows_inserted = %s,
                   rows_updated = %s, error_message = %s, checks = %s
               WHERE run_id = %s""",
            (status, stats["rows_fetched"], stats["rows_inserted"], stats["rows_updated"],
             error, Json(checks), run_id),
        )
    conn.commit()
