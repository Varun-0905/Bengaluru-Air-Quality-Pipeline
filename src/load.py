"""Load: batch upserts. Idempotent, and unchanged rows are not rewritten."""
from __future__ import annotations

import pandas as pd
from psycopg2.extras import execute_values

from . import config


def _upsert_sql(table: str, cols: list[str]) -> str:
    all_cols = ["location_id", "ts", *cols]
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    old = ", ".join(f"{table}.{c}" for c in cols)
    new = ", ".join(f"EXCLUDED.{c}" for c in cols)
    return (
        f"INSERT INTO {table} ({', '.join(all_cols)}) VALUES %s "
        f"ON CONFLICT (location_id, ts) DO UPDATE SET {sets}, ingested_at = now() "
        f"WHERE ({old}) IS DISTINCT FROM ({new}) "
        f"RETURNING (xmax = 0) AS inserted"
    )


def _rows(df: pd.DataFrame, cols: list[str]) -> list[tuple]:
    sub = df[["location_id", *cols]]
    body = sub.astype(object).where(sub.notna(), None)  # NaN -> NULL
    ts = df["ts"].dt.to_pydatetime()
    return [(r[0], t, *r[1:]) for r, t in zip(body.itertuples(index=False, name=None), ts)]


def _upsert(conn, table: str, df: pd.DataFrame, cols: list[str]) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    with conn.cursor() as cur:
        out = execute_values(cur, _upsert_sql(table, cols), _rows(df, cols), page_size=1000, fetch=True)
    inserted = sum(1 for (flag,) in out if flag)
    return inserted, len(out) - inserted  # (new rows, changed rows); unchanged rows are skipped


def upsert_air(conn, df: pd.DataFrame) -> tuple[int, int]:
    return _upsert(conn, "raw_air_quality", df, config.AIR_COLS)


def upsert_weather(conn, df: pd.DataFrame) -> tuple[int, int]:
    return _upsert(conn, "raw_weather", df, config.WEATHER_COLS)
