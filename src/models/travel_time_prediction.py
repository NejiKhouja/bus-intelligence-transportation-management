"""Travel-time prediction models.

Strategy (see docs/architecture.md): historical mean travel time per
route-leg/hour-of-day/day-of-week as the baseline before LightGBM/XGBoost.

Not implemented yet — blocked on route-leg matching for GPS segments
(see src/features/travel_time_features.py docstring and docs/roadmap.md).
"""

from __future__ import annotations

import pandas as pd


def historical_mean_baseline(segments: pd.DataFrame, group_cols: list[str] = None,
                              target_col: str = "travel_time_s") -> pd.DataFrame:
    group_cols = group_cols or ["route_id", "hour", "dow"]
    return segments.groupby(group_cols)[target_col].mean().reset_index(name=f"{target_col}_baseline")
