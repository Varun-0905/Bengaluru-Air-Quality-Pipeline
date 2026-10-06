"""Orchestrator. One run = fetch -> validate -> load raw -> build clean -> log.

Usage:  python -m src.pipeline [--past-days N]     (use --past-days 30 once to backfill)
Exit code is 1 on any failure so GitHub Actions marks the run red and emails you.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import config, db, ingest, load, notify, transform, validate

log = logging.getLogger("pipeline")


class ValidationFailed(Exception):
    pass


def run(past_days: int) -> int:
    started = datetime.now(timezone.utc)
    now = ingest.now_floor_utc()
    conn, run_id = None, None
    stats = {"rows_fetched": 0, "rows_inserted": 0, "rows_updated": 0}
    results: list[validate.CheckResult] = []
    status, error = "failed", None

    try:
        conn = db.connect()
        db.init_schema(conn)
        db.sync_locations(conn)
        run_id = db.start_run(conn, started)

        air, weather = ingest.fetch_all(config.LOCATIONS, past_days)
        air, weather = ingest.trim_future(air, now), ingest.trim_future(weather, now)
        stats["rows_fetched"] = len(air) + len(weather)

        config.OUT_DIR.mkdir(exist_ok=True)  # uploaded as an Actions artifact on failure
        air.to_csv(config.OUT_DIR / "last_batch_air.csv", index=False)
        weather.to_csv(config.OUT_DIR / "last_batch_weather.csv", index=False)

        results = validate.run_all(air, weather, len(config.LOCATIONS), past_days, now)
        failed = [r for r in results if not r.passed]
        if failed:  # quarantine: bad data is never loaded; the next run refetches the window
            raise ValidationFailed("; ".join(f"{r.name}: {r.detail}" for r in failed))

        ins_a, upd_a = load.upsert_air(conn, air)
        ins_w, upd_w = load.upsert_weather(conn, weather)
        stats["rows_inserted"], stats["rows_updated"] = ins_a + ins_w, upd_a + upd_w
        transform.build_clean(conn, now - timedelta(days=past_days + 1))
        conn.commit()  # raw + clean land together or not at all
        status = "success"
        log.info("success: %s", stats)
    except Exception as exc:  # noqa: BLE001
        log.exception("run failed")
        error = f"{type(exc).__name__}: {exc}"
        if conn is not None:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass

    if conn is not None and run_id is not None:
        try:
            db.finish_run(conn, run_id, status, stats, error, [r.as_dict() for r in results])
        except Exception:  # noqa: BLE001
            log.exception("could not write pipeline_runs row")
    if conn is not None:
        conn.close()

    if status != "success":
        notify.send(f"Air-quality pipeline FAILED (run {run_id}):\n{(error or '')[:900]}")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--past-days", type=int, default=config.DEFAULT_PAST_DAYS)
    args = ap.parse_args()
    if not 1 <= args.past_days <= 92:
        sys.exit("--past-days must be between 1 and 92 (Open-Meteo limit)")
    sys.exit(run(args.past_days))
