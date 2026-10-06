"""The six data-quality checks (schema, nulls, range, duplicates, freshness, volume)."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from . import config


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def expected_rows(now: pd.Timestamp, past_days: int, n_locations: int) -> int:
    """Hours from 00:00 UTC of (today - past_days) up to and including `now`, per location."""
    start = (now - pd.Timedelta(days=past_days)).normalize()
    hours = int((now - start) / pd.Timedelta(hours=1)) + 1
    return hours * n_locations


def check_schema(df: pd.DataFrame, table: str, cols: list[str]) -> CheckResult:
    missing = [c for c in ["location_id", "ts", *cols] if c not in df.columns]
    return CheckResult(f"{table}.schema", not missing, "ok" if not missing else f"missing columns {missing}")


def check_nulls(df: pd.DataFrame, table: str, cols: list[str], max_pct: float) -> CheckResult:
    name = f"{table}.nulls"
    if df.empty:
        return CheckResult(name, False, "no rows")
    pct = df[cols].isna().mean() * 100
    bad = {c: round(float(p), 1) for c, p in pct.items() if p > max_pct}
    return CheckResult(name, not bad, "ok" if not bad else f"null % above {max_pct}: {bad}")


def check_ranges(df: pd.DataFrame, table: str, cols: list[str]) -> CheckResult:
    bad = {}
    for c in cols:
        lo, hi = config.RANGES[c]
        n = int(((df[c] < lo) | (df[c] > hi)).sum())
        if n:
            bad[c] = n
    return CheckResult(f"{table}.range", not bad, "ok" if not bad else f"out-of-range rows: {bad}")


def check_duplicates(df: pd.DataFrame, table: str) -> CheckResult:
    n = int(df.duplicated(["location_id", "ts"]).sum())
    return CheckResult(f"{table}.duplicates", n == 0, "ok" if n == 0 else f"{n} duplicate (location_id, ts) rows")


def check_freshness(df: pd.DataFrame, table: str, key_col: str, now: pd.Timestamp,
                    expected_ids: list[int], max_age_hours: float) -> CheckResult:
    """Freshness uses the newest NON-NULL value, so an API returning empty recent hours is caught."""
    latest = df.dropna(subset=[key_col]).groupby("location_id")["ts"].max().reindex(expected_ids)
    limit = pd.Timedelta(hours=max_age_hours)
    stale = [int(i) for i, ts in latest.items() if pd.isna(ts) or (now - ts) > limit]
    return CheckResult(f"{table}.freshness", not stale,
                       "ok" if not stale else f"stale/missing for location_ids {stale} (> {max_age_hours}h)")


def check_volume(df: pd.DataFrame, table: str, expected: int) -> CheckResult:
    n = len(df)
    lo, hi = expected * config.MIN_VOLUME_RATIO, expected * config.MAX_VOLUME_RATIO
    return CheckResult(f"{table}.volume", lo <= n <= hi, f"{n} rows, expected ~{expected}")


def run_all(air: pd.DataFrame, weather: pd.DataFrame, n_locations: int, past_days: int,
            now: pd.Timestamp) -> list[CheckResult]:
    expected = expected_rows(now, past_days, n_locations)
    ids = [l["location_id"] for l in config.LOCATIONS][:n_locations]
    results: list[CheckResult] = []
    for table, df, cols, key in (
        ("air", air, config.AIR_COLS, "pm2_5"),
        ("weather", weather, config.WEATHER_COLS, "temperature"),
    ):
        schema = check_schema(df, table, cols)
        results.append(schema)
        if not schema.passed:  # other checks need the columns
            continue
        results += [
            check_nulls(df, table, cols, config.MAX_NULL_PCT),
            check_ranges(df, table, cols),
            check_duplicates(df, table),
            check_freshness(df, table, key, now, ids, config.MAX_AGE_HOURS),
            check_volume(df, table, expected),
        ]
    return results
