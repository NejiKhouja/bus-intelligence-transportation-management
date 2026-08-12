# Database Discovery Report

Server: `mongodb://localhost:27017` (single MongoDB instance).
Discovered via `scripts/explore_database.py` — every number below is
reproducible by re-running that tool, not assumed.

This is the operational database of **Winicari**, a ticketing/AOVC
(GPS-tracking-and-ticketing device) platform used by ~10 regional bus
operators in Tunisia (S.R.T.K / Kasserine, S.R.T.BIZERTE, S.T.S / Sousse,
SRT.ELGOUAFEL / Gafsa, S.R.T.SELIANA, S.R.T.M / Médenine, TCV / Tunis,
TUS / Tunis, EPE-TVE / Annaba, SORETRAS). All four databases below live
on the same server and are logically one system.

## Databases found

| Database | Purpose | Relevant to this project |
|---|---|---|
| `winicari` | Live operational data: vehicles, routes, stops, fares, live GPS, live tickets, app/admin metadata | Yes — primary source for master data (routes, vehicles, stops) and the live/rolling GPS + ticket feeds |
| `Historique_Tickets` | Yearly archive of every ticket ever sold, 2019–2026 | Yes — primary demand dataset |
| `Historique_pos` | One collection per calendar day (`dYYYYMMDD`) of GPS pings, 2022-01-21 → 2026-06-21 | Yes — primary GPS/travel-time dataset |
| `OpenData` | Geocoded stop reference data, Tunisian admin geography, weather calendar | Yes — reference/exogenous data |
| `admin`, `config`, `local` | MongoDB system databases | No |

## `winicari` — collection inventory

Sizes are `estimated_document_count()` (metadata-based, not a full scan).

### Relevant to this project

| Collection | ~Count | What it is |
|---|---|---|
| `societe` | 10 | Operator master data: name, full name, governorate, address, active flag |
| `bus` | 772 | Vehicle master data: code, matricule (plate), capacity, max speed, operator, active/fonctionnel flags, last known GPS position |
| `ligne` | 402 | Route master data: code, operator, origin/destination (FR+AR), **ordered** list of internal stop IDs and names, optional OpenData stop-code + lat array for routes that have been geocoded |
| `station` | 289 | Stop master data (subset of stops): stop_id, name FR/AR, lat/lon (as strings), occasionally an embedded `horaires` array of scheduled departure times per line |
| `STOPS.T.S`, `STOPS.R.T.K`, `STOPS.R.T.M`, `STOPS.R.T.BIZERTE`, `STOPS.R.T.SELIANA`, `STOPSORETRAS`, `STOPSRT.ELGOUAFEL`, `STOPEPE-TVE`, `STOPS.T.C.I`, `STOPTCV` | 26–1,562 each | Per-operator stop-sequence tables: route number, stop number (position in sequence), a `NAMENR` code, cumulative km. One family of tables per operator instead of one shared schema — a real fragmentation issue, not a modeling choice |
| `price` | 51,660 | Fare matrix: route, from-stop, to-stop, price, fare type, operator |
| `klm` | 3,331 | Cumulative distance per route/stop (operator, route, stop, km). **Field names are mojibake-corrupted** on this legacy collection (e.g. `Soci�t�` instead of `Société`) |
| `ticket` | 13,401 | **Live** ticket sales, rolling ~1-week window (2026-06-16 → 2026-06-22 observed) before rows age into `Historique_Tickets`. Heavily denormalized: each ticket embeds a full snapshot of its device/operator/vehicle |
| `position` | 64,431 | **Live** GPS pings, same rolling ~1-week window (2026-06-22 observed). Same embedding pattern as `ticket` |
| `details` | 7,881 (+ `details_OLD`: 25,306) | Per-device/bus/line/day rollup: ticket count, revenue breakdown by type (cash, favor, requisition, discount tiers). Date range observed: 2025-02-03 → 2026-06-22 |
| `recetteSoc` | 452 | Closest thing to a "trip" record: one row per completed service run with average speed, distance travelled, ticket count, revenue, direction (Aller/Retour). Sparse — only 2021–2022 observed |
| `panne` | 453 | Breakdown/incident log: bus, driver, timestamp, incident type |
| `centre` | 11 | Depot/agency per operator |
| `demande_ligne` | 93 | Free-text customer requests for new routes — sparse and inconsistently filled (`de`/`vers`/`heure_demandée`/`jour_demandée`, several docs missing most fields) |
| `NamesConv` | 1,116 | Driver code → name/phone lookup. No shift, availability, or schedule data |
| `Names` | 1,788 | Legacy stop-name-code lookup per operator |

