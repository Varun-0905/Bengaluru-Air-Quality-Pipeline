"""Weekly summary. Step 1: plain-Python numbers. Step 2 (optional): LLM rewords those numbers only."""
from __future__ import annotations

import logging
import os

import pandas as pd
import requests
from sqlalchemy import text

from . import db, notify

log = logging.getLogger("weekly_report")
EXPECTED_RUNS_PER_WEEK = 28  # every 6 hours


def compute_summary(cur: pd.DataFrame, prev: pd.DataFrame, runs: pd.DataFrame) -> dict:
    """cur/prev: columns name, hour_ist, pm2_5, us_aqi. runs: column status."""
    s: dict = {
        "runs_total": int(len(runs)),
        "runs_failed": int((runs["status"] != "success").sum()) if len(runs) else 0,
        "expected_runs": EXPECTED_RUNS_PER_WEEK,
        "has_data": bool(cur["pm2_5"].notna().any()),
    }
    if not s["has_data"]:
        return s
    by_area = cur.groupby("name")["pm2_5"].mean().dropna().sort_values()
    s["best_area"], s["best_pm25"] = by_area.index[0], round(float(by_area.iloc[0]), 1)
    s["worst_area"], s["worst_pm25"] = by_area.index[-1], round(float(by_area.iloc[-1]), 1)
    s["city_pm25"] = round(float(cur["pm2_5"].mean()), 1)
    s["prev_city_pm25"] = round(float(prev["pm2_5"].mean()), 1) if prev["pm2_5"].notna().any() else None
    s["change_pct"] = (round(100 * (s["city_pm25"] - s["prev_city_pm25"]) / s["prev_city_pm25"], 1)
                       if s["prev_city_pm25"] else None)
    aqi = cur["us_aqi"].dropna()
    s["pct_hours_unhealthy"] = round(float((aqi > 100).mean() * 100), 1) if len(aqi) else None
    s["peak_hour_ist"] = int(cur.groupby("hour_ist")["pm2_5"].mean().idxmax())
    return s


def render_text(s: dict) -> str:
    lines = ["Bengaluru air quality: weekly summary (last 7 days)"]
    if s["has_data"]:
        change = (f"{s['change_pct']:+.1f}% vs previous week" if s["change_pct"] is not None
                  else "no previous week to compare")
        lines += [
            f"- City average PM2.5: {s['city_pm25']} ug/m3 ({change})",
            f"- Worst area: {s['worst_area']} ({s['worst_pm25']}); best: {s['best_area']} ({s['best_pm25']})",
            f"- Hours with US AQI above 100: {s['pct_hours_unhealthy']}%",
            f"- Typical daily PM2.5 peak: {s['peak_hour_ist']:02d}:00 IST",
        ]
    else:
        lines.append("- No air-quality data in the last 7 days.")
    lines.append(f"- Pipeline: {s['runs_total']} runs (about {s['expected_runs']} expected), {s['runs_failed']} not successful")
    if s["runs_total"] < 0.8 * s["expected_runs"]:
        lines.append("WARNING: far fewer runs than expected. Check that the GitHub Actions schedule is still enabled.")
    return "\n".join(lines)


def llm_rewrite(s: dict) -> str | None:
    """Optional. Any OpenAI-compatible endpoint. Gets computed numbers only, never raw data."""
    url, key, model = (os.environ.get(k) for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"))
    if not (url and key and model):
        return None
    prompt = ("Write exactly three plain-language sentences summarising this weekly air-quality data for Bengaluru. "
              "Use only these numbers, add no other facts:\n" + str(s))
    try:
        r = requests.post(f"{url.rstrip('/')}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
                          timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM step skipped: %s", type(exc).__name__)
        return None


def main() -> int:
    eng = db.engine()
    q = ("SELECT l.name, c.hour_ist, c.pm2_5, c.us_aqi FROM clean_hourly c JOIN locations l USING (location_id) "
         "WHERE c.ts >= now() - interval '{a}' AND c.ts < now() - interval '{b}'")
    with eng.connect() as conn:
        cur = pd.read_sql(text(q.format(a="7 days", b="0 seconds")), conn)
        prev = pd.read_sql(text(q.format(a="14 days", b="7 days")), conn)
        runs = pd.read_sql(text("SELECT status FROM pipeline_runs WHERE started_at >= now() - interval '7 days'"), conn)
    summary = compute_summary(cur, prev, runs)
    message = render_text(summary)
    extra = llm_rewrite(summary) if summary["has_data"] else None
    if extra:
        message += "\n\n" + extra
    print(message)
    notify.send(message)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
