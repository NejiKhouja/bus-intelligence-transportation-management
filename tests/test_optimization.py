"""Unit tests for the vehicle allocation optimizer — synthetic inputs,
no MongoDB/reference-DB required.
"""

import pandas as pd

from src.optimization.vehicle_optimizer import allocate_vehicles


def test_allocate_vehicles_fully_covers_when_capacity_sufficient():
    route_demand = pd.DataFrame({
        "route_id": ["1"], "societe": ["ACME"], "predicted_demand": [100.0],
    })
    fleet = pd.DataFrame({
        "societe": ["ACME"], "available_vehicles": [5], "avg_capacity": [54.0],
    })
    result = allocate_vehicles(route_demand, fleet)
    row = result.iloc[0]
    assert row["shortfall"] == 0
    assert row["assigned_vehicles"] * 54.0 >= row["predicted_demand"]
    # shouldn't over-allocate beyond what's needed to cover demand
    assert row["assigned_vehicles"] <= 3


def test_allocate_vehicles_reports_shortfall_when_capacity_insufficient():
    route_demand = pd.DataFrame({
        "route_id": ["1"], "societe": ["ACME"], "predicted_demand": [1000.0],
    })
    fleet = pd.DataFrame({
        "societe": ["ACME"], "available_vehicles": [2], "avg_capacity": [54.0],
    })
    result = allocate_vehicles(route_demand, fleet)
    row = result.iloc[0]
    assert row["assigned_vehicles"] == 2  # uses everything available
    assert row["shortfall"] == 1000.0 - 2 * 54.0
    assert row["shortfall"] > 0


def test_allocate_vehicles_leaves_uncovered_company_at_zero():
    # A route whose company has no operational vehicles at all — must
    # not silently borrow capacity from another company.
    route_demand = pd.DataFrame({
        "route_id": ["1"], "societe": ["GHOST_CO"], "predicted_demand": [50.0],
    })
    fleet = pd.DataFrame({
        "societe": ["ACME"], "available_vehicles": [10], "avg_capacity": [54.0],
    })
    result = allocate_vehicles(route_demand, fleet)
    row = result.iloc[0]
    assert row["assigned_vehicles"] == 0
    assert row["shortfall"] == 50.0


def test_allocate_vehicles_respects_company_fleet_cap_across_routes():
    route_demand = pd.DataFrame({
        "route_id": ["1", "2"], "societe": ["ACME", "ACME"], "predicted_demand": [500.0, 500.0],
    })
    fleet = pd.DataFrame({
        "societe": ["ACME"], "available_vehicles": [3], "avg_capacity": [54.0],
    })
    result = allocate_vehicles(route_demand, fleet)
    assert result["assigned_vehicles"].sum() <= 3
