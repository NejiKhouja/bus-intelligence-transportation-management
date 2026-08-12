"""Shared cleaning helpers for the messy, inconsistently-formatted date and
identifier fields observed across collections during discovery (see
docs/data_dictionary.md for the exact formats seen per field).
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

# Formats observed across ticket/GPS/session collections. Some rows have a
# single-digit day/month ("2020/01/1 09:28:00") or a trailing space
# ("2019/12/25 04:41:00 ") — both are handled by stripping + trying each
# format in order rather than assuming one canonical format.
_KNOWN_FORMATS = [
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]


def parse_flexible_datetime(value) -> pd.Timestamp | None:
    """Parse the assorted date-string formats found in this database.
    Returns NaT (via None) rather than raising, so bad rows can be counted
    by the caller instead of crashing an extraction run.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return pd.Timestamp(value)
    text = str(value).strip()
    if not text:
        return None
    # Collapse "2020/01/1" -> "2020/01/01" style single-digit components.
    text = re.sub(r"\b(\d)\b", r"0\1", text)
    for fmt in _KNOWN_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(text, fmt))
        except ValueError:
            continue
    # Last resort: let pandas try to infer it.
    ts = pd.to_datetime(text, errors="coerce", dayfirst=False)
    return ts if pd.notna(ts) else None


def normalize_societe_name(name: str | None) -> str | None:
    """Collapses known duplicate spellings of the same operator seen in
    winicari.bus / winicari.ligne (e.g. "winicari" vs "Winicari" is a
    platform placeholder, not a real operator name — flagged, not merged,
    since we don't know which real operator those rows belong to)."""
    if name is None:
        return None
    return name.strip()


def swap_lat_lon_if_needed(lat: float, lon: float) -> tuple[float, float]:
    """winicari.position stores localisation as {x, y} where x is actually
    latitude and y is actually longitude (confirmed against Tunisia's
    bounding box: lat ~30-38, lon ~7-12). This helper defends against that
    convention being inconsistent by swapping only when it would move an
    out-of-range pair into range."""
    if _in_tunisia_bounds(lat, lon):
        return lat, lon
    if _in_tunisia_bounds(lon, lat):
        return lon, lat
    return lat, lon


def _in_tunisia_bounds(lat: float, lon: float) -> bool:
    return 30.0 <= lat <= 38.0 and 7.0 <= lon <= 12.0
