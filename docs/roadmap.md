# Roadmap

Reflects what database discovery actually found (`docs/database.md`),
not the originally assumed scope. Ordered by dependency, not by
calendar time.

## Immediate next steps

1. **Resolve the operator-name inconsistency** (`winicari` vs
   `Winicari`, `S.R.T.GAFSA` vs `SRT.ELGOUAFEL`) with the business before
   it's baked into any per-operator aggregation — a wrong merge here
   silently splits or double-counts one operator's demand.
2. **Decide on a canonical stop table.** Four overlapping OpenData
   station tables exist (`Station`, `Station2`, `Station_new`,
   `Station_sts`). `extraction.py` currently defaults to `Station_new`;
   confirm with whoever owns OpenData ingestion whether that's actually
   the most complete/correct one, and get a plan for the ~52% of routes
   still missing `station_opendata` linkage.
3. **Extract and persist a full year of tickets + a representative month
   of GPS** (not just the one day / one year sampled during discovery)
   into `data/processed/`, running `src/data/validation.py` over the
   full extract to get real (not sampled) missing/invalid rates.
4. **Get an answer on the missing-schedule problem** (see
   `docs/optimization_problem.md`, Problem 1) — this determines whether
   schedule optimization is deliverable in this project's first phase or
   needs a data-collection prerequisite first.

## Phase A — Demand forecasting (feasible now)

- Persist demand aggregation (`transformations.aggregate_demand()`) for
  all available years per route, at daily and hourly granularity.
- Join `OpenData.historiqueJourMeteo` calendar flags once per-station
  coverage is confirmed (see `data_dictionary.md` — coverage was
  inconsistent across the two sampled stations).
- Ship the naive last-week baseline
  (`src/models/demand_forecasting.py:naive_last_week_baseline`) first,
  measure it with `src/evaluation/forecasting_metrics.py`, and only then
  justify a LightGBM/XGBoost model by how much it beats that baseline.

## Phase B — Travel-time prediction (feasible, more work than demand)

- Build route-leg matching: snap each GPS segment
  (`transformations.build_gps_segments()`) to a specific stop-to-stop leg
  of its route. Only usable for the ~48% of routes with
  `station_opendata` geometry today — the rest need either manual
  geometry entry or a different matching approach (e.g. matching against
  `stations[]` order without coordinates).
- Filter GPS outliers before modeling — the discovery run already found
  an implausible ~530 km/h computed segment from a single bad fix; this
  needs a systematic filter (e.g. max plausible speed, minimum ping
  density), not just eyeballing.
- Baseline: historical mean travel time per leg/hour/day-of-week
  (`src/models/travel_time_prediction.py`) before any learned model.

## Phase C — Vehicle allocation (feasible once Phase A exists)

- Implement `src/optimization/vehicle_optimizer.py` against Phase A's
  demand predictions and the current `fonctionnel` fleet (162 vehicles
  in the discovery snapshot — confirm this is current, since 584/772 are
  marked `active: false`, which is a very retired-looking fleet list to
  plan against without checking with the business first).

## Phase D — Schedule optimization (blocked)

- Cannot start until the missing-schedule question in
  `docs/optimization_problem.md` is resolved with the business.

## Explicitly out of scope for this project (per the brief)

- Driver scheduling/optimization — no data exists (Problem 3 in
  `docs/optimization_problem.md`).
- Anything already covered by the existing separate AI layer (RAG
  chatbot, ETA/delay prediction, trip anomaly detection, ticket-sales
  anomaly detection) — this project reads the same MongoDB server but
  does not duplicate or modify that layer.
