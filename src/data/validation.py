"""Data-quality checks used to produce the audit in docs/database.md.

Each function returns a small dict of metrics rather than raising, so a
full report can be assembled by calling all of them over a sample or a
full extracted DataFrame.
"""

from __future__ import annotations

import pandas as pd

TUNISIA_LAT_RANGE = (30.0, 38.0)
TUNISIA_LON_RANGE = (7.0, 12.0)
MAX_PLAUSIBLE_BUS_SPEED_KMH = 120


def missing_rate(df: pd.DataFrame, columns: list[str]) -> dict[str, float]:
    return {c: float(df[c].isna().mean()) if c in df.columns else 1.0 for c in columns}


def duplicate_rate(df: pd.DataFrame, subset: list[str]) -> float:
    if df.empty:
        return 0.0
    return float(df.duplicated(subset=subset).mean())


def invalid_coordinate_rate(df: pd.DataFrame, lat_col: str, lon_col: str) -> float:
    if df.empty:
        return 0.0
    lat_ok = df[lat_col].between(*TUNISIA_LAT_RANGE)
    lon_ok = df[lon_col].between(*TUNISIA_LON_RANGE)
    return float((~(lat_ok & lon_ok)).mean())


def implausible_speed_rate(df: pd.DataFrame, speed_col: str, max_kmh: float = MAX_PLAUSIBLE_BUS_SPEED_KMH) -> float:
    if df.empty or speed_col not in df.columns:
        return 0.0
    return float((df[speed_col] > max_kmh).mean())


def negative_or_zero_duration_rate(df: pd.DataFrame, start_col: str, end_col: str) -> float:
    if df.empty:
        return 0.0
    delta = (df[end_col] - df[start_col]).dt.total_seconds()
    return float((delta <= 0).mean())


def gps_gap_stats(df: pd.DataFrame, group_col: str, time_col: str, max_gap_minutes: float = 15) -> dict:
    """For a single day/vehicle GPS extract: how often consecutive pings
    for the same vehicle are further apart than `max_gap_minutes`."""
    if df.empty:
        return {"n_gaps_over_threshold": 0, "median_gap_seconds": None}
    df = df.sort_values([group_col, time_col])
    gaps = df.groupby(group_col)[time_col].diff().dt.total_seconds()
    return {
        "n_gaps_over_threshold": int((gaps > max_gap_minutes * 60).sum()),
        "median_gap_seconds": float(gaps.median()) if gaps.notna().any() else None,
    }


def build_quality_report(name: str, df: pd.DataFrame, checks: dict) -> dict:
    """checks: mapping of report-key -> (function, kwargs) to run against df."""
    report = {"dataset": name, "row_count": len(df)}
    for key, (fn, kwargs) in checks.items():
        report[key] = fn(df, **kwargs)
    return report
