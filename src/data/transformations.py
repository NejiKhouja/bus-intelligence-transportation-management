"""Derived datasets built on top of extraction.py: demand by time bucket,
GPS pings collapsed into travel-time segments."""

from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_demand(tickets: pd.DataFrame, freq: str = "H") -> pd.DataFrame:
    """Ticket rows (route_id, sold_at, price) -> passenger counts per
    route per time bucket."""
    df = tickets.dropna(subset=["sold_at"]).copy()
    df["time_bucket"] = df["sold_at"].dt.floor(freq)
    grouped = (
        df.groupby(["route_id", "time_bucket"])
        .agg(passenger_count=("ticket_id", "count"), revenue=("price", "sum"))
        .reset_index()
    )
    return grouped


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return r * 2 * np.arcsin(np.sqrt(a))


def build_gps_segments(gps: pd.DataFrame) -> pd.DataFrame:
    """Consecutive GPS pings per vehicle (vehicle_id, timestamp, lat, lon)
    -> vehicle_id, route_id, segment_start, segment_end, travel_time_s,
    distance_km, avg_speed_kmh. Fallback for days/companies not covered
    by travel_times_from_trip_stops() below."""
    df = gps.dropna(subset=["timestamp", "lat", "lon"]).sort_values(["vehicle_id", "timestamp"]).copy()
    df["next_timestamp"] = df.groupby("vehicle_id")["timestamp"].shift(-1)
    df["next_lat"] = df.groupby("vehicle_id")["lat"].shift(-1)
    df["next_lon"] = df.groupby("vehicle_id")["lon"].shift(-1)
    df = df.dropna(subset=["next_timestamp"])

    travel_time_s = (df["next_timestamp"] - df["timestamp"]).dt.total_seconds()
    distance_km = haversine_km(df["lat"], df["lon"], df["next_lat"], df["next_lon"])

    out = pd.DataFrame({
        "vehicle_id": df["vehicle_id"],
        "route_id": df["route_id"],
        "segment_start": df["timestamp"],
        "segment_end": df["next_timestamp"],
        "travel_time_s": travel_time_s,
        "distance_km": distance_km,
    })
    out = out[out["travel_time_s"] > 0]
    out["avg_speed_kmh"] = out["distance_km"] / (out["travel_time_s"] / 3600.0)
    return out.reset_index(drop=True)


# --- built from the reference DB's trips/trip_stops, see reference_db_integration.md ---

def travel_times_from_trip_stops(trip_stops: pd.DataFrame) -> pd.DataFrame:
    """extraction.extract_trip_stops() -> one row per route leg per trip:
    trip_id, from_stop_id, to_stop_id, seq, leg_travel_time_s, distance_m.
    Real per-leg time (departure at i -> arrival at i+1), not a raw
    ping-to-ping gap that might span several stops.

    Only matched=1 rows are used. Note: a matched fix at both ends of a
    leg doesn't rule out a multi-hour dark gap in between — bound
    leg_travel_time_s before using this for modeling (see
    reference_db_integration.md).
    """
    df = trip_stops[trip_stops["matched"] == 1].sort_values(["trip_id", "seq"]).copy()
    df["next_stop_id"] = df.groupby("trip_id")["stop_id"].shift(-1)
    df["next_arrival"] = df.groupby("trip_id")["arrival"].shift(-1)
    df["next_dist_m"] = df.groupby("trip_id")["dist_m"].shift(-1)
    df = df.dropna(subset=["next_arrival"])

    leg_travel_time_s = (df["next_arrival"] - df["departure"]).dt.total_seconds()
    out = pd.DataFrame({
        "trip_id": df["trip_id"],
        "from_stop_id": df["stop_id"],
        "to_stop_id": df["next_stop_id"].astype(df["stop_id"].dtype),
        "seq": df["seq"],
        "leg_travel_time_s": leg_travel_time_s,
        "distance_m": df["next_dist_m"],
    })
    return out[out["leg_travel_time_s"] > 0].reset_index(drop=True)


def derive_empirical_schedule(trips: pd.DataFrame, freq_minutes: int = 30) -> pd.DataFrame:
    """extraction.extract_trips() -> trip-frequency table per (line_id,
    dir, day-of-week, time-of-day bucket) — the inferred schedule the
    fleet actually runs, since no published timetable exists (see
    optimization_problem.md, Problem 1). Reports frequency per bucket
    rather than one representative departure time, since real
    trip_start times vary trip-to-trip.
    """
    df = trips.dropna(subset=["trip_start"]).copy()
    df["dow"] = df["trip_start"].dt.dayofweek
    minute_of_day = df["trip_start"].dt.hour * 60 + df["trip_start"].dt.minute
    df["time_bucket_min"] = (minute_of_day // freq_minutes) * freq_minutes

    grouped = (
        df.groupby(["line_id", "dir", "dow", "time_bucket_min"])
        .agg(
            n_trips_observed=("trip_id", "count"),
            median_elapsed_min=("total_elapsed_min", "median"),
            mean_match_rate=("match_rate", "mean"),
        )
        .reset_index()
    )
    return grouped
