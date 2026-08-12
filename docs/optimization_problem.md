# Optimization Problem — Initial Formulation

This describes the intended problem shape, not a finished implementation
— `src/optimization/` is currently scaffolding only (see
`docs/architecture.md`). Written now so the objective/constraints
modules have a target to fill in once demand and travel-time predictions
exist.

## Why optimization, not a bigger neural network

Scheduling and allocation are combinatorial decisions under hard
constraints (a vehicle can't be in two places, capacity is a hard cap,
a depot has a fixed number of vehicles). ML is good at predicting
uncertain quantities (demand, travel time); it is a poor fit for
enforcing hard constraints or guaranteeing feasibility. The standard
and more explainable approach — and the one this project defaults to —
is: predict the environment with ML, then solve the decision problem
with constraint programming / MILP. Google OR-Tools is the intended
solver (CP-SAT for scheduling, linear_solver for allocation), per the
brief.

## Problem 1: Schedule optimization (headway / departure times)

**Given**, per route and time-of-day bucket:
- Predicted passenger demand (`src/models/demand_forecasting.py`)
- Predicted travel time per leg (`src/models/travel_time_prediction.py`)
- Vehicle capacity (`winicari.bus.nbrPlace`)

**Decide:** departure times / headway for each route.

**Objective (draft):** minimize a weighted sum of (a) predicted unmet
demand (passengers left waiting beyond capacity), (b) deviation from the
current schedule (operational disruption cost), (c) vehicle-hours used.

**Constraints (draft):** minimum/maximum headway, vehicle count
available per operator/depot, route travel time from predictions.

**Blocked on:** no ground-truth schedule/timetable exists in the
database to optimize against or validate deviation from (see
`docs/database.md` — "No dedicated schedule/timetable collection
exists"). The `horaires` array on a minority of `winicari.station`
documents is not sufficient. This needs either (a) the business
supplying the current published timetables outside MongoDB, or (b)
inferring an implicit current schedule from GPS departure-time patterns
in `Historique_pos`, which is a real but nontrivial project on its own.

## Problem 2: Vehicle allocation

**Given:** predicted demand per route, current vehicle
`active`/`fonctionnel` status, current operator/depot (`centre`)
assignment.

**Decide:** which of the ~772 vehicles serve which routes.

**Objective (draft):** maximize demand coverage subject to fleet size,
or minimize fleet size subject to a coverage target — the business
needs to pick which framing matches their actual planning question.

**Constraints (draft):** a vehicle can only be assigned to one route at
a time; capacity ≥ predicted demand (or an accepted overflow rate);
`fonctionnel: true` only (only 162/772 vehicles are currently marked
operational — the rest of the fleet snapshot is not actually assignable
today).

**Feasible today** for a first pass, since vehicle master data and
route-level demand both exist — see `docs/roadmap.md` for sequencing.

## Problem 3: Driver scheduling — NOT FEASIBLE with current data

No driver availability, shift, or working-hours data exists anywhere in
the database (`NamesConv` is a name/phone lookup only — see
`docs/database.md`, section G). This cannot be built without new data
being collected or supplied. Do not attempt to infer shifts from GPS/
ticket activity as a substitute without explicit sign-off — that would
be modeling a symptom (when a device happened to be active) as if it
were the underlying constraint (when a driver is contractually
available), which risks recommending schedules no driver can legally
staff.
