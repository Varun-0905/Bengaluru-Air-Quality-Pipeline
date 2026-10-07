# Bengaluru Air Quality and Weather Pipeline

An automated, end-to-end data pipeline: scheduled ingestion, six data-quality checks, PostgreSQL storage
(raw / clean / ops layers), a live Streamlit dashboard and a weekly insight alert. Runs on free tiers only.

**Live dashboard:** [_add link_](https://bengaluru-air-quality-pipeline-hk6dva7fumaucxvy5uud7n.streamlit.app/)  |  **Data:** [Open-Meteo](https://open-meteo.com) air-quality and weather APIs

## Architecture

```
Open-Meteo APIs -> ingest.py -> validate.py -> load.py -> PostgreSQL (raw, clean, pipeline_runs)
        ^                                                        |           |
GitHub Actions (cron, every 6 h)                                 |           +--> Streamlit dashboard
                                                                 +--> weekly_report.py --> Telegram
```

## Design decisions

- **Idempotent**: primary key `(location_id, ts)` plus upserts; running twice gives the same result. Unchanged rows are not rewritten.
- **Self-healing**: every run re-fetches the last 2 days and upserts, so a skipped or late run is filled by the next one.
- **Validation gate**: all six checks (schema, nulls, range, duplicates, freshness, volume) run on both tables. Any failure marks the run `failed`, loads nothing, logs the reason in `pipeline_runs`, sends a Telegram alert and turns the Actions run red. Freshness uses the newest non-null value, so an API that returns empty recent hours is caught.
- **Atomic load**: raw and clean updates commit together or not at all.
- **ELT-lite**: raw data stays untouched; `clean_hourly` is built inside the database by `sql/clean_hourly.sql` (UTC stored, IST derived). AQI bands come from one list in `src/config.py` and generate the SQL `CASE`.
- **Efficient**: one API request per source for all locations, batched upserts, cached dashboard queries.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                   # add DATABASE_URL (Neon/Supabase)
pytest -q                                              # 26 tests
python -m src.ingest                                   # dry run: fetch + validate, no database
python -m src.pipeline --past-days 30                  # create tables, backfill 30 days
python -m src.pipeline                                 # normal run
streamlit run dashboard/app.py                         # needs: pip install -r dashboard/requirements.txt
```

## Deploy (all free)

1. Push to a **public** GitHub repo. Add secrets: `DATABASE_URL`, optionally `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and for the optional LLM wording `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`.
2. Actions tab: run **ingest** manually with `past_days = 30` once, then it runs every 6 hours. **weekly_report** runs Mondays 08:00 IST.
3. Streamlit Community Cloud: new app, main file `dashboard/app.py`, Python 3.11, add `DATABASE_URL` under Secrets.
4. My deployed version : https://bengaluru-air-quality-pipeline-hk6dva7fumaucxvy5uud7n.streamlit.app/



## Limitations (read before quoting results)

- Open-Meteo air quality is **model output, not sensor readings**, and grids are coarse, so nearby areas can show near-identical values. Differences between areas are indicative, not ground truth.
- 10 locations and a short history: patterns are exploratory. Correlation is not causation.
- Free tiers: Neon pauses idle compute (first query can be slow), Streamlit apps sleep when idle, scheduled workflows can start late and are paused after 60 days of repo inactivity (the weekly job tries to re-enable them; a small commit also resets the timer).

## Layout

`src/` pipeline code | `sql/` schema, transform, analysis queries | `tests/` pytest | `dashboard/` Streamlit | `.github/workflows/` schedules and CI | `docs/findings.md` results
