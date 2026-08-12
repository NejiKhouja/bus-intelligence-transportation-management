"""Feature engineering for travel-time prediction.

Input: the output of src.data.transformations.build_gps_segments() — one
row per consecutive GPS-ping pair per vehicle, with travel_time_s and
distance_km already computed.

Not implemented yet (see docs/roadmap.md): segment-to-route-leg matching
(snapping a raw GPS segment to a specific stop-to-stop leg of its route)
is the prerequisite this needs and hasn't been validated against the
~51% of routes that lack OpenData stop geometry.
"""

from __future__ import annotations

import pandas as pd


def add_time_of_day_features(segments: pd.DataFrame, time_col: str = "segment_start") -> pd.DataFrame:
    df = segments.copy()
    df["hour"] = df[time_col].dt.hour
    df["dow"] = df[time_col].dt.dayofweek
    return df
