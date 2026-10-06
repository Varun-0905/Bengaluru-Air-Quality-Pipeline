import pandas as pd
import pytest

from src import config, validate

NOW = pd.Timestamp("2026-10-06 12:00", tz="UTC")
PAST_DAYS = 2
N_LOC = len(config.LOCATIONS)


def make(cols, past_days=PAST_DAYS, now=NOW, **overrides):
    start = (now - pd.Timedelta(days=past_days)).normalize()
    hours = pd.date_range(start, now, freq="h")
    rows = [(l["location_id"], ts) for l in config.LOCATIONS for ts in hours]
    df = pd.DataFrame(rows, columns=["location_id", "ts"])
    for c in cols:
        df[c] = 10.0
    for k, v in overrides.items():
        df[k] = v
    return df


@pytest.fixture
def air():
    return make(config.AIR_COLS)


@pytest.fixture
def weather():
    return make(config.WEATHER_COLS, humidity=60.0)


def failed(results):
    return {r.name for r in results if not r.passed}


def run(air, weather):
    return validate.run_all(air, weather, N_LOC, PAST_DAYS, NOW)


def test_good_data_passes_all_checks(air, weather):
    assert failed(run(air, weather)) == set()


def test_missing_column_fails_schema(air, weather):
    assert "air.schema" in failed(run(air.drop(columns=["pm2_5"]), weather))


def test_too_many_nulls_fails(air, weather):
    air.loc[: len(air) // 2, "pm2_5"] = None
    assert "air.nulls" in failed(run(air, weather))


def test_out_of_range_pm25_fails(air, weather):
    air.loc[0, "pm2_5"] = 5000
    assert "air.range" in failed(run(air, weather))


def test_humidity_above_100_fails(air, weather):
    weather.loc[0, "humidity"] = 140
    assert "weather.range" in failed(run(air, weather))


def test_duplicates_fail(air, weather):
    assert "air.duplicates" in failed(run(pd.concat([air, air.iloc[:5]]), weather))


def test_stale_data_fails_freshness(air, weather):
    air.loc[air["ts"] > NOW - pd.Timedelta(hours=6), "pm2_5"] = None  # API stalled: recent hours empty
    assert "air.freshness" in failed(run(air, weather))


def test_low_volume_fails(air, weather):
    assert "weather.volume" in failed(run(air, weather.iloc[: len(weather) // 2]))
