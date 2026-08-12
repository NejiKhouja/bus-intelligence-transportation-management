# Architecture

Separate from BUS Software's existing AI layer (RAG chatbot, ETA/delay
prediction, anomaly detection) — reads the same MongoDB, read-only, and
the sibling `winicari` repo's reference DB, also read-only (see
`reference_db_integration.md`). Never writes back to either.

## Pipeline

```
MongoDB + reference DB
      v
src/data/extraction.py        raw -> normalized DataFrames
      v
cleaning.py / validation.py / transformations.py
      v
src/features/                 calendar, lag, time-of-day features
      v
src/models/                   naive baseline -> LightGBM/XGBoost
      v
src/optimization/             OR-Tools: schedule + vehicle allocation
      v
Recommended schedule / vehicle allocation
```

ML predicts the environment (demand, leg travel time); optimization
decides under constraints (capacity, depot). Kept separate — see
`optimization_problem.md`.

## Why

- `src/database/explorer.py` is generic (any collection); `queries.py`
  holds this project's assumptions about which collections matter.
- `extraction.py` is the only place touching raw document shapes —
  everything downstream is stable-column DataFrames, so a schema drift
  (e.g. `winicari.ticket` vs `Historique_Tickets` field names, see
  `data_dictionary.md`) is a one-function fix.
- `validation.py` is a reusable library, not a one-off audit script, so
  the same checks catch regressions on every future extraction.

## Status

| Layer | Status |
|---|---|
| `src/database/` | Implemented, tested against live MongoDB + reference DB |
| `src/data/*` | Implemented, tested (routes, vehicles, GPS, tickets, trips, trip_stops) |
| `src/features/` | Scaffolded — blocked on weather-join coverage + route-leg matching |
| `src/models/` | Scaffolded — baselines only, no learned model |
| `src/optimization/` | Scaffolded — pending model outputs |
| `src/api/` | Placeholder |
