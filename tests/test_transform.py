import pandas as pd
import pytest

from src import config, ingest, transform, validate


@pytest.mark.parametrize("value,label", [
    (0, "Good"), (50, "Good"), (51, "Moderate"), (100, "Moderate"),
    (101, "Unhealthy for Sensitive Groups"), (151, "Unhealthy"),
    (250, "Very Unhealthy"), (301, "Hazardous"), (None, None), (float("nan"), None),
])
def test_aqi_category(value, label):
    assert config.aqi_category(value) == label


def test_sql_case_matches_config_bands():
    sql = transform.aqi_case_sql()
    for _, label in config.AQI_BANDS:
        assert f"'{label}'" in sql
    assert "{{AQI_CASE}}" not in transform.build_sql()


def test_clean_sql_is_idempotent_upsert():
    sql = transform.build_sql()
    assert "ON CONFLICT (location_id, ts) DO UPDATE" in sql and "Asia/Kolkata" in sql


def test_parse_hourly_multi_location_and_utc():
    payload = [
        {"hourly": {"time": ["2026-10-06T00:00", "2026-10-06T01:00"], "pm2_5": [10, None], "us_aqi": [40, 41]}},
        {"hourly": {"time": ["2026-10-06T00:00", "2026-10-06T01:00"], "pm2_5": [20, 21], "us_aqi": [50, 51]}},
    ]
    locs = config.LOCATIONS[:2]
    df = ingest.parse_hourly(payload, locs, {"pm2_5": "pm2_5", "us_aqi": "us_aqi"})
    assert list(df.columns) == ["location_id", "ts", "pm2_5", "us_aqi"]
    assert len(df) == 4 and str(df["ts"].dt.tz) == "UTC" and df["pm2_5"].isna().sum() == 1


def test_parse_hourly_rejects_wrong_location_count():
    with pytest.raises(ingest.IngestError):
        ingest.parse_hourly([{"hourly": {"time": []}}], config.LOCATIONS[:2], config.AIR_VARS)


def test_trim_future_drops_forecast_hours():
    now = pd.Timestamp("2026-10-06 12:00", tz="UTC")
    df = pd.DataFrame({"ts": pd.date_range("2026-10-06 10:00", periods=6, freq="h", tz="UTC")})
    assert df.pipe(ingest.trim_future, now)["ts"].max() == now


def test_expected_rows():
    now = pd.Timestamp("2026-10-06 12:00", tz="UTC")
    assert validate.expected_rows(now, 2, 10) == (48 + 13) * 10
