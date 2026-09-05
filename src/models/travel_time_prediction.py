"""Travel-time prediction. Baseline before any learned model."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# HistGradientBoostingRegressor (sklearn), not LightGBM/XGBoost — see
# src/models/demand_forecasting.py for why.
FEATURE_COLUMNS = ["line_id", "from_stop_id", "to_stop_id", "hour", "dow"]
TARGET_COLUMN = "leg_travel_time_s"


def historical_mean_baseline(legs: pd.DataFrame, group_cols: list[str] = None,
                              target_col: str = TARGET_COLUMN) -> pd.DataFrame:
    """legs must have hour/dow (src/features/travel_time_features.py) and
    line_id (join legs to trips on trip_id first). Grain defaults to
    (line, from_stop, to_stop, hour, dow) — the specific leg at that
    time, not just "the route" (a route's legs vary wildly in length)."""
    group_cols = group_cols or ["line_id", "from_stop_id", "to_stop_id", "hour", "dow"]
    return legs.groupby(group_cols)[target_col].mean().reset_index(name=f"{target_col}_baseline")


def train(train_df: pd.DataFrame, feature_columns: list[str] = None,
          target_column: str = TARGET_COLUMN) -> HistGradientBoostingRegressor:
    """train_df must have line_id/from_stop_id/to_stop_id as 'category'
    dtype and no NaN in feature_columns."""
    feature_columns = feature_columns or FEATURE_COLUMNS
    categorical = [c for c in ("line_id", "from_stop_id", "to_stop_id") if c in feature_columns]
    model = HistGradientBoostingRegressor(categorical_features=categorical, random_state=0)
    model.fit(train_df[feature_columns], train_df[target_column])
    return model


def predict(model: HistGradientBoostingRegressor, df: pd.DataFrame,
            feature_columns: list[str] = None) -> pd.Series:
    feature_columns = feature_columns or FEATURE_COLUMNS
    return pd.Series(model.predict(df[feature_columns]), index=df.index)
