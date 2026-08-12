# Data Dictionary

Field-level reference for the collections this project actually reads
from (via `src/database/queries.py`), plus the normalized schemas
`src/data/extraction.py` produces from them. For the full collection
inventory (including irrelevant ones) see `docs/database.md`.

## Raw collections

### `winicari.societe` (operator master, 10 docs)

| Field | Type | Notes |
|---|---|---|
| `Nom` | string | Short operator code, e.g. `S.R.T.K` — used as the join key everywhere else |
| `nomComplet` | string | Full name |
| `Gouvernorat` | string | Tunisian governorate |
| `active` | bool | 4 of 10 operators are `active: false` in this snapshot |
| `Email`, `telephone`, `Adresse`, `urlPhoto`, `NomAR`, `nom_base_guichet`, `pays` | string | Contact/branding metadata, not planning-relevant |

### `winicari.bus` (vehicle master, 772 docs)

| Field | Type | Notes |
|---|---|---|
| `code` | int | Vehicle ID, used as join key (`bus.code`, `CodeBus`, `codeBus` elsewhere — capitalization varies by collection) |
| `matricule` | string | License plate; **empty string in 52.6% of documents**, not a real plate |
| `societe` | string | Operator — see naming-inconsistency note in `database.md` |
| `nbrPlace` | string (numeric) | Seat capacity, stored as string — must be cast |
| `vitesseMax` | string (numeric) | Max rated speed km/h, stored as string |
| `active`, `fonctionnel` | bool | Two separate flags — `active` (registered/in service) vs `fonctionnel` (currently operational); only 162/772 are `fonctionnel: true` in this snapshot, so most vehicle rows are historical/retired, not a live fleet list |
| `localisation` / `localisationancien` | embedded `{x, y}` | Last known / previous GPS fix. **`x` is latitude, `y` is longitude** despite the naming — confirmed against Tunisia's bounding box (lat 30–38°N, lon 7–12°E) |
| `distanceParc`, `distanceParcAncien`, `new_distance` | number | Odometer-style cumulative distance fields; relationship between the three is not documented anywhere and wasn't reverse-engineered here |
| `dateAjout` | string `DD/MM/YYYY` | Date vehicle was added to the platform |

### `winicari.ligne` (route master, 402 docs)

| Field | Type | Notes |
|---|---|---|
| `code` | string | Route ID |
| `societe` | string | Operator |
| `orfr`/`orar`, `desfr`/`desar` | string | Origin/destination name, French and Arabic |
| `nbrstations` | int | Stop count |
| `stations` | array[string] | Internal stop IDs, **ordered** to match the route sequence |
| `stationnames` | array[string] | Stop names (French), index-aligned with `stations` |
| `stationnamesAR` | array[string] | Stop names (Arabic), index-aligned |
| `station_opendata` | array[string] | OpenData `code_station` values, index-aligned — **present on only ~194/402 routes (48%)** |
| `array_lat_opendata` | array[float] | Latitudes index-aligned with `station_opendata` — note: only latitude is embedded here, not longitude; longitude must come from joining `station_opendata` codes back to `OpenData.Station_new` |

### `winicari.ticket` (live tickets, rolling ~1 week)

Deeply denormalized — every ticket embeds a full snapshot of its device,
operator, and vehicle at sale time (`appareil.societe`, `appareil.bus`
duplicate data already in `societe`/`bus` collections). Key top-level
fields: `idTicket`, `codeLigne`, `origine`/`destination` (stop **position
strings**, e.g. `"01"`, `"22"` — not stop IDs), `prix`, `voyage`
(direction: int, meaning not documented — 0/1/2 observed, tentatively
outbound/return/unassigned), `date` (BSON datetime, reliable).

### `Historique_Tickets.Ticket<year>` (ticket archive, 2019-2026)

Same conceptual record as `winicari.ticket` but capitalized differently
and richer: adds `date_service`/`jour_service` (the service day, which
can differ from `date_ticket`/`date` for late-night trips crossing
midnight) and `heure_debut_ticket`/`heure_fin_ticket` (device's service
start/end time, not the individual ticket's trip time — easy to
misinterpret as a trip duration). `CodeRoute` here is the route ID field
name (vs. `codeLigne` on the live collection) — **field names are not
consistent between the live and archived ticket schemas**, confirmed by
direct inspection, so `src/data/extraction.py` has two separate flatten
functions rather than one shared mapping.

### `winicari.position` / `Historique_pos.d<YYYYMMDD>` (GPS pings)

