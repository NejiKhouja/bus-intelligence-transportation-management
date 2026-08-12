"""Demand forecasting. Baseline before any learned model — see docs/architecture.md."""

from __future__ import annotations

import pandas as pd


def naive_last_week_baseline(demand: pd.DataFrame, group_col: str = "route_id",
                              target_col: str = "passenger_count") -> pd.Series:
    """Same route's value 7 buckets earlier. A learned model has to beat this."""
    return demand.sort_values([group_col, "time_bucket"]).groupby(group_col)[target_col].shift(7)
