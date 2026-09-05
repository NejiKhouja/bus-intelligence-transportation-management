#!/usr/bin/env python
"""Builds real map data per company for the fleet planner web app:
- bus_locations: each vehicle's last known position, from its most recent
  reconstructed trip's last matched stop (reference DB). More current
  than winicari.position (a stale ~1wk live window, and missing S.T.S
  entirely) — verified 100% resolvable for all 4 companies (58 buses).
- terminals: route endpoint stops (first/last stop per line), for lines
  with resolved geometry (line coverage varies 34/42 - 88/111 per company).
- depot: ONE approximate point per company at its governorate capital
  (OpenData.Delegation) — there is no real depot address anywhere in the
  source data (winicari.centre has no coordinates), so this is clearly
  labeled "approximate" everywhere it's used, never presented as exact.

Run: python scripts/build_map_data.py
Writes: data/processed/map_data.json
"""

import json
import sys
from pathlib import Path

import pandas as pd
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.data import extraction  # noqa: E402

COMPANIES = ["S.R.T.K", "S.R.T.SELIANA", "S.T.S", "SRT.ELGOUAFEL"]
GOVERNORATE_BY_COMPANY = {
    "S.R.T.K": "Kasserine",
    "S.R.T.SELIANA": "Siliana",
    "S.T.S": "Sousse",
    "SRT.ELGOUAFEL": "Gafsa",
}
OUT_PATH = Path(settings.data_processed_dir) / "map_data.json"


def build_depot_points():
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    db = client["OpenData"]
    points = {}
    for company, gov in GOVERNORATE_BY_COMPANY.items():
        doc = db.Delegation.find_one({"name": {"$regex": gov, "$options": "i"}})
        if doc:
            points[company] = {"name": doc["name"] + " (approximate)", "lat": doc["lat"], "lon": doc["lng"], "approximate": True}
    return points


def main():
    trips = extraction.extract_trips()
    trip_stops = extraction.extract_trip_stops()
    companies_df = extraction.extract_reference_companies()
    stops = extraction.extract_reference_stops()
    lines = extraction.extract_reference_lines()
    line_stops = extraction.extract_reference_line_stops()

    trips = trips.merge(companies_df[["company_id", "canonical_name"]], on="company_id", how="left")
    lines = lines.merge(companies_df[["company_id", "canonical_name"]], on="company_id", how="left")
    matched_stops = trip_stops[trip_stops["matched"] == 1]

    depots = build_depot_points()

    result = {}
    for company in COMPANIES:
        # --- bus locations: last matched stop of each bus's most recent trip ---
        co_trips = trips[trips["canonical_name"] == company]
        last_trip_per_bus = co_trips.sort_values("trip_start").groupby("bus").tail(1)
        joined = last_trip_per_bus.merge(matched_stops, on="trip_id", how="inner")
        last_stop_per_bus = joined.sort_values("seq").groupby("bus").tail(1)
        with_coords = last_stop_per_bus.merge(stops[["stop_id", "lat", "lon", "primary_name"]], on="stop_id", how="left").dropna(subset=["lat", "lon"])

        bus_locations = [
            {
                "vehicle_id": str(r["bus"]),
                "lat": round(float(r["lat"]), 5),
                "lon": round(float(r["lon"]), 5),
                "near": r["primary_name"],
                "last_seen": r["trip_start"].strftime("%Y-%m-%d %H:%M"),
            }
            for _, r in with_coords.iterrows()
        ]

        # --- terminals: first/last stop per line with resolved geometry ---
        co_line_ids = lines[lines["canonical_name"] == company]["line_id"]
        co_line_stops = line_stops[line_stops["line_id"].isin(co_line_ids)]
        terminal_rows = []
        for line_id, g in co_line_stops.groupby("line_id"):
            g = g.sort_values("seq")
            if len(g) < 2:
                continue
            terminal_rows.append(g.iloc[0])
            terminal_rows.append(g.iloc[-1])
        if terminal_rows:
            term_df = pd.DataFrame(terminal_rows).merge(stops[["stop_id", "lat", "lon", "primary_name"]], on="stop_id", how="left")
            term_df = term_df.dropna(subset=["lat", "lon"]).drop_duplicates("stop_id")
        else:
            term_df = pd.DataFrame(columns=["stop_id", "lat", "lon", "primary_name"])

        terminals = [
            {"stop_id": int(r["stop_id"]), "name": r["primary_name"], "lat": round(float(r["lat"]), 5), "lon": round(float(r["lon"]), 5)}
            for _, r in term_df.iterrows()
        ]

        result[company] = {
            "bus_locations": bus_locations,
            "terminals": terminals,
            "depot": depots.get(company),
        }
        print(f"{company}: {len(bus_locations)} bus locations, {len(terminals)} terminals, depot={'yes' if company in depots else 'NO'}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
