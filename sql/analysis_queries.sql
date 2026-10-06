-- Run after 2-3 weeks of data. Each block answers one analysis question from the project guide.

-- Q1. Worst average PM2.5 by area and hour (IST). Pivot in pandas for the area x hour heatmap.
SELECT l.name, c.hour_ist, ROUND(AVG(c.pm2_5)::numeric, 1) AS avg_pm25, COUNT(*) AS n
FROM clean_hourly c JOIN locations l USING (location_id)
GROUP BY l.name, c.hour_ist
ORDER BY avg_pm25 DESC;

-- Q2. Weekday vs weekend: mean, median and sample size.
SELECT l.name, c.is_weekend,
       ROUND(AVG(c.pm2_5)::numeric, 1) AS mean_pm25,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY c.pm2_5))::numeric, 1) AS median_pm25,
       COUNT(*) AS n
FROM clean_hourly c JOIN locations l USING (location_id)
GROUP BY l.name, c.is_weekend
ORDER BY l.name, c.is_weekend;

-- Q3. PM2.5 vs weather (correlation, not causation).
SELECT ROUND(CORR(pm2_5, wind_speed)::numeric, 2)    AS r_wind,
       ROUND(CORR(pm2_5, humidity)::numeric, 2)      AS r_humidity,
       ROUND(CORR(pm2_5, temperature)::numeric, 2)   AS r_temperature,
       ROUND(CORR(pm2_5, precipitation)::numeric, 2) AS r_precipitation,
       COUNT(*) AS n
FROM clean_hourly;

-- Q4. Share of hours in each AQI category, by area.
SELECT l.name, c.aqi_category, COUNT(*) AS hours,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.name), 1) AS pct
FROM clean_hourly c JOIN locations l USING (location_id)
WHERE c.aqi_category IS NOT NULL
GROUP BY l.name, c.aqi_category
ORDER BY l.name, MIN(c.us_aqi);

-- Q5. Anomalies: PM2.5 more than 3 std devs from the trailing 7-day mean (check real vs glitch).
WITH s AS (
    SELECT location_id, ts, pm2_5,
           AVG(pm2_5)         OVER w AS roll_mean,
           STDDEV_SAMP(pm2_5) OVER w AS roll_sd
    FROM clean_hourly
    WINDOW w AS (PARTITION BY location_id ORDER BY ts ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING)
)
SELECT l.name, s.ts, s.pm2_5, ROUND(s.roll_mean::numeric, 1) AS roll_mean,
       ROUND(((s.pm2_5 - s.roll_mean) / s.roll_sd)::numeric, 1) AS z
FROM s JOIN locations l USING (location_id)
WHERE s.roll_sd > 0 AND ABS(s.pm2_5 - s.roll_mean) / s.roll_sd > 3
ORDER BY ABS(s.pm2_5 - s.roll_mean) / s.roll_sd DESC;

-- Q6. Does rain clean the air? PM2.5 in the 6h before vs 6h after the start of a rain event.
WITH events AS (
    SELECT location_id, ts FROM (
        SELECT location_id, ts, precipitation,
               LAG(precipitation) OVER (PARTITION BY location_id ORDER BY ts) AS prev_p
        FROM clean_hourly
    ) t
    WHERE precipitation >= 1 AND COALESCE(prev_p, 0) < 0.1
),
windows AS (
    SELECT e.location_id, e.ts,
           AVG(c.pm2_5) FILTER (WHERE c.ts <  e.ts) AS pm_before,
           AVG(c.pm2_5) FILTER (WHERE c.ts >  e.ts) AS pm_after
    FROM events e
    JOIN clean_hourly c ON c.location_id = e.location_id
     AND c.ts BETWEEN e.ts - INTERVAL '6 hours' AND e.ts + INTERVAL '6 hours'
    GROUP BY e.location_id, e.ts
)
SELECT COUNT(*) AS rain_events,
       ROUND(AVG(pm_before)::numeric, 1) AS avg_before,
       ROUND(AVG(pm_after)::numeric, 1)  AS avg_after,
       ROUND(AVG(pm_after - pm_before)::numeric, 1) AS avg_change
FROM windows
WHERE pm_before IS NOT NULL AND pm_after IS NOT NULL;

-- Q7. Pipeline health by day: runs, failure rate, rows loaded.
SELECT started_at::date AS day,
       COUNT(*) AS runs,
       COUNT(*) FILTER (WHERE status <> 'success') AS not_success,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status <> 'success') / COUNT(*), 1) AS failure_pct,
       SUM(COALESCE(rows_inserted, 0)) AS rows_inserted
FROM pipeline_runs
GROUP BY 1
ORDER BY 1 DESC;
