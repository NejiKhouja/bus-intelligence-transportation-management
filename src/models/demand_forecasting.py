"""Demand forecasting. Baseline before any learned model — see docs/architecture.md."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# HistGradientBoostingRegressor (sklearn), not LightGBM/XGBoost — avoids
# adding a dependency beyond what's already installed. Swap in if
# accuracy proves insufficient (see requirements.txt).
FEATURE_COLUMNS = ["route_id", "dow", "is_weekend", "passenger_count_lag_1", "passenger_count_lag_7"]
TARGET_COLUMN = "passenger_count"


def naive_last_week_baseline(demand: pd.DataFrame, group_col: str = "route_id",
                              target_col: str = "passenger_count") -> pd.Series:
    """Same route's value 7 buckets earlier. A learned model has to beat this."""
    return demand.sort_values([group_col, "time_bucket"]).groupby(group_col)[target_col].shift(7)


def train(train_df: pd.DataFrame, feature_columns: list[str] = None,
          target_column: str = TARGET_COLUMN) -> HistGradientBoostingRegressor:
    """train_df must already have calendar + lag features (see
    src/features/demand_features.py), route_id as 'category' dtype, and
    no NaN in feature_columns — filter those rows out before calling
    this, don't impute them."""
    feature_columns = feature_columns or FEATURE_COLUMNS
    model = HistGradientBoostingRegressor(categorical_features=["route_id"], random_state=0)
    model.fit(train_df[feature_columns], train_df[target_column])
    return model


def predict(model: HistGradientBoostingRegressor, df: pd.DataFrame,
            feature_columns: list[str] = None) -> pd.Series:
    feature_columns = feature_columns or FEATURE_COLUMNS
    return pd.Series(model.predict(df[feature_columns]), index=df.index)
