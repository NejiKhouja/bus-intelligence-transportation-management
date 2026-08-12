"""Demand forecasting models.

Strategy (see docs/architecture.md): start with a naive historical
baseline (same weekday/hour last week) before any learned model, since
that baseline is often hard to beat for regular commuter routes and gives
a concrete number to justify the complexity of LightGBM/XGBoost.

Not implemented yet — this file exists to fix the module boundary before
Phase 9 model work starts, per the project skeleton.
"""

from __future__ import annotations

import pandas as pd


def naive_last_week_baseline(demand: pd.DataFrame, group_col: str = "route_id",
                              target_col: str = "passenger_count") -> pd.Series:
    """Predicts each bucket's demand as the same route's value 7 buckets
    (e.g. 7 days, if freq='D') earlier. Use this to benchmark any learned
    model — a model that doesn't beat this isn't worth the complexity."""
    return demand.sort_values([group_col, "time_bucket"]).groupby(group_col)[target_col].shift(7)
