#!/usr/bin/env python
"""Uses the trained demand model (models/demand/histgb_v1.joblib) to
forecast next-day passenger demand per route — replacing the recent-
30-day-average proxy that build_demo_payload.py used previously.

Only trusted for the 33 routes the model was actually trained on
(src/features + train_demand_baseline.py, >=200 daily observations).
For every other route (most of them — the model's trained set doesn't
cover most routes at any of the 4 target companies, e.g. only 2/22 for
SRT.ELGOUAFEL), this returns nothing and the caller keeps the honest
recent-average fallback instead of a low-quality guess from a model
that never saw that route during training.

Run standalone to sanity-check: python scripts/predict_next_day_demand.py
"""

import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.data import transformations  # noqa: E402
from src.features import demand_features  # noqa: E402

MIN_ROWS_PER_ROUTE = 200  # must match train_demand_baseline.py exactly
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "demand" / "histgb_v1.joblib"


def trained_route_categories(demand_daily: pd.DataFrame) -> list[str]:
    """Reconstructs the exact categorical dtype the model was trained
    with (sorted route_id strings among the >=200-row routes) — needed
    so predict-time category encoding lines up with what the model
    learned at fit time, not just "the same values, some order"."""
    counts = demand_daily.groupby("route_id").size()
    return sorted(counts[counts >= MIN_ROWS_PER_ROUTE].index.tolist())


def predict_next_day(demand_daily: pd.DataFrame, model=None) -> pd.DataFrame:
    """Returns route_id, predicted_demand, target_date for every route
    the model was trained on and that has enough history to compute
    lag_1/lag_7. Silently omits everything else — no fallback logic
    here, that's the caller's job (see build_demo_payload.py)."""
    if model is None:
        model = joblib.load(MODEL_PATH)

    categories = trained_route_categories(demand_daily)
    eligible = demand_daily[demand_daily["route_id"].isin(categories)]
    filled = transformations.fill_demand_calendar_gaps(eligible)
    filled = demand_features.add_calendar_features(filled)
    filled = demand_features.add_lag_features(filled, lags=(1, 7))

    rows = []
    for route_id, g in filled.groupby("route_id"):
        g = g.sort_values("time_bucket")
        last = g.iloc[-1]
        if len(g) < 8:
            continue  # not enough history for a real lag_7
        target_date = last["time_bucket"] + pd.Timedelta(days=1)
        lag1 = last["passenger_count"]
        # lag_7 for target_date = passenger_count 6 days before `last`
        lag7_row = g[g["time_bucket"] == last["time_bucket"] - pd.Timedelta(days=6)]
        if lag7_row.empty:
            continue
        rows.append({
            "route_id": route_id,
            "dow": target_date.dayofweek,
            "is_weekend": target_date.dayofweek in (4, 5),
            "passenger_count_lag_1": lag1,
            "passenger_count_lag_7": lag7_row.iloc[0]["passenger_count"],
            "target_date": target_date,
        })

    if not rows:
        return pd.DataFrame(columns=["route_id", "predicted_demand", "target_date"])

    features = pd.DataFrame(rows)
    features["route_id"] = pd.Categorical(features["route_id"], categories=categories)
    preds = model.predict(features[["route_id", "dow", "is_weekend", "passenger_count_lag_1", "passenger_count_lag_7"]])
    features["predicted_demand"] = preds.clip(min=0)
    return features[["route_id", "predicted_demand", "target_date"]]


if __name__ == "__main__":
    demand = pd.read_parquet(Path(settings.data_processed_dir) / "demand_daily.parquet")
    result = predict_next_day(demand)
    print(f"{len(result)} routes with a model-based next-day forecast (of {demand['route_id'].nunique()} total)")
    print(result.sort_values("predicted_demand", ascending=False).head(10).to_string(index=False))
    print("\ndistinct predicted values:", result["predicted_demand"].nunique(), "(should be > 1 if route matters)")
