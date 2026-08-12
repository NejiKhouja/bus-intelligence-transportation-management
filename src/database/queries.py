"""Domain-specific read queries against the collections identified as
relevant during database discovery (see docs/database.md). Kept separate
from explorer.py so callers don't need to know raw collection names.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator

from .mongo_client import opendata_db, operational_db, pos_archive_db, tickets_archive_db


def iter_routes() -> Iterator[dict]:
    """winicari.ligne — one document per route/line, embedding its ordered
    stop list. ~402 documents, safe to load fully."""
    yield from operational_db().ligne.find()


def iter_vehicles() -> Iterator[dict]:
    """winicari.bus — vehicle master data. ~772 documents."""
    yield from operational_db().bus.find()


def iter_companies() -> Iterator[dict]:
    """winicari.societe — the ~10 regional operators sharing this database."""
    yield from operational_db().societe.find()


def iter_fare_table() -> Iterator[dict]:
    """winicari.price — per route/stop-pair fares. ~52k documents."""
    yield from operational_db().price.find()


def iter_route_distances() -> Iterator[dict]:
    """winicari.klm — cumulative distance per route/stop. ~3.3k documents.
    Note: field names on this legacy collection are mojibake-corrupted
    (e.g. "Soci�t�" instead of "Société") — access by position or
    re-map keys defensively, don't assume the literal string round-trips."""
    yield from operational_db().klm.find()


def iter_live_gps(batch_size: int = 5000) -> Iterator[dict]:
    """winicari.position — rolling ~1 week window of live GPS pings before
    they age out into Historique_pos. ~64k documents currently."""
    yield from operational_db().position.find(batch_size=batch_size)


def iter_archived_gps_for_day(day: str, batch_size: int = 5000) -> Iterator[dict]:
    """Historique_pos.d<YYYYMMDD> — one collection per calendar day,
    2022-01-21 onward. Same document shape as iter_live_gps().

    day: e.g. "20260601"
    """
    coll_name = f"d{day}"
    yield from pos_archive_db()[coll_name].find(batch_size=batch_size)


def list_archived_gps_days() -> list[str]:
    """All available Historique_pos day-collections, sorted ascending, as
    'YYYYMMDD' strings (prefix stripped)."""
    names = pos_archive_db().list_collection_names()
    return sorted(n[1:] for n in names if n.startswith("d"))


def iter_live_tickets(batch_size: int = 5000) -> Iterator[dict]:
    """winicari.ticket — rolling ~1 week window of just-sold tickets."""
    yield from operational_db().ticket.find(batch_size=batch_size)


def iter_archived_tickets(year: int, batch_size: int = 5000) -> Iterator[dict]:
    """Historique_Tickets.Ticket<year> — full per-ticket sales archive,
    2019-2026. This is the primary demand-forecasting dataset."""
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
    """winicari.details — per-device/bus/line/day revenue+ticket-count
    rollup. ~7.9k current + ~25k in details_OLD."""
    yield from operational_db().details.find()


def iter_trip_records() -> Iterator[dict]:
    """winicari.recetteSoc — per-completed-service record with average
    speed, distance, and ticket count. Closest thing to a "trip" table in
    this database, but sparse (~452 documents, 2021-2022 only observed)."""
    yield from operational_db().recetteSoc.find()


def iter_opendata_stations(variant: str = "Station_new") -> Iterator[dict]:
    """OpenData.Station / Station2 / Station_new / Station_sts — geocoded
    stop reference data. Multiple variants exist; Station_new is the most
    complete/recent per discovery notes (see docs/database.md)."""
    yield from opendata_db()[variant].find()


def iter_weather_calendar() -> Iterator[dict]:
    """OpenData.historiqueJourMeteo — per-station calendar with weather
    condition, holiday, school-break and weekend flags. Useful exogenous
    features for demand forecasting."""
    yield from opendata_db().historiqueJourMeteo.find()
