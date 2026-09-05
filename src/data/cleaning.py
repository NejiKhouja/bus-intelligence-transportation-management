"""Cleaning helpers for the messy date/identifier formats in this
database. See docs/data_dictionary.md for the exact formats per field."""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

# Some rows have a single-digit day/month ("2020/01/1 09:28:00") or a
# trailing space ("2019/12/25 04:41:00 ") — handled by stripping + trying
# each format below rather than assuming one canonical format.
_KNOWN_FORMATS = [
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]


# The platform's own data starts 2018-12-30 (earliest dateAjout seen).
# Some Historique_Tickets docs have a literal "1970/01/01 01:00:00"
# stored as their date field — a device clock-reset artifact recorded
# as a real value, not a parsing failure (confirmed: 192 docs across
# Ticket2025/2026, each a duplicate of another doc with the same ticket
# identity but a real date). Anything outside this window is treated as
# unparseable rather than silently polluting a time-series aggregation.
_PLAUSIBLE_YEAR_RANGE = (2015, 2035)


def parse_flexible_datetime(value) -> pd.Timestamp | None:
    """Returns None on unparseable (or implausible, e.g. epoch-reset)
    input rather than raising, so bad rows can be counted instead of
    crashing an extraction run."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return pd.Timestamp(value)
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\b(\d)\b", r"0\1", text)  # "2020/01/1" -> "2020/01/01"
    parsed = None
    for fmt in _KNOWN_FORMATS:
        try:
            parsed = pd.Timestamp(datetime.strptime(text, fmt))
            break
        except ValueError:
            continue
    if parsed is None:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
        if pd.isna(parsed):
            return None
    if not (_PLAUSIBLE_YEAR_RANGE[0] <= parsed.year <= _PLAUSIBLE_YEAR_RANGE[1]):
        return None
    return parsed


# S.R.T.GAFSA is an older name for SRT.ELGOUAFEL, not a distinct company.
# winicari/Winicari is a platform-name placeholder, not a real operator —
# kept as its own pseudo-company, just case-normalized here.
MANUAL_COMPANY_ALIASES = {
    "S.R.T.GAFSA": "SRT.ELGOUAFEL",
    "winicari": "Winicari",
}


def normalize_societe_name(name, alias_map: dict[str, str] | None = None) -> str | None:
    """alias_map should normally come from
    extraction.build_company_alias_map() (reference DB + MANUAL_COMPANY_ALIASES).
    Falls back to MANUAL_COMPANY_ALIASES alone when the reference DB isn't available.

    Some Historique_Tickets docs have Societe stored as [] instead of a
    string (49 in Ticket2026 alone) — return None for any non-string
    input rather than crashing on it.
    """
    if not isinstance(name, str):
        return None
    stripped = name.strip()
    alias_map = alias_map or MANUAL_COMPANY_ALIASES
    return alias_map.get(stripped, stripped)


def swap_lat_lon_if_needed(lat: float, lon: float) -> tuple[float, float]:
    """winicari.position stores {x, y} where x is latitude and y is
    longitude despite the naming. Swap only if that moves an
    out-of-range pair into Tunisia's bounding box."""
    if _in_tunisia_bounds(lat, lon):
        return lat, lon
    if _in_tunisia_bounds(lon, lat):
        return lon, lat
    return lat, lon


def _in_tunisia_bounds(lat: float, lon: float) -> bool:
    return 30.0 <= lat <= 38.0 and 7.0 <= lon <= 12.0
