-- Rebuilds clean_hourly for the refresh window (%(since)s). Idempotent upsert.
-- {{AQI_CASE}} is generated from config.AQI_BANDS by src/transform.py.
INSERT INTO clean_hourly (
    location_id, ts, ts_ist, hour_ist, day_of_week, is_weekend,
    pm2_5, pm10, no2, ozone, us_aqi, aqi_category,
    temperature, humidity, precipitation, wind_speed
)
SELECT
    a.location_id,
    a.ts,
    a.ts AT TIME ZONE 'Asia/Kolkata',
    EXTRACT(HOUR FROM a.ts AT TIME ZONE 'Asia/Kolkata')::smallint,
    EXTRACT(ISODOW FROM a.ts AT TIME ZONE 'Asia/Kolkata')::smallint,
    EXTRACT(ISODOW FROM a.ts AT TIME ZONE 'Asia/Kolkata') IN (6, 7),
    a.pm2_5, a.pm10, a.no2, a.ozone, a.us_aqi,
    {{AQI_CASE}},
    w.temperature, w.humidity, w.precipitation, w.wind_speed
FROM raw_air_quality a
JOIN raw_weather w ON w.location_id = a.location_id AND w.ts = a.ts
WHERE a.ts >= %(since)s
ON CONFLICT (location_id, ts) DO UPDATE SET
    pm2_5 = EXCLUDED.pm2_5, pm10 = EXCLUDED.pm10, no2 = EXCLUDED.no2,
    ozone = EXCLUDED.ozone, us_aqi = EXCLUDED.us_aqi, aqi_category = EXCLUDED.aqi_category,
    temperature = EXCLUDED.temperature, humidity = EXCLUDED.humidity,
    precipitation = EXCLUDED.precipitation, wind_speed = EXCLUDED.wind_speed
WHERE (clean_hourly.pm2_5, clean_hourly.pm10, clean_hourly.no2, clean_hourly.ozone, clean_hourly.us_aqi,
       clean_hourly.temperature, clean_hourly.humidity, clean_hourly.precipitation, clean_hourly.wind_speed)
      IS DISTINCT FROM
      (EXCLUDED.pm2_5, EXCLUDED.pm10, EXCLUDED.no2, EXCLUDED.ozone, EXCLUDED.us_aqi,
       EXCLUDED.temperature, EXCLUDED.humidity, EXCLUDED.precipitation, EXCLUDED.wind_speed);
