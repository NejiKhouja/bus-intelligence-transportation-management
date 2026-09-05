"""Raw MongoDB documents -> normalized pandas DataFrames. Only for
datasets confirmed usable during discovery (docs/database.md). No model
training here.

`extract_reference_*` functions read the sibling winicari repo's SQLite
reference DB instead of raw MongoDB — see docs/reference_db_integration.md.
"""

from __future__ import annotations

import json

import pandas as pd

from src.database import queries
from src.data.cleaning import MANUAL_COMPANY_ALIASES, normalize_societe_name, parse_flexible_datetime, swap_lat_lon_if_needed


def _parse_json_list(value) -> list:
    """Some reference-DB text columns store a JSON array, others a plain
    string left over from before the column was made multi-valued."""
    if value is None:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return [value]


def build_company_alias_map() -> dict[str, str]:
    """alias -> canonical name, from the reference DB's companies.aliases
    plus MANUAL_COMPANY_ALIASES. Falls back to the manual list alone if
    the reference DB isn't reachable."""
    alias_map = dict(MANUAL_COMPANY_ALIASES)
    try:
        companies = queries.reference_companies()
    except Exception:
        return alias_map
    for _, row in companies.iterrows():
        canonical = row["canonical_name"]
        for alias in _parse_json_list(row["aliases"]):
            alias_map.setdefault(alias, canonical)
    return alias_map


def extract_routes() -> pd.DataFrame:
    """winicari.ligne -> route_id, societe, origin_fr, destination_fr,
    origin_ar, destination_ar, n_stops, stop_ids[], stop_names_fr[],
    opendata_stop_codes[], has_opendata_geometry."""
    rows = []
    for doc in queries.iter_routes():
        opendata_codes = doc.get("station_opendata")
        rows.append({
            "route_id": doc.get("code"),
            "societe": normalize_societe_name(doc.get("societe")),
            "origin_fr": doc.get("orfr"),
            "destination_fr": doc.get("desfr"),
            "origin_ar": doc.get("orar"),
            "destination_ar": doc.get("desar"),
            "n_stops": pd.to_numeric(doc.get("nbrstations"), errors="coerce"),
            "stop_ids": doc.get("stations") or [],
            "stop_names_fr": doc.get("stationnames") or [],
            "opendata_stop_codes": opendata_codes or [],
            "has_opendata_geometry": bool(opendata_codes),
        })
    return pd.DataFrame(rows)


def extract_vehicles(alias_map: dict[str, str] | None = None) -> pd.DataFrame:
    """winicari.bus -> vehicle_id, matricule, societe, capacity,
    max_speed_kmh, active, fonctionnel, date_added. Pass
    build_company_alias_map() as alias_map when joining against
    reference-DB-derived tables (e.g. derive_fleet_operational_status())
    so serial-number variants like S.R.T.K0 fold into S.R.T.K."""
    rows = []
    for doc in queries.iter_vehicles():
        rows.append({
            "vehicle_id": doc.get("code"),
            "matricule": doc.get("matricule") or None,
            "societe": normalize_societe_name(doc.get("societe"), alias_map),
            "capacity": pd.to_numeric(doc.get("nbrPlace"), errors="coerce"),
            "max_speed_kmh": pd.to_numeric(doc.get("vitesseMax"), errors="coerce"),
            "active": doc.get("active"),
            "fonctionnel": doc.get("fonctionnel"),
            "date_added": parse_flexible_datetime(doc.get("dateAjout")),
        })
    return pd.DataFrame(rows)


def extract_companies() -> pd.DataFrame:
    rows = []
    for doc in queries.iter_companies():
        rows.append({
            "societe": normalize_societe_name(doc.get("Nom")),
            "full_name": doc.get("nomComplet"),
            "full_name_ar": doc.get("NomAR"),
            "governorate": doc.get("Gouvernorat"),
            "active": doc.get("active"),
        })
    return pd.DataFrame(rows)


