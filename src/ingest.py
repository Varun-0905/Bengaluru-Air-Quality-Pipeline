"""Extract: fetch air quality + weather for ALL locations in one request each."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from . import config

log = logging.getLogger(__name__)


class IngestError(Exception):
    pass


def now_floor_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).floor("h")


def _get_json(url: str, params: dict):
    """GET with timeout and exponential backoff on network errors, 429 and 5xx."""
    last: Exception | None = None
    for attempt in range(1, config.HTTP_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"retryable status {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last = exc
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if not (code == 429 or code >= 500):
                raise  # 4xx (bad request) will not fix itself
            last = exc
        if attempt < config.HTTP_RETRIES:
            wait = 2**attempt
            log.warning("API attempt %d/%d failed (%s); retrying in %ds",
                        attempt, config.HTTP_RETRIES, type(last).__name__, wait)
            time.sleep(wait)
    raise IngestError(f"API unreachable after {config.HTTP_RETRIES} attempts: {last}")


def _params(locations: list[dict], var_map: dict, past_days: int) -> dict:
    return {
        "latitude": ",".join(str(l["latitude"]) for l in locations),
        "longitude": ",".join(str(l["longitude"]) for l in locations),
        "hourly": ",".join(var_map),
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "UTC",
    }


def parse_hourly(payload, locations: list[dict], var_map: dict) -> pd.DataFrame:
    """Open-Meteo returns a list (one item per location) or a dict for a single location."""
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(locations):
        raise IngestError(f"expected {len(locations)} location blocks, got {len(items)}")
    frames = []
    for loc, item in zip(locations, items):
        hourly = item.get("hourly") if isinstance(item, dict) else None
        if not hourly or "time" not in hourly:
            raise IngestError(f"no hourly block for {loc['name']}")
        df = pd.DataFrame(hourly).rename(columns={**var_map, "time": "ts"})
        df.insert(0, "location_id", loc["location_id"])
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    value_cols = [c for c in var_map.values() if c in out.columns]
    for c in value_cols:  # non-numeric junk becomes NaN and is caught by the null check
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[["location_id", "ts", *value_cols]]


def trim_future(df: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """The API also returns forecast hours; keep only hours up to now."""
    if "ts" not in df.columns:
        return df
    return df[df["ts"] <= now].reset_index(drop=True)


def fetch_all(locations: list[dict], past_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    air = parse_hourly(_get_json(config.AIR_API_URL, _params(locations, config.AIR_VARS, past_days)),
                       locations, config.AIR_VARS)
    weather = parse_hourly(_get_json(config.WEATHER_API_URL, _params(locations, config.WEATHER_VARS, past_days)),
                           locations, config.WEATHER_VARS)
    return air, weather


if __name__ == "__main__":
    # Dry run: fetch + validate, no database needed.  python -m src.ingest
    from . import validate

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now = now_floor_utc()
    a, w = fetch_all(config.LOCATIONS, config.DEFAULT_PAST_DAYS)
    a, w = trim_future(a, now), trim_future(w, now)
    print(a.head(), "\n", w.head())
    for r in validate.run_all(a, w, len(config.LOCATIONS), config.DEFAULT_PAST_DAYS, now):
        print(("PASS" if r.passed else "FAIL"), r.name, "-", r.detail)
