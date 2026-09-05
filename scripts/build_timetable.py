#!/usr/bin/env python
"""Builds a suggested departure timetable per route — the practical,
everyday-usable output: "run buses at these clock times" instead of just
"how many buses total". Real data end to end:

1. Hourly demand SHAPE per route: real proportion of ticket sales in
   each hour of day, computed from all persisted ticket-years
   (2024-2026) for stability — hourly patterns are noisier than daily
   totals, so more history is used here than the 30-day window the
   daily demand numbers use.
2. That shape is applied to the route's predicted_demand (the same
   number already shown elsewhere — model-based or recent-average,
   whichever applies) to get predicted passengers per hour.
3. Suggested departures per hour = ceil(passengers_that_hour / bus
   capacity), spaced evenly across the hour into actual clock times.

Explicitly NOT solved here: which specific bus does which trip, turnaround
time between trips, or driver shifts — see docs/optimization_problem.md
Problem 1/3 for why (no schedule/driver-availability data exists to
validate against). This is a demand-driven departure-frequency
suggestion, not a fully constrained operational roster.

Run: python scripts/build_timetable.py
Writes: data/processed/timetable_data.json
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402

COMPANIES = ["S.R.T.K", "S.R.T.SELIANA", "S.T.S", "SRT.ELGOUAFEL"]
TICKET_YEARS = [2024, 2025, 2026]
MIN_HOUR_SHARE = 0.015  # ignore hours with under 1.5% of a route's daily tickets — noise, not real service
OUT_PATH = Path(settings.data_processed_dir) / "timetable_data.json"


def suggested_times_for_hour(hour: int, n_departures: int) -> list[str]:
    """Evenly space n_departures clock times within [hour:00, hour:59]."""
    if n_departures <= 0:
        return []
    if n_departures == 1:
        minutes = [0]
    else:
        step = 60 / n_departures
        minutes = [round(i * step) for i in range(n_departures)]
    return [f"{hour:02d}:{m:02d}" for m in minutes]


def main():
    data_dir = Path(settings.data_processed_dir)
    with open(data_dir / "demo_payload.json", encoding="utf-8") as f:
        payload = json.load(f)

    print("Loading ticket years for hourly shape:", TICKET_YEARS)
    all_tickets = pd.concat(
        [pd.read_parquet(data_dir / f"tickets_{y}.parquet") for y in TICKET_YEARS],
        ignore_index=True,
    )
    all_tickets = all_tickets.dropna(subset=["sold_at"])
    all_tickets["hour"] = all_tickets["sold_at"].dt.hour

    hourly_counts = all_tickets.groupby(["route_id", "hour"]).size().rename("n").reset_index()
    route_totals = hourly_counts.groupby("route_id")["n"].sum().rename("total")
    hourly_counts = hourly_counts.merge(route_totals, on="route_id")
    hourly_counts["share"] = hourly_counts["n"] / hourly_counts["total"]

    timetables = {}
    for company in COMPANIES:
        co = payload["companies"][company]
        avg_capacity = co["avg_capacity"]
        co_timetables = {}
        for route in co["route_demand"]:
            route_id = route["route_id"]
            shape = hourly_counts[hourly_counts["route_id"] == route_id]
            if shape.empty or shape["total"].iloc[0] < 20:
                continue  # not enough real ticket history to trust an hourly shape

            shape = shape[shape["share"] >= MIN_HOUR_SHARE].sort_values("hour")
            if shape.empty:
                continue

            daily_demand = route["predicted_demand"]
            hourly_rows = []
            total_departures = 0
            peak_hour, peak_passengers = None, -1
            for _, row in shape.iterrows():
                passengers = daily_demand * row["share"]
                departures = max(1, math.ceil(passengers / avg_capacity)) if passengers > 0 else 0
                if departures == 0:
                    continue
                times = suggested_times_for_hour(int(row["hour"]), departures)
                hourly_rows.append({
                    "hour": int(row["hour"]),
                    "predicted_passengers": round(passengers, 1),
                    "suggested_departures": departures,
                    "times": times,
                })
                total_departures += departures
                if passengers > peak_passengers:
                    peak_passengers, peak_hour = passengers, int(row["hour"])

            if not hourly_rows:
                continue

            co_timetables[route_id] = {
                "route_id": route_id,
                "origin": route["origin"],
                "destination": route["destination"],
                "predicted_demand": daily_demand,
                "avg_capacity": avg_capacity,
                "service_start_hour": hourly_rows[0]["hour"],
                "service_end_hour": hourly_rows[-1]["hour"],
                "peak_hour": peak_hour,
                "total_suggested_departures": total_departures,
                "hourly": hourly_rows,
                "ticket_sample_size": int(shape["total"].iloc[0]),
            }
        timetables[company] = co_timetables
        print(f"{company}: timetables built for {len(co_timetables)}/{len(co['route_demand'])} routes")

    OUT_PATH.write_text(json.dumps(timetables, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
