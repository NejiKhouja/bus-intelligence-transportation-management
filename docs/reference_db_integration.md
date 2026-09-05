# Reference DB Integration

The sibling `winicari` repo (delay/ETA prediction, GPS fallback, anomaly
detection, chatbot) already built a clean SQLite reference DB on top of
the same raw MongoDB: canonical companies, clustered stops, resolved
line geometry, and reconstructed GPS trips. Rather than re-solve all of
that here, this project reads it read-only via
`src/database/reference_db.py`. The sibling repo and its models aren't
touched.

## Tables used

| Table | Rows | Replaces |
|---|---|---|
| `companies` | 12 | `winicari.societe` — resolved aliases (`S.R.T.K`/`S.R.T.K0`, `Winicari`/`winicari`), GPS activity window per operator |
| `stops` | 3,248 | The 4 overlapping `OpenData.Station*` tables — DBSCAN-clustered by proximity (150m), confidence-tiered |
| `lines` | 406 | `winicari.ligne`, scoped per `company_id` (raw line codes aren't unique across companies) |
| `line_stops` | 2,956 | `ligne.stations[]`/`stationnames[]` — resolved via a 6-tier method, 54% of lines covered |
| `trips` | 47,567 | Nothing existed in raw Mongo — reconstructed bus/day/direction runs with elapsed time, dwell, `match_rate` |
| `trip_stops` | 563,087 | `build_gps_segments()` — matched, loop/dark-period-aware arrival/departure/dwell per stop per trip |
| `tickets_daily` | 8,223 | `winicari.details`, same grain, cleaner keys |
| `driver_services` | 35,866 | Nothing existed — observed service windows inferred from ticket timestamps |

## What this unblocks

**Schedule optimization** was blocked on no timetable existing.
`transformations.derive_empirical_schedule()` builds a per
(line, direction, day-of-week, time-bucket) trip-frequency table from
`trips` — not a published schedule, but a real record of what the fleet
actually runs, which is what you'd want to optimize headway against
anyway.

**Travel time** is much better from `trip_stops` than from raw GPS.
`travel_times_from_trip_stops()` gives 174,529 per-leg times (median
180s) with two systemic bad-leg patterns filtered out by default (see
below). Use `build_gps_segments()` only as a fallback for days/companies
the reference DB doesn't cover.

**Driver scheduling** is still not feasible. `driver_services` records
when a device was selling tickets, not when a driver was actually
available — descriptive only, not a scheduling constraint.

**Vehicle operational status**: `derive_fleet_operational_status()`
combines two signals against the full 772-vehicle roster (762 unique
societe+vehicle_id pairs): `derive_operational_vehicles()` (GPS trips,
covers 69 vehicles) falls back to `derive_operational_vehicles_from_tickets()`
(ticket sales across all 8 years of `Historique_Tickets`, covers another
157) for companies/vehicles with no GPS history at all. Recency in both
is relative to the latest date in the data, not the system clock.

Result: 226/762 (30%) have some activity signal, split roughly 2:1
tickets-only vs GPS. The remaining 536 (70%) show **zero** activity in
either signal across the full 8-year archive — not "we lack a signal
for them," but no evidence they were ever actually used. Cross-checked
against `fonctionnel`: of the 162 vehicles marked `fonctionnel=True`,
125 (77%) have no recent activity under this check — confirms the flag
is unreliable, not just "sometimes stale."

## Quality issues found here

- **Two systemic bad-leg patterns in `trip_stops`**, both fixed by
  default in `travel_times_from_trip_stops()`:
  - ~12% of matched-to-matched stop pairs skip 1+ unmatched stops in
    between — not a real single leg. `had_gap`/`dark_s` on the
    destination does **not** reliably flag this: the worst case found (a
    10.8h span) has `had_gap=0` on its destination because the dark
    period is recorded on the *origin* stop instead, as pre-trip idle
    time. Fixed by checking that `seq` advances by exactly 1
    (`exclude_skipped_stops=True`).
  - Destination `had_gap=1` legs (real dark period between two actually
    consecutive stops) are separately excluded (`exclude_dark_gaps=True`).
  - Together these cut max leg duration from ~10.8h to ~6.5h and drop
    ~11.6% of raw pairs. A residual ~0.2% still exceed 1h with no flag
    at all (e.g. a bus idling long before really departing seq=0) — cap
    duration by percentile before training on this.
- **`trip_stops.dist_m` is not the distance travelled for a leg.**
  Checked against the sibling repo's `foundation.py`: it's the distance
  from the GPS fix that matched a stop to that stop's own coordinates
  (a match-quality metric), computed once per stop. There is no
  leg-distance field — computing one needs a haversine between the two
  stops' coordinates (`extraction.extract_reference_stops()`), not done
  here yet. Renamed to `arrival_match_distance_m` in this project's
  output to avoid the wrong assumption sticking.
- `driver_services` shift lengths range from -630 min to 137,400 min
  (median 323 min, which is fine) — negative and multi-day values are
  bad data, not real shifts. Bound to something like 0–16h before using.
- 185/402 lines (46%) still have no stop geometry even after the 6-tier
  resolver — missing OpenData coverage for smaller villages, mostly
  S.R.T.SELIANA and the Winicari placeholder. Not fixable with more
  code; travel-time/schedule work only covers the other 54%.
- 49 documents in `Historique_Tickets.Ticket2026` have `Societe: []`
  (empty array) instead of a string — `cleaning.normalize_societe_name()`
  now returns `None` for any non-string input instead of crashing.
- **70% of the vehicle roster (536/772) has no activity signal at all**
  across GPS trips or 8 years of ticket sales — see "vehicle operational
  status" above. Worth asking the business whether `winicari.bus` is
  meant to be a current fleet list or has just never been pruned.

## Usage

```python
from src.data import extraction, transformations

companies = extraction.extract_reference_companies()
stops = extraction.extract_reference_stops()
lines, line_stops = extraction.extract_reference_lines(), extraction.extract_reference_line_stops()

trips = extraction.extract_trips()
trip_stops = extraction.extract_trip_stops()
legs = transformations.travel_times_from_trip_stops(trip_stops)
schedule = transformations.derive_empirical_schedule(trips, freq_minutes=30)

alias_map = extraction.build_company_alias_map()
vehicles = extraction.extract_vehicles(alias_map=alias_map)
gps_ops = transformations.derive_operational_vehicles(trips, companies, recency_days=30)
ticket_activity = transformations.combine_ticket_activity(
    [extraction.extract_ticket_activity_by_bus(y, alias_map=alias_map) for y in range(2019, 2027)]
)
ticket_ops = transformations.derive_operational_vehicles_from_tickets(ticket_activity, recency_days=30)
fleet_status = transformations.derive_fleet_operational_status(vehicles, gps_ops, ticket_ops)

driver_services = extraction.extract_driver_services()  # descriptive only
```

## Still raw-Mongo-only

Per-ticket demand (`tickets_daily` is daily-aggregated, not per-ticket),
live/rolling GPS and tickets (reference DB is a point-in-time snapshot),
and the weather calendar (not part of the reference DB at all).

## Path

`REFERENCE_DB_PATH` assumes both repos sit side by side on the same
machine. If that's not true somewhere, set it explicitly or fall back
to the raw-Mongo extraction functions — `reference_db.is_available()`
tells you which mode you're in.
