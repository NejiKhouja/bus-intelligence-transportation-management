# Data Dictionary

Field-level reference for collections read via `src/database/queries.py`
and the normalized schemas `src/data/extraction.py` produces. Full
collection inventory: `docs/database.md`.

## Raw collections

**`winicari.societe`** (10): `Nom` (join key, e.g. `S.R.T.K`),
`nomComplet`, `Gouvernorat`, `active` (4/10 false). Rest is
contact/branding metadata.

**`winicari.bus`** (772): `code` (join key; capitalization varies
elsewhere — `CodeBus`/`codeBus`), `matricule` (empty in 52.6%), `societe`,
`nbrPlace`/`vitesseMax` (numeric strings, must cast), `active` vs
`fonctionnel` (two separate flags — only 162/772 `fonctionnel: true`,
most rows are historical/retired), `localisation.{x,y}` (x=lat, y=lon,
despite naming — confirmed against Tunisia's bbox), `dateAjout`
(`DD/MM/YYYY`).

**`winicari.ligne`** (402): `code`, `societe`, `orfr`/`orar`+`desfr`/`desar`
(origin/destination FR+AR), `nbrstations`, `stations[]`/`stationnames[]`/
`stationnamesAR[]` (ordered, index-aligned), `station_opendata[]`
(OpenData codes, index-aligned, only on ~194/402 routes),
`array_lat_opendata[]` (latitude only — longitude needs joining
`station_opendata` back to `OpenData.Station_new`).

**`winicari.ticket`** (live, rolling ~1wk): denormalized, embeds a full
device/operator/vehicle snapshot per ticket. Key fields: `idTicket`,
`codeLigne`, `origine`/`destination` (stop position strings like `"01"`,
not stop IDs), `prix`, `voyage` (direction int, meaning undocumented —
0/1/2 observed), `date` (reliable BSON datetime).

**`Historique_Tickets.Ticket<year>`**: same idea as `winicari.ticket`
but different field names (`CodeRoute` vs `codeLigne`) and richer
(`date_service`/`jour_service` vs `date_ticket`/`date`, can differ for
late-night trips; `heure_debut_ticket`/`heure_fin_ticket` is the
device's service window, not a trip duration). Field names don't match
between live and archived schemas — hence two flatten functions in
`extraction.py`, not one shared mapping.

**`winicari.position` / `Historique_pos.d<YYYYMMDD>`**: `localisation.x`/`.y`
(lat/lon, reversed naming), `speed` (km/h, can be 0 or implausible),
`direction` (bearing, null when stationary), `date` (reliable),
`service.codeLigne`/`service.bus.code` (route/vehicle at ping time),
`service.bus.voyages` (`"ALLER"`/`"RETOUR"`).

**`OpenData.Station_new`** (1,212, used as default stop table by
`extract_opendata_stops()`): `code_station` (matches `ligne.station_opendata`),
`nom_fr`/`nom_ar`, `lat`/`lng`. `Station`/`Station2`/`Station_sts` are
overlapping alternates with no documented conflict-resolution rule —
`Station_new` is the working default (superseded project-wide by the
reference DB's clustered `stops` table, see
`reference_db_integration.md`).

**`winicari.klm`** (3,331): operator-name field is mojibake-corrupted
(`Soci�t�`) from a legacy codepage — access defensively, don't assume
`doc["Société"]` matches.

**`OpenData.historiqueJourMeteo`** (1,252): one doc per **station**,
embedding a `historiqueJours[]` calendar array (`date`, `indexJour`
0=Mon, `ferie`, `vacanceScolaire`, `weekend`, `conditionMeteo` free-text
French). Coverage is per-station and inconsistent — check before
treating as one continuous network-wide calendar.

## Normalized schemas (`src/data/extraction.py`)

- **Route** `extract_routes()`: `route_id, societe, origin_fr, destination_fr, n_stops, stop_ids[], stop_names_fr[], opendata_stop_codes[], has_opendata_geometry`
- **Vehicle** `extract_vehicles()`: `vehicle_id, matricule, societe, capacity, max_speed_kmh, active, fonctionnel, date_added`
- **Stop** `extract_opendata_stops()`: `stop_code, name_fr, name_ar, lat, lon`
- **GPS ping** `extract_live_gps()`/`extract_archived_gps_day()`: `vehicle_id, route_id, societe, voyage_direction, timestamp, lat, lon, speed_kmh, direction_deg` (lat/lon order-corrected)
- **GPS segment** `transformations.build_gps_segments()`: `vehicle_id, route_id, segment_start, segment_end, travel_time_s, distance_km, avg_speed_kmh` (derived)
- **Ticket/demand row** `extract_archived_tickets()`/`extract_live_tickets()`: `ticket_id, societe, route_id, vehicle_id, origin_stop, destination_stop, price, voyage_direction, service_date, sold_at` (`service_date` is `None` on live tickets)
- **Aggregated demand** `transformations.aggregate_demand()`: `route_id, time_bucket, passenger_count, revenue`

Reference-DB-backed schemas (companies/stops/lines/trips/trip_stops/
driver_services): see `docs/reference_db_integration.md`.
