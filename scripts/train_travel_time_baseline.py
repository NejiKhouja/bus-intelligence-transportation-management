#!/usr/bin/env python
"""Trains and evaluates the travel-time baseline against the historical-
mean rule, on data/processed/legs.parquet + trips.parquet.

Decisions made here (documented, not asked, per project scope):
- Grain is (line_id, from_stop_id, to_stop_id, hour, dow) — a route's
  legs vary wildly in length, so "the route's average" would be
  meaningless; a specific stop-to-stop leg at a specific hour/weekday is
  the right unit.
- Only (line_id, from_stop_id, to_stop_id) leg-groups with >=30
  occurrences are scored — matches the same reasoning as the >=200-row
  route filter in the demand baseline (need enough history for a
  meaningful mean/model).
- Global time split (last 8 weeks of the overall departure_time range
  as test) rather than per-group, since the historical-mean baseline
  doesn't need per-group continuity the way lagged demand features did.
- Any test leg-group unseen in train falls back to the train-wide mean
  for the baseline (documented, not silently dropped).

Run: python scripts/train_travel_time_baseline.py
"""

import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.features import travel_time_features  # noqa: E402
from src.models import travel_time_prediction  # noqa: E402
from src.evaluation import forecasting_metrics  # noqa: E402

MIN_OCCURRENCES_PER_LEG_GROUP = 30
TEST_WEEKS = 8
MODEL_OUT = Path(__file__).resolve().parents[1] / "models" / "travel_time" / "histgb_v1.joblib"
REPORT_OUT = Path(__file__).resolve().parents[1] / "docs" / "baseline_results.md"


def main():
    data_dir = Path(settings.data_processed_dir)
    legs = pd.read_parquet(data_dir / "legs.parquet")
    trips = pd.read_parquet(data_dir / "trips.parquet")

    legs = legs.merge(trips[["trip_id", "line_id"]], on="trip_id", how="left")
    legs = legs.dropna(subset=["line_id"])
    legs = travel_time_features.add_time_of_day_features(legs, time_col="departure_time")

    group_cols = ["line_id", "from_stop_id", "to_stop_id"]
    counts = legs.groupby(group_cols).size()
    eligible = counts[counts >= MIN_OCCURRENCES_PER_LEG_GROUP].index
    legs = legs.set_index(group_cols)
    legs = legs[legs.index.isin(eligible)].reset_index()
    print(f"{len(eligible)} leg-groups eligible (>= {MIN_OCCURRENCES_PER_LEG_GROUP} occurrences), {len(legs)} rows total")

    cutoff = legs["departure_time"].max() - pd.Timedelta(weeks=TEST_WEEKS)
    train_df = legs[legs["departure_time"] <= cutoff].copy()
    test_df = legs[legs["departure_time"] > cutoff].copy()
    print(f"train: {len(train_df)} rows, test: {len(test_df)} rows (cutoff {cutoff.date()})")

    # Baseline merge on plain (non-categorical) join keys — merging on
    # `category` dtype columns with mismatched category sets between
    # frames makes pandas fall back to a near-cross-join factorization
    # path (hit a 1.7GB allocation trying it here). Cast to category
    # only afterwards, for the model step, which needs it declared.
    baseline_table = travel_time_prediction.historical_mean_baseline(train_df)
    train_wide_mean = train_df["leg_travel_time_s"].mean()
    test_with_baseline = test_df.merge(baseline_table, on=["line_id", "from_stop_id", "to_stop_id", "hour", "dow"], how="left")
    n_unseen = test_with_baseline["leg_travel_time_s_baseline"].isna().sum()
    test_with_baseline["leg_travel_time_s_baseline"] = test_with_baseline["leg_travel_time_s_baseline"].fillna(train_wide_mean)
    print(f"test rows with no matching train group (fell back to train-wide mean): {n_unseen}/{len(test_df)}")

    y_true = test_with_baseline["leg_travel_time_s"]
    baseline_pred = test_with_baseline["leg_travel_time_s_baseline"]

    for col in ("line_id", "from_stop_id", "to_stop_id"):
        train_df[col] = train_df[col].astype("category")
        test_df[col] = test_df[col].astype(pd.CategoricalDtype(categories=train_df[col].cat.categories))

    model = travel_time_prediction.train(train_df)
    model_pred = travel_time_prediction.predict(model, test_df)

    results = {
        "historical_mean": {
            "mae": forecasting_metrics.mae(y_true, baseline_pred),
            "rmse": forecasting_metrics.rmse(y_true, baseline_pred),
            "mape": forecasting_metrics.mape(y_true, baseline_pred),
        },
        "histgb": {
            "mae": forecasting_metrics.mae(test_df["leg_travel_time_s"], model_pred),
            "rmse": forecasting_metrics.rmse(test_df["leg_travel_time_s"], model_pred),
            "mape": forecasting_metrics.mape(test_df["leg_travel_time_s"], model_pred),
        },
    }
    for name, m in results.items():
        print(f"{name}: MAE={m['mae']:.1f}s  RMSE={m['rmse']:.1f}s  MAPE={m['mape']:.3f}")

    improvement = (results["historical_mean"]["mae"] - results["histgb"]["mae"]) / results["historical_mean"]["mae"]
    print(f"MAE improvement over baseline: {improvement * 100:.1f}%")

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_OUT)
    print(f"wrote {MODEL_OUT}")

    verdict = ("beats the historical-mean baseline by a meaningful margin — worth keeping"
               if improvement > 0.10 else
               "does NOT clearly beat the historical-mean baseline — the mean rule is the better default here")

    section = f"""

# Baseline Results — Travel Time

Generated by `scripts/train_travel_time_baseline.py` against
`data/processed/legs.parquet` joined to `trips.parquet`
({len(eligible)} (line, from_stop, to_stop) leg-groups with
>={MIN_OCCURRENCES_PER_LEG_GROUP} occurrences, {len(legs)} scoreable rows).

Train: departures before {cutoff.date()}. Test: the last {TEST_WEEKS}
weeks ({len(test_df)} rows). {n_unseen} test rows had no matching
leg-group in train and used the train-wide mean as fallback.

| Model | MAE (s) | RMSE (s) | MAPE |
|---|---|---|---|
| Historical mean (line, from_stop, to_stop, hour, dow) | {results['historical_mean']['mae']:.1f} | {results['historical_mean']['rmse']:.1f} | {results['historical_mean']['mape']:.3f} |
| HistGradientBoostingRegressor | {results['histgb']['mae']:.1f} | {results['histgb']['rmse']:.1f} | {results['histgb']['mape']:.3f} |

MAE improvement over baseline: {improvement * 100:.1f}%.

**Verdict: the model {verdict}.**

Model artifact: `models/travel_time/histgb_v1.joblib`.
"""
    with open(REPORT_OUT, "a", encoding="utf-8") as f:
        f.write(section)
    print(f"appended to {REPORT_OUT}")


if __name__ == "__main__":
    main()
