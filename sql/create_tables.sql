-- Idempotent schema. Timestamps are stored in UTC (timestamptz); IST is derived for display.

CREATE TABLE IF NOT EXISTS locations (
    location_id SMALLINT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL
);

-- RAW layer: exactly what the API gave us (after validation gate). Never edited by hand.
CREATE TABLE IF NOT EXISTS raw_air_quality (
    location_id SMALLINT NOT NULL REFERENCES locations,
    ts          TIMESTAMPTZ NOT NULL,
    pm2_5       REAL,
    pm10        REAL,
    no2         REAL,
    ozone       REAL,
    us_aqi      REAL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, ts)
);

CREATE TABLE IF NOT EXISTS raw_weather (
    location_id   SMALLINT NOT NULL REFERENCES locations,
    ts            TIMESTAMPTZ NOT NULL,
    temperature   REAL,
    humidity      REAL,
    precipitation REAL,
    wind_speed    REAL,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (location_id, ts)
);

-- CLEAN layer: joined air + weather with IST helper columns, ready for analysis.
CREATE TABLE IF NOT EXISTS clean_hourly (
    location_id   SMALLINT NOT NULL REFERENCES locations,
    ts            TIMESTAMPTZ NOT NULL,
    ts_ist        TIMESTAMP NOT NULL,          -- wall-clock time in Asia/Kolkata
    hour_ist      SMALLINT NOT NULL,
    day_of_week   SMALLINT NOT NULL,           -- ISO: 1 = Monday ... 7 = Sunday
    is_weekend    BOOLEAN NOT NULL,
    pm2_5         REAL,
    pm10          REAL,
    no2           REAL,
    ozone         REAL,
    us_aqi        REAL,
    aqi_category  TEXT,
    temperature   REAL,
    humidity      REAL,
    precipitation REAL,
    wind_speed    REAL,
    PRIMARY KEY (location_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_clean_hourly_ts ON clean_hourly (ts);

-- OPS layer: one row per pipeline run.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    rows_fetched  INTEGER,
    rows_inserted INTEGER,
    rows_updated  INTEGER,
    status        TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    error_message TEXT,
    checks        JSONB
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs (started_at);
