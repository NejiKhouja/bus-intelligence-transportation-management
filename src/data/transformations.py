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


def fill_demand_calendar_gaps(demand: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """aggregate_demand() only has a row for a (route, bucket) that had
    at least one ticket — a bucket with zero tickets is absent, not
    zero. A lag feature computed directly on that (e.g. shift(7)) would
    silently mean "7th most recent bucket with a sale," not "7 buckets
    ago," whenever a route has gaps (verified: a top route has 45
    gap-days in a 906-day span). This reindexes each route to a
    complete calendar within its own observed range and fills gaps with
    0 passengers/revenue, so lag features computed after this are
    actually calendar-correct. Run this before add_lag_features().
    """
    filled = []
    for route_id, g in demand.groupby("route_id"):
        idx = pd.date_range(g["time_bucket"].min(), g["time_bucket"].max(), freq=freq)
        g = g.set_index("time_bucket").reindex(idx)
        g["route_id"] = route_id
        g[["passenger_count", "revenue"]] = g[["passenger_count", "revenue"]].fillna(0)
        g.index.name = "time_bucket"
        filled.append(g.reset_index())
    return pd.concat(filled, ignore_index=True)


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

def travel_times_from_trip_stops(trip_stops: pd.DataFrame, exclude_dark_gaps: bool = True,
                                  exclude_skipped_stops: bool = True) -> pd.DataFrame:
    """extraction.extract_trip_stops() -> one row per route leg per trip:
    trip_id, from_stop_id, to_stop_id, seq, departure_time,
    leg_travel_time_s, arrival_match_distance_m. Real per-leg time
    (departure at i -> arrival at i+1), not a raw ping-to-ping gap that
    might span several stops.

    arrival_match_distance_m is NOT the distance travelled for the leg —
    it's how far the GPS fix that matched the destination stop was from
    that stop's own coordinates (checked against the sibling repo's
    foundation.py: this is a match-quality distance, computed once per
    stop, not a delta between stops). Real leg distance would need a
    haversine on the two stops' coordinates (extraction.extract_reference_stops())
    and isn't computed here yet.

    Only matched=1 rows are used, which means consecutive matched rows
    aren't necessarily consecutive stops — ~12% of matched-to-matched
    pairs skip 1+ unmatched stops in between, and had_gap/dark_s on the
    destination doesn't reliably flag this (verified: the single worst
    case, a 10.8h "leg", has had_gap=0 on its destination — the dark
    period is recorded on the *origin* stop instead, as pre-trip idle
    time, not on either end of the inflated leg). exclude_skipped_stops
    drops any pair where seq doesn't advance by exactly 1, which is what
    actually catches that case. exclude_dark_gaps additionally drops
    legs whose destination has had_gap=1 (real dark period between two
    truly consecutive stops). Both default True; set False to inspect
    the excluded rows instead of discarding them.

    A residual few legs (~0.2%) still exceed 1h with no flag at all —
    e.g. a bus idling a long time before actually departing seq=0, not
    caught by either check above. Apply a final duration cap (e.g.
    percentile clip) before training on this.
    """
    df = trip_stops[trip_stops["matched"] == 1].sort_values(["trip_id", "seq"]).copy()
    df["next_stop_id"] = df.groupby("trip_id")["stop_id"].shift(-1)
    df["next_seq"] = df.groupby("trip_id")["seq"].shift(-1)
    df["next_arrival"] = df.groupby("trip_id")["arrival"].shift(-1)
    df["next_dist_m"] = df.groupby("trip_id")["dist_m"].shift(-1)
    df["next_had_gap"] = df.groupby("trip_id")["had_gap"].shift(-1)
    df = df.dropna(subset=["next_arrival"])

    leg_travel_time_s = (df["next_arrival"] - df["departure"]).dt.total_seconds()
    out = pd.DataFrame({
        "trip_id": df["trip_id"],
        "from_stop_id": df["stop_id"],
        "to_stop_id": df["next_stop_id"].astype(df["stop_id"].dtype),
        "seq": df["seq"],
        "departure_time": df["departure"],
        "leg_travel_time_s": leg_travel_time_s,
        "arrival_match_distance_m": df["next_dist_m"],
        "n_stops_skipped": (df["next_seq"] - df["seq"] - 1).astype(int),
        "had_dark_gap": df["next_had_gap"].astype(bool),
    })
    out = out[out["leg_travel_time_s"] > 0]
    if exclude_skipped_stops:
        out = out[out["n_stops_skipped"] == 0].drop(columns="n_stops_skipped")
    if exclude_dark_gaps:
        out = out[~out["had_dark_gap"]].drop(columns="had_dark_gap")
    return out.reset_index(drop=True)


def derive_operational_vehicles(trips: pd.DataFrame, companies: pd.DataFrame, recency_days: int = 30) -> pd.DataFrame:
    """extraction.extract_trips() + extract_reference_companies() ->
    societe, vehicle_id, last_trip_start, is_recently_active. Better
    signal for "is this vehicle actually running" than
    winicari.bus.fonctionnel, which is often stale (see
    docs/optimization_problem.md Problem 2). Recency is relative to the
    most recent trip_start in the data, not the system clock.

    Only covers vehicles that appear in `trips` at all — trip
    reconstruction only exists for companies with usable historical GPS
    (71/772 vehicles). See derive_fleet_operational_status() for a
    fleet-wide combination with the ticket-based fallback below.
    """
    df = trips.merge(companies[["company_id", "canonical_name"]], on="company_id", how="left")
    df["bus"] = df["bus"].astype(str)
    last_seen = (
        df.groupby(["canonical_name", "bus"])["trip_start"].max()
        .reset_index()
        .rename(columns={"canonical_name": "societe", "bus": "vehicle_id", "trip_start": "last_trip_start"})
    )
    reference_now = trips["trip_start"].max()
    last_seen["is_recently_active"] = (reference_now - last_seen["last_trip_start"]) <= pd.Timedelta(days=recency_days)
    return last_seen


def combine_ticket_activity(yearly_frames: list[pd.DataFrame]) -> pd.DataFrame:
    """List of extraction.extract_ticket_activity_by_bus(year) outputs ->
    one row per (societe, vehicle_id) across all years, with the overall
    last_ticket_date and total n_tickets."""
    all_years = pd.concat(yearly_frames, ignore_index=True)
    return (
        all_years.groupby(["societe", "vehicle_id"])
        .agg(last_ticket_date=("last_ticket_date", "max"), n_tickets=("n_tickets", "sum"))
        .reset_index()
    )


def derive_operational_vehicles_from_tickets(activity: pd.DataFrame, recency_days: int = 30) -> pd.DataFrame:
    """combine_ticket_activity() output -> adds is_recently_active,
    relative to the most recent last_ticket_date in the data (not the
    system clock). Weaker than the GPS-based signal (ticket sales don't
    prove the bus itself is running, just that its device sold tickets
    that day) but covers companies with no GPS history at all."""
    df = activity.copy()
    reference_now = df["last_ticket_date"].max()
    df["is_recently_active"] = (reference_now - df["last_ticket_date"]) <= pd.Timedelta(days=recency_days)
    return df


def derive_fleet_operational_status(vehicles: pd.DataFrame, gps_activity: pd.DataFrame,
                                     ticket_activity: pd.DataFrame) -> pd.DataFrame:
    """extraction.extract_vehicles() (full 772-vehicle roster) +
    derive_operational_vehicles() (GPS) + derive_operational_vehicles_from_tickets()
    (tickets) -> one row per vehicle in the roster, with:
    - is_recently_active: from GPS if the vehicle appears there, else
      from tickets, else null (meaning no activity signal at all, not a
      confirmed-inactive claim — don't treat null as False).
    - activity_source: "gps_trip", "ticket_sales", or "none".
    - last_activity_date: whichever signal was used.

    Joined on (societe, vehicle_id) — bus codes are reused across
    operators (54/772 vehicle_ids collide across companies in this
    fleet), so vehicle_id alone is not a safe join key.
    """
    base = vehicles[["societe", "vehicle_id"]].drop_duplicates().copy()
    base["vehicle_id"] = base["vehicle_id"].astype(str)

    gps = gps_activity.rename(columns={"last_trip_start": "last_activity_date"})[
        ["societe", "vehicle_id", "last_activity_date", "is_recently_active"]
    ]
    tix = ticket_activity.rename(columns={"last_ticket_date": "last_activity_date"})[
        ["societe", "vehicle_id", "last_activity_date", "is_recently_active"]
    ]

    out = base.merge(gps, on=["societe", "vehicle_id"], how="left")
    out["activity_source"] = out["is_recently_active"].notna().map({True: "gps_trip", False: "none"})

    missing = out["activity_source"] == "none"
    fallback = out.loc[missing, ["societe", "vehicle_id"]].merge(tix, on=["societe", "vehicle_id"], how="left")
    out.loc[missing, "last_activity_date"] = fallback["last_activity_date"].values
    out.loc[missing, "is_recently_active"] = fallback["is_recently_active"].values
    # fallback is index-aligned with the `missing` subset (same order, same length),
    # not with the full `out` frame — assign via a same-length array, not a boolean `&`.
    out.loc[missing, "activity_source"] = np.where(
        fallback["is_recently_active"].notna().values, "ticket_sales", "none"
    )

    return out


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
