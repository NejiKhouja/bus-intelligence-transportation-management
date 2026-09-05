#!/usr/bin/env python
"""Runs the real OR-Tools optimizer on demand, for an arbitrary fleet
size — invoked by web/public/optimize.php via subprocess so the "what
if you had N buses" control in the web app triggers a genuine solve,
not a lookup into a precomputed table (the 3 fixed scenarios are
precomputed; this is for anything else the user asks for).

Input (stdin, JSON): {"company": "S.R.T.K", "vehicles": 45}
Output (stdout, JSON): {summary: {...}, routes: [...]}
On error: {"error": "..."} on stdout, exit code 1 — never a raw traceback,
since PHP is parsing this as JSON.

Run: echo '{"company":"S.R.T.K","vehicles":45}' | python scripts/live_allocate.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Windows' console defaults to cp1252, which can't encode Arabic route
# names — printing them without this crashes the script (and PHP would
# see an empty stdout + non-zero exit, not the JSON it's expecting).
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.optimization.vehicle_optimizer import allocate_vehicles  # noqa: E402

DATA_PATH = Path(__file__).resolve().parents[1] / "web" / "data" / "fleet_data.json"
MAX_VEHICLES = 500


def main():
    try:
        req = json.loads(sys.stdin.read())
        company = str(req["company"])
        vehicles = int(req["vehicles"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        print(json.dumps({"error": "Invalid request."}))
        sys.exit(1)

    if not (0 <= vehicles <= MAX_VEHICLES):
        print(json.dumps({"error": f"vehicles must be between 0 and {MAX_VEHICLES}."}))
        sys.exit(1)

    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        company_data = data["companies"][company]
    except (FileNotFoundError, KeyError):
        print(json.dumps({"error": "Unknown company or data unavailable."}))
        sys.exit(1)

    route_demand = pd.DataFrame(company_data["route_demand"])
    if route_demand.empty:
        print(json.dumps({"summary": {"available_vehicles": vehicles, "avg_capacity": company_data["avg_capacity"],
                                       "total_demand": 0, "total_covered": 0, "coverage_pct": 0, "total_shortfall": 0},
                           "routes": []}))
        return

    route_demand["societe"] = company
    fleet_row = pd.DataFrame({
        "societe": [company],
        "available_vehicles": [vehicles],
        "avg_capacity": [company_data["avg_capacity"]],
    })

    result = allocate_vehicles(route_demand[["route_id", "societe", "predicted_demand"]], fleet_row)
    result = result.merge(
        route_demand[["route_id", "origin", "destination", "origin_ar", "destination_ar", "demand_source"]],
        on="route_id", how="left",
    )

    total_demand = float(result["predicted_demand"].sum())
    total_covered = float(result["capacity_provided"].sum())

    output = {
        "summary": {
            "available_vehicles": vehicles,
            "avg_capacity": company_data["avg_capacity"],
            "total_demand": round(total_demand, 1),
            "total_covered": round(total_covered, 1),
            "coverage_pct": round(100 * total_covered / total_demand, 1) if total_demand else 0.0,
            "total_shortfall": round(float(result["shortfall"].sum()), 1),
        },
        "routes": [
            {
                "route_id": r["route_id"],
                "origin": r["origin"],
                "destination": r["destination"],
                "origin_ar": r["origin_ar"],
                "destination_ar": r["destination_ar"],
                "predicted_demand": round(r["predicted_demand"], 1),
                "demand_source": r["demand_source"],
                "assigned_vehicles": int(r["assigned_vehicles"]),
                "capacity_provided": round(r["capacity_provided"], 1),
                "shortfall": round(r["shortfall"], 1),
                "coverage_ratio": round(r["coverage_ratio"], 3),
            }
            for _, r in result.sort_values("predicted_demand", ascending=False).iterrows()
        ],
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
