"""Extraction: raw MongoDB documents -> normalized pandas DataFrames.

Only implemented for datasets confirmed to exist and be usable during
database discovery (see docs/database.md). Nothing here trains a model —
this is purely the MongoDB-independent representation that Phase 9
modeling code will consume.
"""

from __future__ import annotations

import pandas as pd

from src.database import queries
from src.data.cleaning import normalize_societe_name, parse_flexible_datetime, swap_lat_lon_if_needed


def extract_routes() -> pd.DataFrame:
    """winicari.ligne -> one row per route.

    Columns:
        route_id, societe, origin_fr, destination_fr, n_stops,
        stop_ids (list[str]), stop_names_fr (list[str]),
        has_opendata_geometry (bool)
    """
    rows = []
    for doc in queries.iter_routes():
        opendata_codes = doc.get("station_opendata")
        rows.append({
            "route_id": doc.get("code"),
            "societe": normalize_societe_name(doc.get("societe")),
            "origin_fr": doc.get("orfr"),
            "destination_fr": doc.get("desfr"),
            "n_stops": doc.get("nbrstations"),
            "stop_ids": doc.get("stations") or [],
            "stop_names_fr": doc.get("stationnames") or [],
            "opendata_stop_codes": opendata_codes or [],
            "has_opendata_geometry": bool(opendata_codes),
        })
    return pd.DataFrame(rows)


def extract_vehicles() -> pd.DataFrame:
    """winicari.bus -> one row per vehicle.

    Columns: vehicle_id, matricule, societe, capacity, max_speed_kmh,
    active, fonctionnel, date_added
    """
    rows = []
    for doc in queries.iter_vehicles():
        rows.append({
            "vehicle_id": doc.get("code"),
            "matricule": doc.get("matricule") or None,
            "societe": normalize_societe_name(doc.get("societe")),
            "capacity": pd.to_numeric(doc.get("nbrPlace"), errors="coerce"),
            "max_speed_kmh": pd.to_numeric(doc.get("vitesseMax"), errors="coerce"),
            "active": doc.get("active"),
            "fonctionnel": doc.get("fonctionnel"),
            "date_added": parse_flexible_datetime(doc.get("dateAjout")),
        })
    return pd.DataFrame(rows)


def extract_companies() -> pd.DataFrame:
    """winicari.societe -> one row per operator."""
    rows = []
    for doc in queries.iter_companies():
        rows.append({
            "societe": normalize_societe_name(doc.get("Nom")),
            "full_name": doc.get("nomComplet"),
            "governorate": doc.get("Gouvernorat"),
            "active": doc.get("active"),
        })
    return pd.DataFrame(rows)


def extract_opendata_stops(variant: str = "Station_new") -> pd.DataFrame:
    """OpenData.<variant> -> one row per geocoded stop.

    Columns: stop_code, name_fr, name_ar, lat, lon
    """
    rows = []
    for doc in queries.iter_opendata_stations(variant):
        rows.append({
            "stop_code": doc.get("code_station") or None,
            "name_fr": doc.get("nom_fr"),
            "name_ar": doc.get("nom_ar"),
            "lat": pd.to_numeric(doc.get("lat"), errors="coerce"),
            "lon": pd.to_numeric(doc.get("lng"), errors="coerce"),
        })
    return pd.DataFrame(rows)


def _flatten_gps_doc(doc: dict) -> dict:
    loc = doc.get("localisation") or {}
    lat, lon = swap_lat_lon_if_needed(loc.get("x"), loc.get("y"))
    service = doc.get("service") or {}
    bus = service.get("bus") or {}
    return {
        "vehicle_id": bus.get("code"),
        "route_id": service.get("codeLigne"),
        "societe": normalize_societe_name(service.get("societe")),
        "voyage_direction": bus.get("voyages"),
        "timestamp": parse_flexible_datetime(doc.get("date")),
        "lat": lat,
        "lon": lon,
        "speed_kmh": doc.get("speed"),
        "direction_deg": doc.get("direction"),
    }


def extract_live_gps() -> pd.DataFrame:
    """winicari.position -> normalized GPS ping table. Rolling ~1 week
    window; use extract_archived_gps_day() for historical depth."""
    return pd.DataFrame(_flatten_gps_doc(d) for d in queries.iter_live_gps())


def extract_archived_gps_day(day: str) -> pd.DataFrame:
    """Historique_pos.d<day> -> normalized GPS ping table for one calendar
    day. day format: 'YYYYMMDD'. Call once per day and concatenate/persist
    incrementally — do not loop over all 1,600+ days into one DataFrame."""
    return pd.DataFrame(_flatten_gps_doc(d) for d in queries.iter_archived_gps_for_day(day))


def _flatten_ticket_doc(doc: dict, archived: bool) -> dict:
    if archived:
        return {
            "ticket_id": doc.get("IDTicket"),
            "societe": normalize_societe_name(doc.get("Societe")),
            "route_id": doc.get("CodeRoute"),
            "vehicle_id": doc.get("CodeBus"),
            "origin_stop": doc.get("origine"),
            "destination_stop": doc.get("Distination"),
            "price": doc.get("Prix"),
            "voyage_direction": doc.get("voyage"),
            "service_date": parse_flexible_datetime(doc.get("jour_service")),
            "sold_at": parse_flexible_datetime(doc.get("date")),
        }
    appareil = doc.get("appareil") or {}
    societe = (appareil.get("societe") or {}).get("Nom")
    return {
        "ticket_id": doc.get("idTicket"),
        "societe": normalize_societe_name(societe),
        "route_id": doc.get("codeLigne"),
        "vehicle_id": (doc.get("bus") or {}).get("code"),
        "origin_stop": doc.get("origine"),
        "destination_stop": doc.get("destination"),
        "price": doc.get("prix"),
        "voyage_direction": doc.get("voyage"),
        "service_date": None,
        "sold_at": parse_flexible_datetime(doc.get("date")),
    }


def extract_live_tickets() -> pd.DataFrame:
    """winicari.ticket -> normalized demand table. Rolling ~1 week window."""
    return pd.DataFrame(_flatten_ticket_doc(d, archived=False) for d in queries.iter_live_tickets())


def extract_archived_tickets(year: int) -> pd.DataFrame:
    """Historique_Tickets.Ticket<year> -> normalized demand table.
    This is the primary demand-forecasting dataset (2019-2026 available).
    Call once per year and persist incrementally (see data/README.md) —
    a single year can already be 200k-1.3M rows."""
    return pd.DataFrame(_flatten_ticket_doc(d, archived=True) for d in queries.iter_archived_tickets(year))