| Field | Type | Notes |
|---|---|---|
| `localisation.x` / `.y` | float | Latitude / longitude (reversed naming, see `bus.localisation` note above) |
| `speed` | float | km/h, reported by device; can be 0 (idle) or occasionally implausible (see quality findings) |
| `direction` | float or null | Compass bearing degrees; null observed when the device couldn't compute one (e.g. stationary) |
| `date` | BSON datetime | Ping timestamp, reliable |
| `dateStr` | string `YYYY/MM/DD HH:MM:SS` | Same timestamp, string-formatted, redundant with `date` |
| `service.codeLigne` | string | Route ID at ping time |
| `service.bus.code` | int | Vehicle ID |
| `service.bus.voyages` | string | `"ALLER"`/`"RETOUR"` — direction of current trip leg |
| `service.appareil.societe.Nom` | string | Operator |

### `OpenData.Station_new` (geocoded stops, 1,212 docs — used as the
canonical stop table by `extraction.extract_opendata_stops()`)

| Field | Type | Notes |
|---|---|---|
| `code_station` | string | 8-digit code, matches `ligne.station_opendata` entries |
| `nom_fr` / `nom_ar` | string | Stop name |
| `lat` / `lng` | float | Coordinates (note: `lng` not `lon` as the key name here) |

`Station`, `Station2`, `Station_sts` are alternate/overlapping stop
tables from different import batches — not merged into one canonical
table by this project because there's no documented rule for resolving
conflicts between them (different coordinate precision, different
subsets of stops, `Station2` has no `code_station` at all). Treat
`Station_new` as the working default and revisit if it proves
incomplete for a given operator's routes.

### `winicari.klm` (route distance table, 3,331 docs)

Field names are corrupted on this specific legacy collection: the
operator-name field appears as `Soci�t�` (mojibake for `Société`,
written under a different codepage than the rest of the database). Other
fields (`Routenr`, `StopNr`, `nbkm`) are unaffected. Access defensively —
don't assume `doc["Société"]` will match; iterate keys or use the
corrupted literal.

### `OpenData.historiqueJourMeteo` (weather/calendar, 1,252 docs)

One document per **station**, embedding a `historiqueJours` array of
calendar-day records (not one document per day — requires unnesting).
Per-day fields: `date`, `indexJour` (0=Monday..6=Sunday, ISO-style),
`ferie` (public holiday), `vacanceScolaire` (school holiday), `weekend`
(note: Tunisia's weekend is Sat/Sun in this data based on `indexJour`
5/6 flagged `weekend: true`), `conditionMeteo` (free-text French weather
description, not a coded enum — e.g. `"Pluie, Partiellement nuageux"`).
Coverage is per-station and inconsistent — the two sampled documents
had non-overlapping date ranges (one 2022-05 to 2023-08, another
starting 2022-01) — meaning this cannot be treated as one continuous
network-wide calendar without checking coverage per station first.

## Normalized schemas produced by `src/data/extraction.py`

These are what `src/features/` and any modeling code should consume —
they hide the raw-collection inconsistencies documented above.

**Route** (`extract_routes()`): `route_id, societe, origin_fr,
destination_fr, n_stops, stop_ids[], stop_names_fr[],
opendata_stop_codes[], has_opendata_geometry`

**Vehicle** (`extract_vehicles()`): `vehicle_id, matricule, societe,
capacity, max_speed_kmh, active, fonctionnel, date_added`

**Stop** (`extract_opendata_stops()`): `stop_code, name_fr, name_ar, lat,
lon`

**GPS ping** (`extract_live_gps()` / `extract_archived_gps_day()`):
`vehicle_id, route_id, societe, voyage_direction, timestamp, lat, lon,
speed_kmh, direction_deg` — lat/lon already corrected to the right order.

**GPS segment** (`transformations.build_gps_segments()`): `vehicle_id,
route_id, segment_start, segment_end, travel_time_s, distance_km,
avg_speed_kmh` — derived, not stored in MongoDB.

**Ticket / demand row** (`extract_archived_tickets()` /
`extract_live_tickets()`): `ticket_id, societe, route_id, vehicle_id,
origin_stop, destination_stop, price, voyage_direction, service_date,
sold_at` — `service_date` is `None` for live tickets (that field doesn't
exist on the live schema, only the archive).

**Aggregated demand** (`transformations.aggregate_demand()`): `route_id,
time_bucket, passenger_count, revenue`.
