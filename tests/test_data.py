"""Unit tests for pure data-cleaning/transformation logic — these don't
need MongoDB running.
"""

import pandas as pd

from src.data.cleaning import normalize_societe_name, parse_flexible_datetime, swap_lat_lon_if_needed
from src.data.transformations import fill_demand_calendar_gaps, haversine_km, travel_times_from_trip_stops


def test_parse_flexible_datetime_handles_single_digit_day():
    ts = parse_flexible_datetime("2020/01/1 09:28:00")
    assert ts == pd.Timestamp("2020-01-01 09:28:00")


def test_parse_flexible_datetime_handles_trailing_space():
    ts = parse_flexible_datetime("2019/12/25 04:41:00 ")
    assert ts == pd.Timestamp("2019-12-25 04:41:00")


def test_parse_flexible_datetime_none_on_empty():
    assert parse_flexible_datetime("") is None
    assert parse_flexible_datetime(None) is None


def test_swap_lat_lon_if_needed_keeps_correct_order():
    lat, lon = swap_lat_lon_if_needed(35.17, 8.85)
    assert (lat, lon) == (35.17, 8.85)


def test_swap_lat_lon_if_needed_swaps_reversed_pair():
    lat, lon = swap_lat_lon_if_needed(8.85, 35.17)
    assert (lat, lon) == (35.17, 8.85)


def test_haversine_km_zero_distance():
    assert haversine_km(35.0, 9.0, 35.0, 9.0) == 0.0


def test_parse_flexible_datetime_rejects_epoch_reset_artifact():
    # Confirmed real source-data bug: 192 tickets across 2025/2026 have a
    # literal "1970/01/01 01:00:00" date field (device clock reset),
    # each a duplicate of another ticket with the same identity but a
    # real date. Must not be silently treated as a real timestamp.
    assert parse_flexible_datetime("1970/01/01 01:00:00") is None


def test_normalize_societe_name_applies_confirmed_merges():
    assert normalize_societe_name("S.R.T.GAFSA") == "SRT.ELGOUAFEL"
    assert normalize_societe_name("winicari") == "Winicari"


def test_normalize_societe_name_none_on_non_string():
    # 49 docs in Historique_Tickets.Ticket2026 have Societe: [] instead
    # of a string — must not crash.
    assert normalize_societe_name(["bad", "data"]) is None


def test_fill_demand_calendar_gaps_fills_missing_days_with_zero():
    demand = pd.DataFrame({
        "route_id": ["1", "1", "1"],
        "time_bucket": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-05"]),
        "passenger_count": [10, 20, 50],
        "revenue": [100.0, 200.0, 500.0],
    })
    filled = fill_demand_calendar_gaps(demand)
    assert len(filled) == 5  # Jan 1-5 inclusive
    gap_row = filled[filled["time_bucket"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert gap_row["passenger_count"] == 0
    assert gap_row["revenue"] == 0


def _leg_row(trip_id, stop_id, seq, arrival, departure, matched=1, dist_m=10.0, dark_s=0.0, had_gap=False):
    return {
        "trip_id": trip_id, "stop_id": stop_id, "seq": seq,
        "arrival": pd.Timestamp(arrival), "departure": pd.Timestamp(departure),
        "dwell_s": 0.0, "dist_m": dist_m, "matched": matched,
        "dark_s": dark_s, "had_gap": had_gap,
    }


def test_travel_times_from_trip_stops_excludes_skipped_and_dark_gap_legs_by_default():
    trip_stops = pd.DataFrame([
        # trip 1: normal consecutive leg, kept
        _leg_row(1, 100, 0, "2024-01-01 08:00:00", "2024-01-01 08:00:00"),
        _leg_row(1, 101, 1, "2024-01-01 08:05:00", "2024-01-01 08:05:00"),
        # trip 2: seq 1 unmatched (skipped) -> the 0->2 pair must be excluded
        _leg_row(2, 200, 0, "2024-01-01 09:00:00", "2024-01-01 09:00:00"),
        _leg_row(2, 201, 1, "2024-01-01 09:03:00", "2024-01-01 09:03:00", matched=0),
        _leg_row(2, 202, 2, "2024-01-01 09:06:00", "2024-01-01 09:06:00"),
        # trip 3: consecutive but destination has had_gap=1 -> excluded
        _leg_row(3, 300, 0, "2024-01-01 10:00:00", "2024-01-01 10:00:00"),
        _leg_row(3, 301, 1, "2024-01-01 11:30:00", "2024-01-01 11:30:00", dark_s=5400.0, had_gap=True),
    ])
    legs = travel_times_from_trip_stops(trip_stops)
    assert set(legs["trip_id"]) == {1}

    legs_unfiltered = travel_times_from_trip_stops(trip_stops, exclude_dark_gaps=False, exclude_skipped_stops=False)
    assert set(legs_unfiltered["trip_id"]) == {1, 2, 3}
