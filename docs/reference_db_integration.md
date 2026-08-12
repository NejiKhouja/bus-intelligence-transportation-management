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
`travel_times_from_trip_stops()` gives 197,364 per-leg times (median
211s) already corrected for loop routes and dark periods. Use
`build_gps_segments()` only as a fallback for days/companies the
reference DB doesn't cover.

**Driver scheduling** is still not feasible. `driver_services` records
when a device was selling tickets, not when a driver was actually
available — descriptive only, not a scheduling constraint.

## New quality issues found here

- Leg travel times from `trip_stops` go up to ~10.8h on `matched=1`
  legs — a matched fix at both ends doesn't rule out a multi-hour dark
  gap in between. Needs a max-duration filter before modeling, not just
  trusting `matched=1`.
- `driver_services` shift lengths range from -630 min to 137,400 min
  (median 323 min, which is fine) — negative and multi-day values are
  bad data, not real shifts. Bound to something like 0–16h before using.
- 185/402 lines (46%) still have no stop geometry even after the 6-tier
  resolver — missing OpenData coverage for smaller villages, mostly
  S.R.T.SELIANA and the Winicari placeholder. Not fixable with more
  code; travel-time/schedule work only covers the other 54%.

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

driver_services = extraction.extract_driver_services()  # descriptive only
alias_map = extraction.build_company_alias_map()
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
