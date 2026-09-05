# Intelligent Route & Schedule Optimization

Foundation/skeleton for BUS Software's demand analysis, travel-time
estimation, route/schedule optimization, and vehicle allocation.
Separate from the existing AI layer (RAG chatbot, ETA/delay prediction,
anomaly detection) — reads from the same MongoDB server, never modifies
it or that layer.

## Status

Extraction pipeline, demand-forecasting and travel-time baselines, vehicle
allocation (OR-Tools), and a PHP/JS planning web app are built and tested
against live data — see `docs/system_overview.md` for the full picture:
data choices, quality fixes, model rationale, training/evaluation, and the
optimization layer, end to end. Also reuses the sibling `winicari` repo's
reference DB read-only for company/stop/line identity and GPS trip
reconstruction — see `docs/reference_db_integration.md`.

## Docs

- `docs/system_overview.md` — **start here**: the full story, data to models to optimization
- `docs/database.md` — MongoDB inventory, volumes, relationships, quality findings
- `docs/reference_db_integration.md` — what the sibling repo's reference DB adds and why
- `docs/data_dictionary.md` — field-level reference
- `docs/data_quality_report.md` — measured missing/invalid rates, current run
- `docs/architecture.md` — pipeline shape
- `docs/baseline_results.md` — demand/travel-time model vs. baseline numbers
- `docs/optimization_problem.md` — schedule/vehicle/driver feasibility
- `docs/optimization_results.md` — a real vehicle-allocation run, worked example
- `docs/roadmap.md` — next steps
- `web/README.md` — the planning web app (PHP/HTML/CSS/JS): stack, data flow, AI Insights

## Setup

```bash
cp .env.example .env      # MONGODB_URI, REFERENCE_DB_PATH
pip install -r requirements.txt
python scripts/explore_database.py ping
```

## Layout

```
config/         env-driven settings
data/           extracted/derived datasets (gitignored)
notebooks/      01 database exploration, 02 data quality, 03 features
src/database/   MongoDB + reference-DB read-only clients
src/data/       extraction / cleaning / validation / transformations
src/features/   feature engineering (scaffolded)
src/models/     demand + travel-time baselines (scaffolded)
src/optimization/  OR-Tools schedule/vehicle optimization (scaffolded)
src/evaluation/ metrics
src/api/        placeholder
scripts/        explore_database.py CLI
tests/          pytest (MongoDB-dependent tests auto-skip if unreachable)
docs/           see above
```

## Quick usage

```python
from src.data import extraction, transformations

routes = extraction.extract_routes()
vehicles = extraction.extract_vehicles()
demand = transformations.aggregate_demand(extraction.extract_archived_tickets(2025), freq="D")

trips = extraction.extract_trips()               # from the reference DB
schedule = transformations.derive_empirical_schedule(trips)
legs = transformations.travel_times_from_trip_stops(extraction.extract_trip_stops())
```

```bash
python scripts/explore_database.py stats --db winicari
python scripts/explore_database.py sample --db winicari --collection ligne -n 2
```
