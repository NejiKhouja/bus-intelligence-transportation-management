"""Derived datasets built from the normalized extractions in extraction.py.

These turn per-event data (one row per ticket, one row per GPS ping) into
the shapes the feature-engineering layer (src/features/) will need:
demand aggregated by route/stop/hour, and GPS pings collapsed into
travel-time segments between consecutive fixes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_demand(tickets: pd.DataFrame, freq: str = "H") -> pd.DataFrame:
    """Ticket-level rows -> passenger counts per route per time bucket.

    Input: output of extraction.extract_archived_tickets() /
    extract_live_tickets() (must have route_id, sold_at, price columns).
    """
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
    """Consecutive GPS pings per vehicle -> travel-time segments.

    Input: output of extraction.extract_archived_gps_day() /
    extract_live_gps() (must have vehicle_id, timestamp, lat, lon).

    Output columns: vehicle_id, route_id, segment_start, segment_end,
    travel_time_s, distance_km, avg_speed_kmh
    """
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
