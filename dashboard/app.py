"""Streamlit dashboard: Now / Trends / Patterns / Pipeline health. Run: streamlit run dashboard/app.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

from src.config import AQI_COLORS, AQI_ORDER

st.set_page_config(page_title="Bengaluru Air Quality", page_icon="🌫️", layout="wide")


@st.cache_resource
def engine():
    url = None
    try:
        url = st.secrets["DATABASE_URL"]
    except Exception:  # no secrets file locally
        pass
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL is not configured (Streamlit secrets or environment).")
        st.stop()
    return create_engine(url.replace("postgres://", "postgresql://", 1), pool_pre_ping=True)


def query(sql: str) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn)


# Cached 15 min: protects the free DB (Neon sleeps when idle) and keeps the app fast.
@st.cache_data(ttl=900, show_spinner="Loading data...")
def load(name: str) -> pd.DataFrame:
    return query({
        "latest": """SELECT DISTINCT ON (c.location_id) l.name, c.ts_ist, c.pm2_5, c.pm10, c.us_aqi,
                            c.aqi_category, c.temperature, c.humidity, c.wind_speed
                     FROM clean_hourly c JOIN locations l USING (location_id)
                     ORDER BY c.location_id, c.ts DESC""",
        "trend": """SELECT l.name, c.ts_ist, c.pm2_5, c.us_aqi FROM clean_hourly c
                    JOIN locations l USING (location_id)
                    WHERE c.ts >= now() - interval '7 days' ORDER BY c.ts_ist""",
        "hourly": """SELECT l.name, c.hour_ist, AVG(c.pm2_5) AS pm2_5, COUNT(*) AS n
                     FROM clean_hourly c JOIN locations l USING (location_id) GROUP BY 1, 2""",
        "weekend": """SELECT l.name, CASE WHEN c.is_weekend THEN 'Weekend' ELSE 'Weekday' END AS day_type,
                             AVG(c.pm2_5) AS pm2_5, COUNT(*) AS n
                      FROM clean_hourly c JOIN locations l USING (location_id) GROUP BY 1, 2""",
        "categories": """SELECT l.name, c.aqi_category, COUNT(*) AS hours FROM clean_hourly c
                         JOIN locations l USING (location_id)
                         WHERE c.aqi_category IS NOT NULL GROUP BY 1, 2""",
        "runs": """SELECT run_id, started_at, finished_at, status, rows_fetched, rows_inserted,
                          rows_updated, error_message, checks
                   FROM pipeline_runs ORDER BY started_at DESC LIMIT 200""",
        "daily": """SELECT ts_ist::date AS day, COUNT(*) AS rows FROM clean_hourly GROUP BY 1 ORDER BY 1""",
        "n_loc": "SELECT COUNT(*) AS n FROM locations",
    }[name])


st.title("🌫️ Bengaluru Air Quality and Weather")
st.caption("Model-based estimates from Open-Meteo (not physical sensors). Times in IST.")

latest = load("latest")
if latest.empty:
    st.info("No data yet. Run the pipeline at least once.")
    st.stop()

age_h = (pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None) - latest["ts_ist"].max()).total_seconds() / 3600
if age_h > 8:
    st.warning(f"Data may be stale: newest hour is {age_h:.0f} h old. See the Pipeline health tab.")

tab_now, tab_trend, tab_pat, tab_health = st.tabs(["Now", "Trends", "Patterns", "Pipeline health"])

with tab_now:
    c1, c2, c3 = st.columns(3)
    c1.metric("City avg PM2.5 (ug/m3)", f"{latest['pm2_5'].mean():.1f}")
    c2.metric("City avg US AQI", f"{latest['us_aqi'].mean():.0f}")
    c3.metric("Latest hour (IST)", latest["ts_ist"].max().strftime("%d %b %H:%M"))
    fig = px.bar(latest.sort_values("us_aqi", ascending=False), x="name", y="us_aqi",
                 color="aqi_category", color_discrete_map=AQI_COLORS,
                 category_orders={"aqi_category": AQI_ORDER},
                 labels={"name": "", "us_aqi": "US AQI", "aqi_category": "Category"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(latest.rename(columns={"ts_ist": "hour (IST)"}).round(1), hide_index=True, use_container_width=True)

with tab_trend:
    trend = load("trend")
    areas = sorted(trend["name"].unique())
    pick = st.multiselect("Areas", areas, default=areas[:4])
    metric = st.radio("Metric", ["pm2_5", "us_aqi"], horizontal=True,
                      format_func=lambda m: "PM2.5 (ug/m3)" if m == "pm2_5" else "US AQI")
    st.plotly_chart(px.line(trend[trend["name"].isin(pick)], x="ts_ist", y=metric, color="name",
                            labels={"ts_ist": "", "name": "Area"}), use_container_width=True)
    st.caption("Last 7 days, hourly.")

with tab_pat:
    hourly = load("hourly")
    pivot = hourly.pivot(index="name", columns="hour_ist", values="pm2_5")
    st.subheader("Average PM2.5 by area and hour of day (IST)")
    st.plotly_chart(px.imshow(pivot, aspect="auto", color_continuous_scale="YlOrRd",
                              labels={"x": "Hour (IST)", "y": "", "color": "PM2.5"}), use_container_width=True)
    st.subheader("Weekday vs weekend")
    wk = load("weekend")
    st.plotly_chart(px.bar(wk, x="name", y="pm2_5", color="day_type", barmode="group",
                           labels={"name": "", "pm2_5": "Mean PM2.5", "day_type": ""}), use_container_width=True)
    st.subheader("Share of hours by AQI category")
    cat = load("categories")
    cat["pct"] = 100 * cat["hours"] / cat.groupby("name")["hours"].transform("sum")
    st.plotly_chart(px.bar(cat, x="name", y="pct", color="aqi_category", color_discrete_map=AQI_COLORS,
                           category_orders={"aqi_category": AQI_ORDER},
                           labels={"name": "", "pct": "% of hours", "aqi_category": "Category"}),
                    use_container_width=True)
    st.caption(f"Based on {int(hourly['n'].sum()):,} hourly records. Correlation is not causation; "
               "short history means patterns are indicative only.")

with tab_health:
    runs = load("runs")
    runs["started_at"] = pd.to_datetime(runs["started_at"], utc=True).dt.tz_convert("Asia/Kolkata")
    week = runs[runs["started_at"] >= pd.Timestamp.now(tz="Asia/Kolkata") - pd.Timedelta(days=7)]
    ok = runs[runs["status"] == "success"]
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Runs (7 d)", len(week))
    h2.metric("Success rate (7 d)", f"{100 * (week['status'] == 'success').mean():.0f}%" if len(week) else "n/a")
    h3.metric("Last success", ok["started_at"].max().strftime("%d %b %H:%M") if len(ok) else "never")
    h4.metric("Newest data age", f"{age_h:.1f} h")

    daily, n_loc = load("daily"), int(load("n_loc")["n"][0])
    daily = daily.iloc[:-1]  # today is partial
    daily["completeness_pct"] = (100 * daily["rows"] / (n_loc * 24)).clip(upper=100)
    if len(daily):
        st.subheader("Data completeness by day (clean rows vs locations x 24 h)")
        st.plotly_chart(px.bar(daily, x="day", y="completeness_pct", labels={"day": "", "completeness_pct": "%"}),
                        use_container_width=True)

    st.subheader("Recent runs")
    st.dataframe(runs.drop(columns=["checks"]).head(30), hide_index=True, use_container_width=True)
    last_checks = runs["checks"].dropna()
    if len(last_checks):
        st.subheader("Checks from the most recent run")
        st.dataframe(pd.DataFrame(last_checks.iloc[0]), hide_index=True, use_container_width=True)
