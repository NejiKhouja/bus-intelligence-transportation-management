"""Travel-time prediction. Baseline before any learned model."""

from __future__ import annotations

import pandas as pd


def historical_mean_baseline(segments: pd.DataFrame, group_cols: list[str] = None,
                              target_col: str = "travel_time_s") -> pd.DataFrame:
    group_cols = group_cols or ["route_id", "hour", "dow"]
    return segments.groupby(group_cols)[target_col].mean().reset_index(name=f"{target_col}_baseline")
