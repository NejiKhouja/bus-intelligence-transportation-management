"""Unit tests for pure data-cleaning/transformation logic — these don't
need MongoDB running.
"""

import pandas as pd

from src.data.cleaning import parse_flexible_datetime, swap_lat_lon_if_needed
from src.data.transformations import haversine_km


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
