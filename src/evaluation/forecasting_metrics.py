"""MAE, RMSE, MAPE — for comparing a model against the naive baseline in
src/models/demand_forecasting.py."""

from __future__ import annotations

import numpy as np
import pandas as pd


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(np.abs(y_true - y_pred).mean())


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(np.sqrt(((y_true - y_pred) ** 2).mean()))


def mape(y_true: pd.Series, y_pred: pd.Series) -> float:
    mask = y_true != 0
    return float((np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])).mean())
