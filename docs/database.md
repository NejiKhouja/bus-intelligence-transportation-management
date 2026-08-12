# Database

> The sibling `winicari` repo already fixed most of the issues below
> (company identity, stop clustering, line geometry, trip
> reconstruction) — see `reference_db_integration.md`. This doc is the
> raw MongoDB as found; the reference-DB doc wins where they overlap.

Server: `mongodb://localhost:27017`. Numbers here come from
`scripts/explore_database.py`, re-runnable, not eyeballed.

Winicari is a ticketing/GPS platform used by ~10 regional Tunisian bus
operators (S.R.T.K, S.R.T.BIZERTE, S.T.S, SRT.ELGOUAFEL, S.R.T.SELIANA,
S.R.T.M, TCV, TUS, EPE-TVE, SORETRAS).

## Databases

| Database | Purpose |
|---|---|
| `winicari` | Live ops: vehicles, routes, stops, fares, rolling ~1wk of live GPS/tickets, app metadata |
| `Historique_Tickets` | Yearly ticket archive, 2019–2026 — main demand dataset |
| `Historique_pos` | One collection/day (`dYYYYMMDD`) of GPS pings, 2022-01-21→2026-06-21 |
| `OpenData` | Geocoded stops, Tunisian admin geography, weather calendar |

(`admin`/`config`/`local` are Mongo system DBs, skipped.)

## `winicari` — collections that matter

| Collection | ~Count | Notes |
|---|---|---|
| `societe` | 10 | Operator master: name, governorate, active flag |
| `bus` | 772 | Vehicle master: code, matricule, capacity, max speed, operator, active/fonctionnel. `fonctionnel` is often stale — use recent trip/GPS activity to tell if a vehicle is actually running |
| `ligne` | 402 | Route master: code, operator, origin/destination FR+AR, ordered stop IDs/names, optional OpenData stop-code+lat array |
| `station` | 289 | Stop subset: stop_id, name FR/AR, lat/lon as strings, occasional `horaires` (departure times per line) |
| `STOPS.*` (10 per-operator tables) | 26–1,562 each | Per-operator stop-sequence: route/stop number, `NAMENR` code, cumulative km — one schema family per operator, not shared |
| `price` | 51,660 | Fare matrix: route, from/to stop, price, fare type, operator |
| `klm` | 3,331 | Cumulative distance per route/stop. Field names are mojibake (legacy codepage) |
| `ticket` | 13,401 | Live sales, rolling ~1wk before archiving to `Historique_Tickets`. Denormalized — embeds device/operator/vehicle snapshot |
| `position` | 64,431 | Live GPS, same rolling window, same embedding |
| `details` (+`details_OLD`) | 7,881 (+25,306) | Per-device/bus/line/day rollup: ticket count, revenue by type. 2025-02-03→2026-06-22 |
| `recetteSoc` | 452 | Closest thing to a trip record in raw Mongo (speed/distance/tickets/direction). Sparse, 2021–2022 only, superseded by the reference DB |
| `panne` | 453 | Breakdown log: bus, driver, timestamp, type |
| `centre` | 11 | Depot per operator |
| `demande_ligne` | 93 | Free-text new-route requests, sparse and dirty |
| `NamesConv` | 1,116 | Driver code → name/phone. No shift/availability |
| `Names` | 1,788 | Legacy stop-name-code lookup per operator |

Not relevant (app/account/support): `session_ouverte`, `ConfirmationToken`,
`notifications`, `impression`, `admin`, `adminC`, `userCaisse`, `owner`,
`sav`, `windev`, `Nouveautes`, `facebook`, `appareil`, `historiqueStation`,
`stop`. Empty: `faveur`, `alert`, `bagage`, `paiement`, `recharge`,
`requisition`, `stat_societes`, `photo.*`, `HistoriqueElma80`,
`historiqueTicket`.

## `Historique_Tickets`

One collection per year:

| Year | ~Count | `date_service` range |
|---|---|---|
| 2019 | 241,725 | → 2019-12-25 |
| 2020 | 216,639 | 2020-01-01 → 2020-10-05 |
| 2021 | 876,158 | 2021-01-01 → 2021-12-08 |
| 2022 | 1,270,905 | 2022-01-01 → 2022-12-19 |
| 2023 | 491,108 | 2023-01-01 → 2023-11-25 |
| 2024 | 1,080,200 | 2024-01-01 → 2024-12-27 |
| 2025 | 926,743 | 2025-01-01 → 2025-12-29 |
| 2026 (partial) | 383,239 | 2026-01-01 → 2026-06-27 |

~5.5M records, ~7.5 years. The 2023 dip (491k vs 1.27M in 2022, 1.08M in
2024) was a bunch of ticketing machines going offline that year, not a
real demand drop — exclude or downweight 2023 in demand models.

## `Historique_pos`

1,603 daily collections, 2022-01-21→2026-06-21. Per-day counts swing
from single digits to >120k depending on how many devices were active
that day — no fixed schedule. Same shape as `winicari.position`. Pull
one day at a time, never in bulk.

## `OpenData`

| Collection | ~Count | Notes |
|---|---|---|
| `Station` | 2,898 | Geocoded stops: code, name FR/AR, lat/lng |
| `Station2` | 2,525 | Second source, no `code_station` |
| `Station_new` | 1,212 | Curated successor to `Station` |
| `Station_sts` | 1,113 | Third list, lat/lng as strings |
| `Delegation` | 264 | Tunisian delegations: name, lat/lng, gov code |
| `GOV` | 24 | Tunisia's 24 governorates |
| `historiqueJourMeteo` | 1,252 | Per-station calendar: holiday/school-break/weekend/weather |
| `USER` | 6 | OAuth profiles, ignore |

Four overlapping station tables, no single source of truth — the
reference DB resolves this by clustering (see `reference_db_integration.md`).

## Relationships

```
societe (operator)
  ├── bus.societe, ligne.societe, centre.societe, NamesConv.societe   [string join]

ligne
  ├── stationnames[]/stations[]        ordered, index-aligned — route's stop sequence
  └── station_opendata[]/array_lat_opendata[]   only on ~194/402 routes (48%);
                                        codes match OpenData.Station(_new).code_station

ticket / Historique_Tickets.Ticket<year>
  ├── codeLigne/CodeRoute -> ligne.code
  ├── bus.code/CodeBus -> bus.code
  ├── appareil.societe.Nom/Societe -> societe.Nom
  └── origine/destination (stop POSITION, e.g. "01") -> ligne.stations[i], not a stop _id

position / Historique_pos.d<day>
  ├── service.codeLigne -> ligne.code, service.bus.code -> bus.code
  └── service.appareil.societe -> societe.Nom
```

No ObjectId foreign keys anywhere — every join is a string/numeric code,
fragile to typos and case. `ticket`/`position` are rolling ~1wk windows
only; use `Historique_Tickets`/`Historique_pos` for anything historical.

## Quality issues

- 14 `societe` strings for 10 real operators. `S.R.T.GAFSA` and
  `SRT.ELGOUAFEL` are the same operator (rename), `winicari`/`Winicari`
  is a platform placeholder kept separate from real operators. Handled
  in `cleaning.normalize_societe_name()`.
- ~52% of routes (208/402) have no `station_opendata` — no coordinate
  geometry, just stop names/IDs.
- 52.6% of vehicles have an empty `matricule`.
- `klm` has corrupted field names (mojibake, legacy codepage).
- GPS speed outliers: one vehicle jumped 30.86°N→34.38°N in 2 minutes in
  `Historique_pos.d20260601`, a ~530 km/h glitch. Rare (0.016% of a
  5,000-row sample over 120 km/h) but has to be filtered downstream.
- `recetteSoc`, the closest thing to a trip table, is sparse and stale
  (2021-2022 only) — superseded by the reference DB's `trips`/`trip_stops`.
- No schedule/timetable collection, just a sparse `horaires` array on
  some `station` docs. Partially covered by an inferred schedule from
  reference-DB trips, see `optimization_problem.md`.
- No driver availability data — `NamesConv` is name/phone only. The
  reference DB's `driver_services` gets closer but has its own quality
  problems, see `reference_db_integration.md`.