### Present but not relevant to this project (app/account/support plumbing)

`session_ouverte` (web login logs w/ IP geolocation), `ConfirmationToken`,
`notifications`, `impression` (in-app feedback/error counters), `admin`,
`adminC`, `userCaisse`, `owner`, `sav`, `windev`, `Nouveautes`,
`facebook`, `appareil` (device↔operator registry — referenced by GPS/
ticket docs but not itself a planning input), `historiqueStation` (dirty,
41 docs), `stop` (7 empty shell documents, unrelated to `station`).
Empty (0 docs): `faveur`, `alert`, `bagage`, `paiement`, `recharge`,
`requisition`, `stat_societes`, `photo.files`, `photo.chunks`,
`HistoriqueElma80`, `historiqueTicket`.

## `Historique_Tickets` — yearly ticket archive

One collection per year, `Ticket2019` … `Ticket2026`:

| Year | ~Count | `date_service` range observed |
|---|---|---|
| 2019 | 241,725 | (no `date_service` on earliest doc; last: 2019-12-25) |
| 2020 | 216,639 | 2020-01-01 → 2020-10-05 |
| 2021 | 876,158 | 2021-01-01 → 2021-12-08 |
| 2022 | 1,270,905 | 2022-01-01 → 2022-12-19 |
| 2023 | 491,108 | 2023-01-01 → 2023-11-25 |
| 2024 | 1,080,200 | 2024-01-01 → 2024-12-27 |
| 2025 | 926,743 | 2025-01-01 → 2025-12-29 |
| 2026 (partial year) | 383,239 | 2026-01-01 → 2026-06-27 |

Total ≈ **5.5M ticket records**, ~7.5 years of history. Each document is a
per-ticket sale with route/origin/destination stop codes, price, the
service date vs. the actual sale timestamp (both present, occasionally
different), and driver/vehicle/operator codes. Note the observed count
dip in 2023 (491k, vs 1.27M in 2022 and 1.08M in 2024) and the fact that
no year has full clean coverage to Dec 31 — worth asking the business
whether this reflects real gaps (an operator or device outage) or an
export/archival lag rather than assuming it's a real demand drop.

## `Historique_pos` — daily GPS archive

**1,603 daily collections**, named `dYYYYMMDD`, spanning
**2022-01-21 → 2026-06-21** (~4.5 years). Per-day document counts vary
widely (from single digits to >120,000/day), which tracks with how many
devices were active/reporting that day rather than a fixed schedule.
Each document has the identical schema to `winicari.position` — a GPS
ping with an embedded snapshot of the service/bus/operator/device at
ping time. This is the largest dataset in the system by a wide margin
(order of 10s of millions of GPS pings in total, extrapolating from the
sampled per-day counts) — extract incrementally per day, never in bulk.

## `OpenData` — reference data

| Collection | ~Count | What it is |
|---|---|---|
| `Station` | 2,898 | Geocoded stop reference: code, name FR/AR, lat/lng |
| `Station2` | 2,525 | A second, differently-sourced geocoded stop list (no `code_station` populated) |
| `Station_new` | 1,212 | Appears to be the curated/deduplicated successor to `Station` (adds `code_stationSTS` linkage on some rows) |
| `Station_sts` | 1,113 | A third stop list, lat/lng stored as strings, tied to an "STS" numbering |
| `Delegation` | 264 | Tunisian administrative delegations: name, lat/lng, governorate code |
| `GOV` | 24 | Tunisia's 24 governorates: code, name |
| `historiqueJourMeteo` | 1,252 | Per-station calendar: date, weekday index, `ferie` (public holiday), `vacanceScolaire` (school break), `weekend`, `conditionMeteo` (French-language weather description) |
| `USER` | 6 | OAuth profile records — not relevant |

Four overlapping station tables (`Station`, `Station2`, `Station_new`,
`Station_sts`) with no single canonical source is itself a data-quality
finding, not just an inventory note — see `docs/data_dictionary.md`.

## Relationship map (confirmed, not assumed)

