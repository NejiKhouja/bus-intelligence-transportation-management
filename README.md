# Intelligent Route & Schedule Optimization

Foundation and skeleton for BUS Software's transportation demand
analysis, travel-time estimation, route/schedule optimization, and
vehicle allocation project. Separate from BUS Software's existing AI
layer (RAG chatbot, ETA/delay prediction, trip/ticket anomaly
detection) — this project does not modify that layer, it only reads
from the same MongoDB server.

## Status

Database discovery is complete and the extraction pipeline is built and
tested against the live database. No forecasting/optimization models
are trained yet — that was an explicit non-goal until the data was
understood. See `docs/roadmap.md` for what's next and why.

## What was found

The operational data spans **four MongoDB databases** on one server —
not one clean schema, but a real system that grew over ~7.5 years across
~10 regional Tunisian bus operators:

- `winicari` — live operational data: ~772 vehicles, 402 routes, fare
  tables, plus rolling ~1-week windows of live tickets and live GPS.
- `Historique_Tickets` — **~5.5M ticket sales, 2019–2026**, the primary
  demand dataset.
- `Historique_pos` — **1,603 daily GPS-ping collections, 2022–2026**,
  the primary travel-time dataset.
- `OpenData` — geocoded stops, Tunisian administrative geography, and a
  weather/holiday calendar.

Full write-up: `docs/database.md`. Field-level reference:
`docs/data_dictionary.md`.

## What this means for the project

| Component | Status | Why |
|---|---|---|
| Demand forecasting | **Available** | 7.5 years of per-ticket sales with route/stop/timestamp |
| Travel-time prediction | **Partially available** | 4.5 years of GPS pings, but only ~48% of routes have coordinate geometry to match segments to legs |
| Vehicle allocation | **Available** | Vehicle master data + demand data both exist |
| Schedule optimization | **Blocked** | No timetable/schedule collection exists anywhere in the database |
| Driver scheduling | **Not feasible** | No driver availability/shift data exists |

Details and reasoning: `docs/optimization_problem.md`.

## Repository layout

```
config/            Settings (env-driven, no secrets committed)
data/               Local extracted/derived datasets (gitignored, see data/README.md)
notebooks/          Exploration notebooks matching the phases below
src/database/       Read-only MongoDB client, generic explorer, domain queries
src/data/           MongoDB documents -> normalized DataFrames, cleaning, validation
src/features/       Feature engineering (scaffolded)
src/models/         Forecasting models (scaffolded, baselines only)
src/optimization/   OR-Tools-based schedule/vehicle optimization (scaffolded)
src/evaluation/     Metrics for models and optimization outputs
src/api/            Placeholder for exposing results to other services
scripts/            explore_database.py — reusable MongoDB exploration CLI
tests/              pytest suite (some tests need a live MongoDB, auto-skip if unreachable)
docs/               database.md, data_dictionary.md, architecture.md,
                    optimization_problem.md, roadmap.md
```

## Setup

```bash
cp .env.example .env      # edit MONGODB_URI if not localhost
pip install -r requirements.txt
python scripts/explore_database.py ping
```

## Using the exploration tool

```bash
python scripts/explore_database.py list-databases
python scripts/explore_database.py stats --db winicari
python scripts/explore_database.py sample --db winicari --collection ligne -n 2
python scripts/explore_database.py fields --db winicari --collection position --depth 2
python scripts/explore_database.py range --db winicari --collection position --field date
python scripts/explore_database.py daily-span --db Historique_pos
```

## Using the extraction pipeline

```python
from src.data import extraction, transformations, validation

routes = extraction.extract_routes()
vehicles = extraction.extract_vehicles()
tickets_2025 = extraction.extract_archived_tickets(2025)
demand = transformations.aggregate_demand(tickets_2025, freq="D")

gps_day = extraction.extract_archived_gps_day("20260601")
segments = transformations.build_gps_segments(gps_day)

validation.missing_rate(vehicles, ["matricule", "capacity"])
```

All of the above have been run against the live database during
discovery — see `docs/database.md` for the resulting numbers.

## Architecture and strategy

- `docs/architecture.md` — pipeline shape (MongoDB → extraction →
  features → models → optimization) and why it's layered this way.
- `docs/optimization_problem.md` — the schedule and vehicle-allocation
  problems this system is meant to eventually solve, and which of them
  the current data actually supports.
- `docs/roadmap.md` — ordered next steps, including the open questions
  that need a decision from the business before modeling continues.
