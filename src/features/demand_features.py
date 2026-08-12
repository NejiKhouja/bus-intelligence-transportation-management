"""Features for demand forecasting. Input: transformations.aggregate_demand() output."""

from __future__ import annotations

import pandas as pd


def add_calendar_features(demand: pd.DataFrame, time_col: str = "time_bucket") -> pd.DataFrame:
    """Holiday/school-break join from historiqueJourMeteo not done yet —
    station-level coverage vs route-level demand isn't validated."""
    df = demand.copy()
    df["dow"] = df[time_col].dt.dayofweek
    df["is_weekend"] = df["dow"].isin([4, 5])  # Fri/Sat weekend in Tunisia
    df["hour"] = df[time_col].dt.hour if hasattr(df[time_col].dt, "hour") else None
    return df


def add_lag_features(demand: pd.DataFrame, group_col: str = "route_id", target_col: str = "passenger_count",
                      lags: tuple[int, ...] = (1, 7)) -> pd.DataFrame:
    df = demand.sort_values([group_col, "time_bucket"]).copy()
    for lag in lags:
        df[f"{target_col}_lag_{lag}"] = df.groupby(group_col)[target_col].shift(lag)
    return df
