# Roadmap

Ordered by dependency, not calendar time.

## Resolved during discovery

- Operator-name inconsistency — confirmed: `S.R.T.GAFSA`==`SRT.ELGOUAFEL`,
  `winicari`/`Winicari` is a placeholder kept separate. Handled in
  `cleaning.normalize_societe_name()` / `extraction.build_company_alias_map()`.
- Canonical stop table — reference DB's clustered `stops` (3,248 rows)
  supersedes the 4 overlapping `OpenData` variants. Use
  `extraction.extract_reference_stops()`.
- 2023 ticket dip — confirmed device outage, not real demand drop or
  export gap. Treat 2023 as under-observed in demand models.
- Missing-schedule blocker — partially resolved via
  `transformations.derive_empirical_schedule()` on reconstructed trips.

## Immediate next steps

1. Extract/persist a full year of tickets + a representative GPS month
   into `data/processed/`, running `validation.py` for real (not
   sampled) missing/invalid rates.
2. Add a concrete filter for `trip_stops`/`trips` before modeling — leg
   travel-time and `driver_services` shift-length outliers
   (`reference_db_integration.md`) need a bound, not just a caveat.
3. Replace `fonctionnel` as the "is this vehicle operational" signal
   with recent trip/GPS activity — the flag is often stale (see
   `optimization_problem.md` Problem 2).
4. Decide how to treat the 46% of lines with no resolved stop geometry
   — out of scope, or a geocoding effort to close it.

## Phase A — Demand forecasting (feasible now)

- Persist `aggregate_demand()` for all years, daily + hourly.
- Join `historiqueJourMeteo` once per-station coverage is confirmed.
- Ship the naive last-week baseline first; only add LightGBM/XGBoost if
  it measurably beats it.

## Phase B — Travel-time prediction (feasible)

- Prefer `travel_times_from_trip_stops()` (reference DB) over
  `build_gps_segments()` (raw GPS) — already matched/corrected.
- Bound outliers before modeling (see step 2 above).
- Baseline: historical mean per leg/hour/day-of-week before any learned model.

## Phase C — Vehicle allocation (feasible)

- Implement `vehicle_optimizer.py` against Phase A's demand and an
  activity-derived operational fleet (not raw `fonctionnel`, see step 3).

## Phase D — Schedule optimization (feasible, empirical baseline)

- Use `derive_empirical_schedule()` as the baseline to optimize headway
  against. A real published timetable from the business would validate
  it further but isn't required to start.

## Out of scope

- Driver scheduling — no availability data exists (Problem 3).
- Anything already covered by the existing AI layer (RAG chatbot,
  ETA/delay, anomaly detection) — read-only reuse, no duplication.
