import pandas as pd

from src import weekly_report as wr


def frame(rows):
    return pd.DataFrame(rows, columns=["name", "hour_ist", "pm2_5", "us_aqi"])


def test_summary_picks_worst_best_and_change():
    cur = frame([("A", 8, 60, 150), ("A", 9, 80, 160), ("B", 8, 20, 60), ("B", 9, 20, 60)])
    prev = frame([("A", 8, 50, 100), ("B", 8, 30, 80)])
    runs = pd.DataFrame({"status": ["success"] * 26 + ["failed"] * 2})
    s = wr.compute_summary(cur, prev, runs)
    assert (s["worst_area"], s["best_area"]) == ("A", "B")
    assert s["city_pm25"] == 45.0 and s["change_pct"] == 12.5
    assert s["runs_failed"] == 2 and s["pct_hours_unhealthy"] == 50.0 and s["peak_hour_ist"] == 9


def test_summary_handles_no_data_and_warns_on_few_runs():
    empty = frame([])
    s = wr.compute_summary(empty, empty, pd.DataFrame({"status": ["success"] * 3}))
    assert s["has_data"] is False
    assert "WARNING" in wr.render_text(s)