```
winicari.societe (operator)
   |
   ├── winicari.bus (vehicle)              [bus.societe == societe.Nom, string join]
   ├── winicari.ligne (route)              [ligne.societe == societe.Nom]
   ├── winicari.centre (depot)             [centre.societe == societe.Nom]
   └── winicari.NamesConv (driver)         [NamesConv.societe == societe.Nom]

winicari.ligne (route)
   |
   ├── stationnames[] / stations[]         ordered, index-aligned arrays — the route's
   |                                        stop sequence, joined by position not by ID
   └── station_opendata[] / array_lat_opendata[]   present on ~194/402 routes (48%);
                                            station_opendata codes match
                                            OpenData.Station(_new).code_station format
                                            (8-digit codes like "42590001") — confirmed
                                            by direct string comparison, not inferred

winicari.ticket / Historique_Tickets.Ticket<year> (ticket)
   |
   ├── codeLigne / CodeRoute  -> ligne.code           (route)
   ├── bus.code / CodeBus     -> bus.code              (vehicle)
   ├── appareil.societe.Nom / Societe -> societe.Nom   (operator)
   └── origine/destination (numeric stop position, e.g. "01", "22") -> ligne.stations[i]
       by POSITION in the route's stop array, not by a stop document _id

winicari.position / Historique_pos.d<day> (GPS ping)
   |
   ├── service.codeLigne -> ligne.code
   ├── service.bus.code  -> bus.code
   └── service.appareil.societe -> societe.Nom
```

**Important caveats about these relationships:**

- There is **no ObjectId foreign key** anywhere in this schema between
  routes/tickets/GPS/vehicles — every join is a string or numeric code
  match (`codeLigne`, `CodeBus`, operator name string). This works but
  means joins are fragile to typos/case differences (see
  `data_dictionary.md` for the `winicari`/`Winicari` duplicate).
- Origin/destination on tickets are **positions within a route's stop
  array**, not stop document IDs — resolving a ticket's actual stop
  names/coordinates requires joining through `ligne.stations`/
  `stationnames` by index, then (if available) through
  `station_opendata` to get coordinates. This chain breaks for the ~52%
  of routes without `station_opendata`.
- `winicari.ticket` and `winicari.position` are **rolling live windows**
  (~1 week), not the historical record — always extract history from
  `Historique_Tickets` / `Historique_pos` instead.

## Historical depth summary

| Dataset | Depth |
|---|---|
| Ticket sales (`Historique_Tickets`) | 2019-01-01 → 2026-06-27 (~7.5 years) |
| GPS pings (`Historique_pos`) | 2022-01-21 → 2026-06-21 (~4.5 years) |
| Weather/calendar (`OpenData.historiqueJourMeteo`) | 2022-01 → 2023-08+ observed on sampled stations, coverage per-station not per-network |
| Vehicle/route/stop master data | Current snapshot only, `dateAjout` fields go back to 2018-12-30 |

## Data-quality findings (see also `data_dictionary.md`)

- **Operator naming is inconsistent**: `winicari.bus` has 14 distinct
  `societe` strings for what `winicari.societe` lists as 10 real
  operators — includes case-duplicate `winicari`/`Winicari` (the platform
  name itself, not a real operator, incorrectly used as an operator on
  some vehicles) and `S.R.T.GAFSA` alongside `SRT.ELGOUAFEL` (Gafsa's
  actual operator record) as separate strings.
- **~52% of routes (208/402) have no `station_opendata`/`array_lat_opendata`**,
  meaning half the route network has no coordinate-based geometry —
  only an ordered list of stop names/IDs.
- **52.6% of vehicles have an empty `matricule`** (license plate)
  sampled from `winicari.bus`.
- **klm collection has corrupted field names** (mojibake on `Société`
  and related French accented keys) from a legacy codepage mismatch.
- **GPS speed outliers exist**: a same-vehicle jump from 30.86°N to
  34.38°N latitude across 2 minutes was observed in
  `Historique_pos.d20260601`, i.e. an initial-fix or transmission glitch
  producing an implausible ~530 km/h computed speed on the very first
  segment of that vehicle's day — rare (0.016% of a 5,000-row sample
  exceeded 120 km/h) but present, so downstream travel-time code must
  filter it rather than trust every consecutive pair of pings.
- **`recetteSoc` (the closest thing to a trip table) is sparse and
  stale** — only 452 documents, all from 2021–2022 — it was apparently
  discontinued in favor of `details`/`details_OLD`, which don't record
  per-trip speed/distance, only per-device/day aggregates.
- **No dedicated schedule/timetable collection exists.** The only
  schedule-like data is an optional `horaires` array embedded in a
  minority of `winicari.station` documents (departure/return times per
  line at that stop) — far short of a full timetable.
- **No driver availability/shift data exists** — `NamesConv` is a
  name/phone lookup only.
