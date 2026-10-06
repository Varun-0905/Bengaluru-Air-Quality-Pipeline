"""Single source of truth for settings, locations, thresholds and AQI bands."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "out"
load_dotenv(ROOT / ".env")

# Coordinates are approximate area centres. Open-Meteo grids are coarse (~11 km or more)
# so neighbouring areas can share a grid cell; see README "Limitations".
LOCATIONS = [
    {"location_id": 1, "name": "Silk Board", "latitude": 12.9177, "longitude": 77.6233},
    {"location_id": 2, "name": "Whitefield", "latitude": 12.9698, "longitude": 77.7500},
    {"location_id": 3, "name": "Hebbal", "latitude": 13.0358, "longitude": 77.5970},
    {"location_id": 4, "name": "Koramangala", "latitude": 12.9352, "longitude": 77.6245},
    {"location_id": 5, "name": "Peenya", "latitude": 13.0285, "longitude": 77.5197},
    {"location_id": 6, "name": "Electronic City", "latitude": 12.8452, "longitude": 77.6602},
    {"location_id": 7, "name": "Jayanagar", "latitude": 12.9308, "longitude": 77.5838},
    {"location_id": 8, "name": "Yelahanka", "latitude": 13.1007, "longitude": 77.5963},
    {"location_id": 9, "name": "Indiranagar", "latitude": 12.9784, "longitude": 77.6408},
    {"location_id": 10, "name": "Hebbagodi", "latitude": 12.8000, "longitude": 77.6600},
]

AIR_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# API variable name -> our column name
AIR_VARS = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "ozone": "ozone",
    "us_aqi": "us_aqi",
}
WEATHER_VARS = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "precipitation": "precipitation",
    "wind_speed_10m": "wind_speed",
}
AIR_COLS = list(AIR_VARS.values())
WEATHER_COLS = list(WEATHER_VARS.values())

# Each run re-fetches this many past days and upserts (self-healing window).
DEFAULT_PAST_DAYS = 2
HTTP_TIMEOUT = 30
HTTP_RETRIES = 4  # waits 2s, 4s, 8s between attempts

# Validation thresholds
RANGES = {
    "pm2_5": (0, 1000), "pm10": (0, 1500), "no2": (0, 1000), "ozone": (0, 1000),
    "us_aqi": (0, 500),
    "temperature": (-10, 55), "humidity": (0, 100),
    "precipitation": (0, 200), "wind_speed": (0, 200),
}
MAX_NULL_PCT = 10.0
MAX_AGE_HOURS = 3
MIN_VOLUME_RATIO = 0.95
MAX_VOLUME_RATIO = 1.05

# US AQI bands (upper bound inclusive, label). Used by SQL transform, tests and dashboard.
AQI_BANDS = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for Sensitive Groups"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (None, "Hazardous"),
]
AQI_ORDER = [label for _, label in AQI_BANDS]
AQI_COLORS = {
    "Good": "#2e9e4f", "Moderate": "#e6c229", "Unhealthy for Sensitive Groups": "#f08c2b",
    "Unhealthy": "#d63c3c", "Very Unhealthy": "#8e44ad", "Hazardous": "#6b1d1d",
}


def aqi_category(value: float | None) -> str | None:
    if value is None or value != value:  # None or NaN
        return None
    for upper, label in AQI_BANDS:
        if upper is None or value <= upper:
            return label
    return None


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return url
