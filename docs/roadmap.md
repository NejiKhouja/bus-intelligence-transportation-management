# Roadmap

Ordered by dependency, not calendar time.

## Resolved

- Operator-name inconsistency — `S.R.T.GAFSA`==`SRT.ELGOUAFEL`,
  `winicari`/`Winicari` is a placeholder kept separate. Handled in
  `cleaning.normalize_societe_name()` / `extraction.build_company_alias_map()`.
- Canonical stop table — reference DB's clustered `stops` (3,248 rows)
  supersedes the 4 overlapping `OpenData` variants.
- 2023 ticket dip — confirmed device outage, not real demand drop.
  Treat 2023 as under-observed in demand models.
- Missing-schedule blocker — partially resolved via
  `derive_empirical_schedule()` on reconstructed trips.
- `trip_stops` bad-leg patterns — `travel_times_from_trip_stops()` now
  excludes skipped-stop spans and dark-gap legs by default (see
  `reference_db_integration.md`). ~0.2% residual outliers remain; cap by
  percentile before training.
- Vehicle-operational signal — `derive_fleet_operational_status()`
  combines GPS trips (69 vehicles) with a fallback across all 8 years of
  `Historique_Tickets` (157 more) against the full 772-vehicle roster.
  Confirms `fonctionnel` is unreliable: 125/162 `fonctionnel=True`
  vehicles have no recent activity under this check. See
  `reference_db_integration.md` for the full breakdown.

## Immediate next steps

1. Ask the business about the 536/772 vehicles (70% of the roster) with
   **zero** activity signal across GPS trips and 8 years of ticket sales
   — is `winicari.bus` meant to be a current fleet list, or has it just
   never been pruned? This affects whether vehicle allocation should
   plan against 772, ~226, or something the business defines separately.
2. Extract/persist a full year of tickets + a representative GPS month
   into `data/processed/`, running `validation.py` for real (not
   sampled) missing/invalid rates.
3. Decide how to treat the 46% of lines with no resolved stop geometry
   — out of scope, or a geocoding effort to close it.
4. If leg distance is needed for travel-time features, compute it from
   `extract_reference_stops()` coordinates (haversine) rather than
   `trip_stops.dist_m`, which is a match-quality distance, not a leg
   distance (see `reference_db_integration.md`).

## Phase A — Demand forecasting (feasible now)

- Persist `aggregate_demand()` for all years, daily + hourly.
- Join `historiqueJourMeteo` once per-station coverage is confirmed.
- Ship the naive last-week baseline first; only add LightGBM/XGBoost if
  it measurably beats it.

## Phase B — Travel-time prediction (feasible)

- Use `travel_times_from_trip_stops()` (reference DB) over
  `build_gps_segments()` (raw GPS) — already matched/corrected.
- Cap the residual duration outliers (see Resolved, above) before training.
- Baseline: historical mean per leg/hour/day-of-week before any learned model.

## Phase C — Vehicle allocation (feasible)

- Implement `vehicle_optimizer.py` against Phase A's demand and
  `derive_fleet_operational_status()`, once step 1 above settles what
  "the fleet" actually means for planning purposes.

## Phase D — Schedule optimization (feasible, empirical baseline)

- Use `derive_empirical_schedule()` as the baseline to optimize headway
  against. A real published timetable from the business would validate
  it further but isn't required to start.

## Out of scope

- Driver scheduling — no availability data exists (Problem 3).
- Anything already covered by the existing AI layer (RAG chatbot,
  ETA/delay, anomaly detection) — read-only reuse, no duplication.