def extract_opendata_stops(variant: str = "Station_new") -> pd.DataFrame:
    """OpenData.<variant> -> stop_code, name_fr, name_ar, lat, lon."""
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
    """Rolling ~1wk window; use extract_archived_gps_day() for history."""
    return pd.DataFrame(_flatten_gps_doc(d) for d in queries.iter_live_gps())


def extract_archived_gps_day(day: str) -> pd.DataFrame:
    """day format 'YYYYMMDD'. Call per day and persist incrementally —
    don't loop over all 1,600+ days into one DataFrame."""
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
    return pd.DataFrame(_flatten_ticket_doc(d, archived=False) for d in queries.iter_live_tickets())


def extract_archived_tickets(year: int) -> pd.DataFrame:
    """Main demand dataset, 2019-2026. A single year can be 200k-1.3M rows."""
    return pd.DataFrame(_flatten_ticket_doc(d, archived=True) for d in queries.iter_archived_tickets(year))


def extract_ticket_activity_by_bus(year: int, alias_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Historique_Tickets.Ticket<year>, projected to just societe/bus/date
    -> one row per (societe, vehicle_id) with last_ticket_date and
    n_tickets for that year. Used to fill the fleet-operational-status
    gap left by extract_trips() (GPS-based, only 71/772 vehicles) — see
    transformations.derive_fleet_operational_status(). Pass
    build_company_alias_map() as alias_map — this archive uses
    'S.R.T.K0' as well as 'S.R.T.K', which only the fuller alias map
    (not MANUAL_COMPANY_ALIASES alone) folds together."""
    rows = []
    for doc in queries.iter_ticket_activity_fields(year):
        bus = doc.get("CodeBus")
        rows.append({
            "societe": normalize_societe_name(doc.get("Societe"), alias_map),
            "vehicle_id": str(bus) if bus is not None else None,
            "date": parse_flexible_datetime(doc.get("date")),
        })
    df = pd.DataFrame(rows).dropna(subset=["date", "societe", "vehicle_id"])
    return (
        df.groupby(["societe", "vehicle_id"])
        .agg(last_ticket_date=("date", "max"), n_tickets=("date", "count"))
        .reset_index()
    )


# --- reference DB (sibling winicari repo, docs/reference_db_integration.md) ---
# Prefer these over the raw-Mongo functions above wherever both exist.

def extract_reference_companies() -> pd.DataFrame:
    df = queries.reference_companies()
    df["aliases"] = df["aliases"].apply(_parse_json_list)
    return df


def extract_reference_stops() -> pd.DataFrame:
    """Supersedes extract_opendata_stops() — see reference_db_integration.md."""
    df = queries.reference_stops()
    df["aliases"] = df["aliases"].apply(_parse_json_list)
    df["source"] = df["source"].apply(_parse_json_list)
    return df


def extract_reference_lines() -> pd.DataFrame:
    return queries.reference_lines()


def extract_reference_line_stops() -> pd.DataFrame:
    return queries.reference_line_stops()


def extract_trips() -> pd.DataFrame:
    """Main travel-time ground truth — see
    transformations.travel_times_from_trip_stops()/derive_empirical_schedule()."""
    df = queries.reference_trips()
    for col in ("trip_start", "trip_end"):
        df[col] = pd.to_datetime(df[col], format="mixed")
    return df


def extract_trip_stops() -> pd.DataFrame:
    """563,087 rows — filter by trip_id rather than loading unfiltered
    for large-scale work."""
    df = queries.reference_trip_stops()
    for col in ("arrival", "departure"):
        df[col] = pd.to_datetime(df[col], format="mixed")
    return df


def extract_reference_tickets_daily() -> pd.DataFrame:
    df = queries.reference_tickets_daily()
    df["day"] = pd.to_datetime(df["day"], format="%Y%m%d")
    return df


def extract_driver_services() -> pd.DataFrame:
    """Descriptive only — see docs/optimization_problem.md Problem 3."""
    df = queries.reference_driver_services()
    df["day"] = pd.to_datetime(df["day"], format="%Y%m%d")
    for col in ("service_start", "service_end"):
        df[col] = pd.to_datetime(df[col], format="mixed")
    return df
