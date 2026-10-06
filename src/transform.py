"""Transform (ELT): build clean_hourly inside the database from the raw tables."""
from __future__ import annotations

import pandas as pd

from . import config


def aqi_case_sql(col: str = "a.us_aqi") -> str:
    """CASE expression generated from config.AQI_BANDS so SQL and Python never drift apart."""
    parts = [f"WHEN {col} IS NULL THEN NULL"]
    for upper, label in config.AQI_BANDS:
        parts.append(f"WHEN {col} <= {upper} THEN '{label}'" if upper is not None else f"ELSE '{label}'")
    return "CASE " + " ".join(parts) + " END"


def build_sql() -> str:
    return (config.SQL_DIR / "clean_hourly.sql").read_text().replace("{{AQI_CASE}}", aqi_case_sql())


def build_clean(conn, since: pd.Timestamp) -> int:
    """Upsert clean rows for the refresh window. Safe to re-run."""
    with conn.cursor() as cur:
        cur.execute(build_sql(), {"since": since.to_pydatetime()})
        return cur.rowcount
