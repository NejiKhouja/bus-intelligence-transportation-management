"""Features for travel-time prediction. Input: build_gps_segments() or
travel_times_from_trip_stops() output."""

from __future__ import annotations

import pandas as pd


def add_time_of_day_features(segments: pd.DataFrame, time_col: str = "segment_start") -> pd.DataFrame:
    df = segments.copy()
    df["hour"] = df[time_col].dt.hour
    df["dow"] = df[time_col].dt.dayofweek
    return df

