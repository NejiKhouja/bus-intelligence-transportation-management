"""Vehicle allocation: given a fixed number of operational vehicles per
company and predicted daily demand per route, decide how many vehicles
each route gets to minimize unmet demand.

Vehicles within a company are treated as fungible (assign a *count* per
route, not specific vehicle IDs) — reasonable here since capacity barely
varies within a company (see docs/optimization_problem.md, Problem 2).
Solved as a small MILP with OR-Tools CP-SAT: integer vehicle counts,
continuous shortfall, exact for this size (dozens of routes, a handful
of companies).
"""

from __future__ import annotations

import pandas as pd
from ortools.sat.python import cp_model

# Demand and capacity are reported in whole passengers; CP-SAT needs
# integers, so continuous inputs are rounded to this many passengers of
# resolution rather than scaled — the demand/capacity numbers here are
# already whole-ish (ticket counts, seat counts), so this only matters
# for interpolated capacity means.
_SCALE = 1


def allocate_vehicles(route_demand: pd.DataFrame, fleet: pd.DataFrame) -> pd.DataFrame:
    """route_demand: route_id, societe, predicted_demand (one row/route).
    fleet: societe, available_vehicles, avg_capacity (one row/company).

    Returns route_demand with assigned_vehicles, capacity_provided,
    shortfall, coverage_ratio added. Companies/routes not present in
    `fleet` are left unassigned (assigned_vehicles=0) rather than
    dropped, so gaps are visible instead of silently disappearing.
    """
    model = cp_model.CpModel()

    fleet = fleet.set_index("societe")
    routes = route_demand.reset_index(drop=True)

    max_vehicles_per_route = int(fleet["available_vehicles"].max()) if len(fleet) else 0
    assign_vars = {}
    shortfall_vars = {}

    for i, row in routes.iterrows():
        societe = row["societe"]
        demand = int(round(row["predicted_demand"]))
        upper = max_vehicles_per_route if societe in fleet.index else 0
        x = model.NewIntVar(0, upper, f"x_{i}")
        capacity = int(round(fleet.loc[societe, "avg_capacity"])) if societe in fleet.index else 0
        shortfall = model.NewIntVar(0, demand, f"shortfall_{i}")
        model.Add(shortfall >= demand - x * capacity)
        assign_vars[i] = x
        shortfall_vars[i] = shortfall

    for societe, avail in fleet["available_vehicles"].items():
        route_idxs = routes.index[routes["societe"] == societe]
        if len(route_idxs):
            model.Add(sum(assign_vars[i] for i in route_idxs) <= int(avail))

    model.Minimize(sum(shortfall_vars.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"solver did not find a feasible solution: status={solver.StatusName(status)}")

    out = routes.copy()
    out["assigned_vehicles"] = [solver.Value(assign_vars[i]) for i in routes.index]
    out["capacity_provided"] = out.apply(
        lambda r: r["assigned_vehicles"] * (fleet.loc[r["societe"], "avg_capacity"] if r["societe"] in fleet.index else 0),
        axis=1,
    )
    out["shortfall"] = (out["predicted_demand"] - out["capacity_provided"]).clip(lower=0)
    out["coverage_ratio"] = (out["capacity_provided"] / out["predicted_demand"]).clip(upper=1.0)
    out.attrs["solver_status"] = solver.StatusName(status)
    out.attrs["objective_total_shortfall"] = solver.ObjectiveValue()
    return out
