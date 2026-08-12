# Architecture

## Scope boundary

This project is separate from BUS Software's existing AI layer (RAG
chatbot, ETA/delay prediction, trip anomaly detection, ticket-sales
anomaly detection). It does not modify that layer. It reads from the
same MongoDB server, read-only, and produces its own local artifacts
(`data/`) and its own models/optimizers (`src/models/`,
`src/optimization/`). If results ever need to be surfaced to another
service, that happens through `src/api/app.py`, not by writing back into
the operational collections.

## Pipeline shape

```
MongoDB (winicari, Historique_Tickets, Historique_pos, OpenData)
      |  src/database/  (read-only client + generic explorer + domain queries)
      v
src/data/extraction.py        raw documents -> normalized DataFrames
      |
      v
src/data/cleaning.py          date parsing, lat/lon order fix, name normalization
src/data/validation.py        missing/invalid/duplicate metrics -> docs/database.md audit
src/data/transformations.py   ticket-level -> demand-by-bucket; GPS pings -> travel-time segments
      |
      v
src/features/                 calendar features, lag features, time-of-day features
      |
      v
src/models/                   naive baseline -> LightGBM/XGBoost (demand, travel time)
      |
      v
src/optimization/             OR-Tools: schedule + vehicle allocation, constrained by predictions
      |
      v
Recommended schedule / vehicle allocation
```

ML predicts the operating environment (how many passengers, how long a
leg takes). Optimization decides what to do about it under constraints
(vehicle capacity, depot assignment). The two are not merged into a
single model — see `docs/optimization_problem.md` for why.

## Why this layering

- **`src/database/` is generic** (`explorer.py`) plus **domain-specific**
  (`queries.py`) on purpose: `explorer.py` has no knowledge of "routes"
  or "tickets" and is reusable for any future collection; `queries.py`
  is where this project's assumptions about which collections matter
  live, so they're easy to find and revise.
- **`extraction.py` is the only place that touches raw MongoDB document
  shapes.** Everything downstream works on flat DataFrames with stable
  column names, so a future schema change in `winicari.ticket` (which
  has already diverged from `Historique_Tickets.Ticket<year>` once, see
  `data_dictionary.md`) only requires editing one function.
- **Validation is a library, not a one-off script**, so the same checks
  used for the initial audit (`docs/database.md`) can be re-run on every
  future extraction to catch regressions (e.g. a device firmware update
  that starts sending swapped lat/lon again).

## What's implemented vs. scaffolded

| Layer | Status |
|---|---|
| `src/database/` | Implemented and tested against the live database |
| `src/data/extraction.py`, `cleaning.py`, `validation.py`, `transformations.py` | Implemented and tested against the live database (routes, vehicles, companies, OpenData stops, one day of GPS, one year of tickets) |
| `src/features/` | Scaffolded — calendar/lag/time-of-day helpers exist, but the weather-join and route-leg-matching work they depend on is not done (see `docs/roadmap.md`) |
| `src/models/` | Scaffolded — baseline functions only (naive lag, historical mean), no learned model yet |
| `src/optimization/` | Scaffolded — module boundaries and docstrings only, pending model outputs to optimize against |
| `src/api/` | Placeholder — no consumer specified yet |

This matches the brief: build the foundation and prove the data supports
it, don't train models before the data is understood.
