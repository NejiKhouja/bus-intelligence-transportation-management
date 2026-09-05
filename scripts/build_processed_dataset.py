#!/usr/bin/env python
"""Builds the processed datasets this project's baselines/optimization
work runs against, and writes them to data/processed/ as parquet.

Decisions made here (no business sign-off available, documented instead
of left open — see docs/roadmap.md and docs/reference_db_integration.md):

- Demand: persists tickets for 2024-2026 only, not the full 2019-2026
  archive. 2023 is excluded (confirmed device-outage year, would bias
  any model trained on it). 2019-2022 are skipped to keep this run
  tractable; extending is a one-line change to TICKET_YEARS below,
  extract_archived_tickets() already handles any year in range.
- Routes/stops/lines/trips: reference-DB tables are authoritative
  wherever they exist (see reference_db_integration.md) — the raw-Mongo
  `ligne`/OpenData equivalents are not persisted separately here.
- trip_stops (563k rows) itself is not persisted, only the derived
  per-leg travel times from it (174k rows) — trip_stops regenerates
  quickly from the local reference DB if needed again.
- Fleet operational status uses ALL 8 years of ticket history for the
  fallback signal (cheap: projected fields only, not full documents)
  even though the demand dataset above only covers 2024-2026 — recency
  detection benefits from the longer history, demand modeling doesn't
  need it.
- "Operational fleet" for planning purposes = vehicles with
  is_recently_active=True in fleet_status (67 of 772 at last run). This
  is an engineering decision, not a business-confirmed number — see
  docs/optimization_problem.md Problem 2.

Run: python scripts/build_processed_dataset.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.data import extraction, transformations  # noqa: E402

TICKET_YEARS = [2024, 2025, 2026]
ALL_TICKET_YEARS_FOR_FLEET_STATUS = list(range(2019, 2027))
FLEET_RECENCY_DAYS = 30

OUT_DIR = Path(settings.data_processed_dir)


def _save(df, name):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False)
    print(f"  wrote {path} ({len(df):,} rows)")


def main():
    t0 = time.time()

    print("Reference DB: companies, stops, lines, line_stops, trips")
    alias_map = extraction.build_company_alias_map()
    companies = extraction.extract_reference_companies()
    _save(companies, "companies")
    _save(extraction.extract_reference_stops(), "stops")
    _save(extraction.extract_reference_lines(), "lines")
    _save(extraction.extract_reference_line_stops(), "line_stops")

    trips = extraction.extract_trips()
    _save(trips, "trips")

    print("Reference DB: trip_stops -> legs (not persisting raw trip_stops, see module docstring)")
    trip_stops = extraction.extract_trip_stops()
    legs = transformations.travel_times_from_trip_stops(trip_stops)
    _save(legs, "legs")
    del trip_stops  # 563k-row frame, done with it

    print("Reference DB: empirical schedule")
    schedule = transformations.derive_empirical_schedule(trips, freq_minutes=30)
    _save(schedule, "schedule")

    print("Raw Mongo: routes, vehicles")
    _save(extraction.extract_routes(), "routes")
    vehicles = extraction.extract_vehicles(alias_map=alias_map)
    _save(vehicles, "vehicles")

    print("Fleet operational status (GPS trips + full 8yr ticket-activity fallback)")
    gps_ops = transformations.derive_operational_vehicles(trips, companies, recency_days=FLEET_RECENCY_DAYS)
    ticket_activity = transformations.combine_ticket_activity([
        extraction.extract_ticket_activity_by_bus(y, alias_map=alias_map)
        for y in ALL_TICKET_YEARS_FOR_FLEET_STATUS
    ])
    ticket_ops = transformations.derive_operational_vehicles_from_tickets(ticket_activity, recency_days=FLEET_RECENCY_DAYS)
    fleet_status = transformations.derive_fleet_operational_status(vehicles, gps_ops, ticket_ops)
    _save(fleet_status, "fleet_status")

    print(f"Raw Mongo: tickets for {TICKET_YEARS}")
    ticket_frames = []
    for year in TICKET_YEARS:
        df = extraction.extract_archived_tickets(year)
        _save(df, f"tickets_{year}")
        ticket_frames.append(df)

    print("Demand aggregation (daily, per route)")
    import pandas as pd
    all_tickets = pd.concat(ticket_frames, ignore_index=True)
    demand_daily = transformations.aggregate_demand(all_tickets, freq="D")
    _save(demand_daily, "demand_daily")

    print(f"\nDone in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
