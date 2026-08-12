"""Feature engineering for demand forecasting.

Input: the output of src.data.transformations.aggregate_demand() — one row
per (route_id, time_bucket) with passenger_count and revenue.

Not implemented yet: this module is a placeholder until a baseline model
(Phase 9) is scoped. Kept here so the pipeline shape (extraction ->
features -> model) is visible from day one, per the project skeleton.
"""

from __future__ import annotations

import pandas as pd


def add_calendar_features(demand: pd.DataFrame, time_col: str = "time_bucket") -> pd.DataFrame:
    """Day-of-week / hour-of-day / weekend features from the timestamp.
    Holiday and school-break flags should be joined in separately from
    OpenData.historiqueJourMeteo (see src/database/queries.py:iter_weather_calendar) —
    that join is not implemented here yet because Station-level weather
    calendar coverage vs. route-level demand has not been validated.
    """
    df = demand.copy()
    df["dow"] = df[time_col].dt.dayofweek
    df["is_weekend"] = df["dow"].isin([4, 5])  # Fri/Sat weekend in Tunisia
    df["hour"] = df[time_col].dt.hour if hasattr(df[time_col].dt, "hour") else None
    return df


def add_lag_features(demand: pd.DataFrame, group_col: str = "route_id", target_col: str = "passenger_count",
                      lags: tuple[int, ...] = (1, 7)) -> pd.DataFrame:
    """Same-route lagged demand (t-1, t-7 buckets) as baseline predictors."""
    df = demand.sort_values([group_col, "time_bucket"]).copy()
    for lag in lags:
        df[f"{target_col}_lag_{lag}"] = df.groupby(group_col)[target_col].shift(lag)
    return df
