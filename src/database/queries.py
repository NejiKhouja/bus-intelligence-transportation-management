"""Domain queries for the collections that matter (see docs/database.md).
Kept separate from explorer.py so callers don't need raw collection names.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from . import reference_db
from .mongo_client import opendata_db, operational_db, pos_archive_db, tickets_archive_db


def iter_routes() -> Iterator[dict]:
    """winicari.ligne, ~402 docs, safe to load fully."""
    yield from operational_db().ligne.find()


def iter_vehicles() -> Iterator[dict]:
    yield from operational_db().bus.find()


def iter_companies() -> Iterator[dict]:
    yield from operational_db().societe.find()


def iter_fare_table() -> Iterator[dict]:
    yield from operational_db().price.find()


def iter_route_distances() -> Iterator[dict]:
    """winicari.klm — field names are mojibake-corrupted (legacy
    codepage), don't assume "Société" round-trips."""
    yield from operational_db().klm.find()


def iter_live_gps(batch_size: int = 5000) -> Iterator[dict]:
    """Rolling ~1wk window before pings age into Historique_pos."""
    yield from operational_db().position.find(batch_size=batch_size)


def iter_archived_gps_for_day(day: str, batch_size: int = 5000) -> Iterator[dict]:
    """day like "20260601". Historique_pos.d<YYYYMMDD>, 2022-01-21 onward."""
    yield from pos_archive_db()[f"d{day}"].find(batch_size=batch_size)


def list_archived_gps_days() -> list[str]:
    names = pos_archive_db().list_collection_names()
    return sorted(n[1:] for n in names if n.startswith("d"))


def iter_live_tickets(batch_size: int = 5000) -> Iterator[dict]:
    """Rolling ~1wk window of just-sold tickets."""
    yield from operational_db().ticket.find(batch_size=batch_size)


def iter_archived_tickets(year: int, batch_size: int = 5000) -> Iterator[dict]:
    """Historique_Tickets.Ticket<year>, 2019-2026. Main demand dataset."""
    yield from tickets_archive_db()[f"Ticket{year}"].find(batch_size=batch_size)


def available_ticket_years() -> list[int]:
    names = tickets_archive_db().list_collection_names()
    years = []
    for n in names:
        if n.startswith("Ticket"):
            try:
                years.append(int(n[len("Ticket"):]))
            except ValueError:
                continue
    return sorted(years)


def iter_daily_device_summary() -> Iterator[dict]:
    yield from operational_db().details.find()


def iter_trip_records() -> Iterator[dict]:
    """winicari.recetteSoc — sparse, 2021-2022 only, superseded by the reference DB's trips."""
    yield from operational_db().recetteSoc.find()


def iter_opendata_stations(variant: str = "Station_new") -> Iterator[dict]:
    """4 overlapping variants exist; Station_new is the default."""
    yield from opendata_db()[variant].find()


def iter_weather_calendar() -> Iterator[dict]:
    yield from opendata_db().historiqueJourMeteo.find()


# --- reference DB (sibling winicari repo, docs/reference_db_integration.md) ---
# Returns DataFrames directly, not iterators — source is already relational.

def reference_companies():
    return reference_db.read_table("companies")


def reference_stops():
    return reference_db.read_table("stops")


def reference_lines():
    return reference_db.read_table("lines")


def reference_line_stops():
    return reference_db.read_table("line_stops")


def reference_trips():
    return reference_db.read_table("trips")


def reference_trip_stops():
    """matched=0 rows had no real GPS fix at that stop — filter on
    matched=1 for anything travel-time-sensitive."""
    return reference_db.read_table("trip_stops")


def reference_tickets_daily():
    return reference_db.read_table("tickets_daily")


def reference_driver_services():
    """Observed service windows, not a real availability table —
    see docs/optimization_problem.md, Problem 3."""
    return reference_db.read_table("driver_services")
