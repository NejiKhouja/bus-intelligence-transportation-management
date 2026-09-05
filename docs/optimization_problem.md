# Optimization Problem

Intended shape, not built yet — `src/optimization/` is scaffolding.

## Why optimization, not a bigger model

Scheduling/allocation are combinatorial decisions under hard constraints
(a vehicle can't be in two places, capacity is a hard cap). ML predicts
the uncertain stuff (demand, travel time); OR-Tools (CP-SAT for
scheduling, linear_solver for allocation) makes the constrained
decision. Keeping these separate rather than folding into one model.

## Problem 1: Schedule optimization (headway/departure times)

Given per route/time-bucket: predicted demand, predicted leg travel
time, vehicle capacity. Decide departure times/headway. Objective
(draft): minimize unmet demand + schedule-deviation cost +
vehicle-hours. Constraints (draft): min/max headway, vehicles available
per depot.

No published timetable exists, but the reference DB reconstructs 47,567
real trips with matched per-stop timing. `derive_empirical_schedule()`
turns that into a per (line, direction, day-of-week, time-bucket)
trip-frequency table — an inferred schedule grounded in what the fleet
actually runs. Only as good as the 54% of lines with resolved stop
geometry, and it's a frequency table, not exact clock times. A real
published timetable would validate/correct this, not replace it.

## Problem 2: Vehicle allocation

Given: predicted demand per route, vehicle status, depot assignment.
Decide which vehicles serve which routes. Objective (draft): maximize
coverage for a given fleet size, or minimize fleet size for a coverage
target. Constraints (draft): one route at a time, capacity ≥ predicted
demand, vehicle currently operational.

`winicari.bus.fonctionnel` is a bad signal for "operational" — confirmed,
not just suspected: of the 162 vehicles marked `fonctionnel=True`, 125
(77%) show no recent activity under an evidence-based check.
`transformations.derive_fleet_operational_status()` replaces it,
combining GPS trip activity (69 vehicles) with a ticket-sales fallback
across all 8 years of `Historique_Tickets` (157 more), both recency
relative to the data's own latest date, not the system clock.

Bigger finding: 536 of 772 vehicles (70%) show **zero** activity in
either signal, ever. That's not a coverage gap in this analysis — it's
evidence that most of `winicari.bus` isn't a current fleet list. Vehicle
allocation should plan against the ~226 vehicles with a real activity
signal (or whatever subset the business confirms is current), not the
full 772-row table. See roadmap.

## Problem 3: Driver scheduling — not feasible

No driver availability data exists. `NamesConv` is name/phone only. The
reference DB's `driver_services` (35,866 rows) is closer — observed
service windows from ticket timestamps — but that's when a device was
selling tickets, not when a driver was actually available, and it has
its own quality problems (negative and multi-day "shifts"). Useful
descriptively (typical shift length/start time), not as a scheduling
constraint. Needs real availability data collected before this is
buildable.
