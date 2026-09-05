#!/usr/bin/env python
"""Builds the real-data JSON payload for the fleet-ops demo artifact:
per-company vehicle rosters (for the 3D depot view) and 3 real fleet-size
scenarios per company, each solved with the actual OR-Tools optimizer.

Scenarios (grounded in fleet_status.parquet, not invented):
- active:  vehicles with is_recently_active == True (real activity, last 30d)
- signal:  active + any vehicle with activity_source in (gps_trip, ticket_sales)
           ever (i.e. any confirmed activity, not just recent)
- roster:  every vehicle in winicari.bus for that company (the naive
           "trust the fleet table" assumption)

Run: python scripts/build_demo_payload.py
Writes: data/processed/demo_payload.json
"""

import json
import sys
from pathlib import Path

import pandas as pd
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings  # noqa: E402
from src.data.extraction import extract_companies  # noqa: E402
from src.optimization.vehicle_optimizer import allocate_vehicles  # noqa: E402
from predict_next_day_demand import predict_next_day  # noqa: E402

INVESTMENT_MULTIPLIER = 2  # the "what if you doubled your tracking devices" scenario


def device_counts_by_company() -> dict[str, int]:
    """winicari.appareil — one document per physical GPS/ticketing unit
    (the hardware BUS Software provides operators). This is the real
    hard cap on how many buses a company can track/schedule with
    confidence at once — a much more direct explanation for a small
    "confirmed active" fleet than assuming buses are retired. Verified:
    S.T.S has exactly 5 devices and exactly 5 "active" vehicles — not a
    coincidence, that scenario's fleet size is capped by device supply,
    not by how many of their 370 registered buses still run.
    """
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    db = client["winicari"]
    counts = {}
    for doc in db.appareil.aggregate([{"$group": {"_id": "$societe.Nom", "count": {"$sum": 1}}}]):
        counts[doc["_id"]] = doc["count"]
    return counts

COMPANIES = ["S.R.T.K", "S.R.T.SELIANA", "S.T.S", "SRT.ELGOUAFEL"]
RECENT_DAYS = 30
# A route must have sold at least one ticket within this many days of the
# dataset's real latest date to be treated as currently operating. Close
# to the 30-day window used for vehicle "active" status elsewhere, with a
# little slack since ticket reporting can be less frequent than GPS pings.
FRESHNESS_DAYS = 45
OUT_PATH = Path(settings.data_processed_dir) / "demo_payload.json"

# Confirmed sentinel/placeholder vehicle codes, not real vehicles — reused
# across multiple unrelated companies (impossible for a real plate/vehicle),
# or an explicit non-bus record. "0"/GUICHET is the office ticket counter
# (matricule literally means "counter" in French); it shows up as
# is_recently_active=True in fleet_status because counter sales happen
# constantly — would silently render as an "operational bus" if not
# excluded. Verified against vehicles.parquet before excluding.
SENTINEL_VEHICLE_IDS = {"0", "9999", "1111", "11111", "111"}


def vehicle_status(row) -> str:
    if row["is_recently_active"] == True:  # noqa: E712
        return "active"
    if row["activity_source"] in ("gps_trip", "ticket_sales"):
        return "signal"
    return "none"


def main():
    data_dir = Path(settings.data_processed_dir)
    vehicles = pd.read_parquet(data_dir / "vehicles.parquet")
    vehicles["vehicle_id"] = vehicles["vehicle_id"].astype(str)
    n_before = len(vehicles)
    vehicles = vehicles[~vehicles["vehicle_id"].isin(SENTINEL_VEHICLE_IDS)]
    print(f"excluded {n_before - len(vehicles)} sentinel/placeholder vehicle records "
          f"({sorted(SENTINEL_VEHICLE_IDS)})")
    fleet_status = pd.read_parquet(data_dir / "fleet_status.parquet")
    routes = pd.read_parquet(data_dir / "routes.parquet")
    demand = pd.read_parquet(data_dir / "demand_daily.parquet")

    # Real model forecast where the trained model actually covers a route
    # (33 routes with >=200 days of history — see predict_next_day_demand.py);
    # every other route keeps the honest recent-30-day average instead of a
    # prediction from a model that never saw it during training.
    model_predictions = predict_next_day(demand).set_index("route_id")["predicted_demand"].to_dict()
    print(f"model-based forecast available for {len(model_predictions)} routes")

    fs = fleet_status.merge(vehicles[["societe", "vehicle_id", "matricule", "capacity"]],
                             on=["societe", "vehicle_id"], how="right")
    fs["activity_source"] = fs["activity_source"].fillna("none")
    fs["is_recently_active"] = fs["is_recently_active"].apply(lambda v: v is True)
    fs["status"] = fs.apply(vehicle_status, axis=1)
    fs["capacity"] = fs["capacity"].fillna(54.0)

    r_societe = routes[["route_id", "societe", "origin_fr", "destination_fr", "origin_ar", "destination_ar"]].drop_duplicates("route_id")
    d = demand.merge(r_societe, on="route_id", how="left")

    # Real, serious bug caught before shipping further: the old cutoff was
    # anchored to EACH ROUTE's own last-seen date, not the dataset's real
    # end date — so a route whose last ticket sale was 831 days ago still
    # got a "recent 30-day average" computed from whatever few days
    # existed near ITS OWN stale cutoff, presented as if it reflected
    # today's demand. Checked broadly, not just the one route that
    # surfaced it: 60 of 106 routes (57%) across all 4 companies hadn't
    # reported in over 14 days as of the snapshot's real end date; S.T.S
    # specifically had only 6-7 of 38 routes genuinely current at any
    # reasonable threshold. Fixed two ways: (1) the averaging window is
    # now anchored to the dataset's actual latest date for every route,
    # not each route's own; (2) routes that haven't reported within
    # FRESHNESS_DAYS of that real end date are excluded from demand/
    # allocation entirely and instead surfaced as a "stale routes" list
    # for the insights feature — visible, not silently smoothed over.
    overall_max = demand["time_bucket"].max()
    route_last_seen = demand.groupby("route_id")["time_bucket"].max()
    fresh_route_ids = set(route_last_seen[route_last_seen >= overall_max - pd.Timedelta(days=FRESHNESS_DAYS)].index)

    stale_routes_df = route_last_seen[~route_last_seen.index.isin(fresh_route_ids)].reset_index()
    stale_routes_df.columns = ["route_id", "last_seen"]
    stale_routes_df["days_stale"] = (overall_max - stale_routes_df["last_seen"]).dt.days
    stale_routes_df = stale_routes_df.merge(r_societe, on="route_id", how="left")

    d = d[d["route_id"].isin(fresh_route_ids)]
    cutoff = overall_max - pd.Timedelta(days=RECENT_DAYS)
    recent = d[d["time_bucket"] > cutoff]

    companies_meta = extract_companies().set_index("societe")

    payload = {"generated_from": "data/processed/*.parquet (real, computed pipeline output)", "companies": {}}

    for company in COMPANIES:
        co_vehicles = fs[fs["societe"] == company].copy()
        # Group on (route_id, societe) only, not the display-name columns —
        # groupby() silently drops any row whose group key is NaN, and 8/402
        # routes have a null name (French or Arabic). Names are merged back
        # afterward on route_id so a missing name never loses demand data.
        co_route_demand = (
            recent[recent["societe"] == company]
            .groupby(["route_id", "societe"])["passenger_count"]
            .mean()
            .reset_index()
            .rename(columns={"passenger_count": "predicted_demand"})
        )
        co_route_demand = co_route_demand[co_route_demand["predicted_demand"] > 0]
        co_route_demand = co_route_demand.merge(
            r_societe[["route_id", "origin_fr", "destination_fr", "origin_ar", "destination_ar"]],
            on="route_id", how="left",
        )
        # Swap in the real model forecast wherever it covers this route;
        # everywhere else, keep the recent-30-day average. demand_source
        # is carried through to the payload so the UI can show which is which.
        co_route_demand["demand_source"] = co_route_demand["route_id"].map(
            lambda r: "model" if r in model_predictions else "average"
        )
        co_route_demand["predicted_demand"] = co_route_demand.apply(
            lambda r: model_predictions.get(r["route_id"], r["predicted_demand"]), axis=1
        )

        scenarios = {}
        subsets = {
            "active": co_vehicles[co_vehicles["status"] == "active"],
            "signal": co_vehicles[co_vehicles["status"].isin(["active", "signal"])],
            "roster": co_vehicles,
        }
        for name, subset in subsets.items():
            if len(subset) == 0 or len(co_route_demand) == 0:
                scenarios[name] = {
                    "available_vehicles": 0, "avg_capacity": 54.0,
                    "total_demand": float(co_route_demand["predicted_demand"].sum()) if len(co_route_demand) else 0,
                    "total_covered": 0.0, "coverage_pct": 0.0, "total_shortfall": 0.0,
                    "routes": [],
                }
                continue
            fleet_row = pd.DataFrame({
                "societe": [company],
                "available_vehicles": [len(subset)],
                "avg_capacity": [float(subset["capacity"].mean())],
            })
            result = allocate_vehicles(co_route_demand[["route_id", "societe", "predicted_demand"]], fleet_row)
            result = result.merge(
                co_route_demand[["route_id", "origin_fr", "destination_fr", "origin_ar", "destination_ar", "demand_source"]],
                on="route_id", how="left",
            )
            total_demand = float(result["predicted_demand"].sum())
            total_covered = float(result["capacity_provided"].sum())
            scenarios[name] = {
                "available_vehicles": int(len(subset)),
                "avg_capacity": round(float(subset["capacity"].mean()), 1),
                "total_demand": round(total_demand, 1),
                "total_covered": round(total_covered, 1),
                "coverage_pct": round(100 * total_covered / total_demand, 1) if total_demand else 0.0,
                "total_shortfall": round(float(result["shortfall"].sum()), 1),
                "routes": [
                    {
                        "route_id": r["route_id"],
                        "origin": r["origin_fr"] or "?",
                        "destination": r["destination_fr"] or "?",
                        "origin_ar": r["origin_ar"] or r["origin_fr"] or "?",
                        "destination_ar": r["destination_ar"] or r["destination_fr"] or "?",
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

        meta = companies_meta.loc[company] if company in companies_meta.index else None
        payload["companies"][company] = {
            "full_name": (meta["full_name"] if meta is not None and pd.notna(meta["full_name"]) else company),
            "full_name_ar": (meta["full_name_ar"] if meta is not None and pd.notna(meta["full_name_ar"]) else company),
            "vehicles": [
                {
                    "vehicle_id": v["vehicle_id"],
                    "matricule": v["matricule"] if pd.notna(v["matricule"]) and v["matricule"] else None,
                    "capacity": int(v["capacity"]),
                    "status": v["status"],
                    "last_activity": v["last_activity_date"].strftime("%Y-%m-%d") if pd.notna(v.get("last_activity_date")) else None,
                }
                for _, v in co_vehicles.sort_values("vehicle_id").iterrows()
            ],
            "roster_size": int(len(co_vehicles)),
            "avg_capacity": round(float(co_vehicles["capacity"].mean()), 1) if len(co_vehicles) else 54.0,
            # Scenario-independent demand, for the live "what-if N buses"
            # optimizer (web/public/optimize.php) — predicted_demand per
            # route doesn't change with fleet size, only the allocation does.
            "route_demand": [
                {
                    "route_id": r["route_id"],
                    "origin": r["origin_fr"] or "?",
                    "destination": r["destination_fr"] or "?",
                    "origin_ar": r["origin_ar"] or r["origin_fr"] or "?",
                    "destination_ar": r["destination_ar"] or r["destination_fr"] or "?",
                    "predicted_demand": round(r["predicted_demand"], 1),
                    "demand_source": r["demand_source"],
                }
                for _, r in co_route_demand.sort_values("predicted_demand", ascending=False).iterrows()
            ],
            "scenarios": scenarios,
        }
        print(f"{company}: roster={len(co_vehicles)}, routes={len(co_route_demand)}, "
              f"active={len(subsets['active'])}, signal={len(subsets['signal'])}")

    # Cross-company summary for the "what this shows / recommendations"
    # section — computed once here (not per-selection), so it reads the
    # same regardless of which company is currently picked in the UI.
    device_counts = device_counts_by_company()
    overview_rows = []
    for company in COMPANIES:
        co = payload["companies"][company]
        none_count = sum(1 for v in co["vehicles"] if v["status"] == "none")
        active = co["scenarios"]["active"]
        model_routes = sum(1 for r in co["route_demand"] if r["demand_source"] == "model")
        n_devices = device_counts.get(company, 0)
        # Devices only clearly explain a small active fleet when
        # device_count and active_vehicles are close to each other (using
        # nearly all of what they have) — NOT merely "active <= devices",
        # which SRT.ELGOUAFEL would also satisfy (29 devices, 9 active)
        # despite that being the opposite story: they have plenty of spare
        # device capacity already, so devices are clearly not what's
        # holding them back. Checked ratio, not assumed: S.T.S is an exact
        # match (5 devices, 5 active, ratio 1.0) — devices are visibly the
        # binding constraint there. S.R.T.K's active fleet (39) far
        # exceeds its registered devices (14 — likely rotated across more
        # buses over a month, or the registry is incomplete); flagged as
        # device_story so the UI doesn't force the same "buy more
        # devices" pitch on every company regardless of what the numbers
        # actually show for it.
        device_ratio = (n_devices / active["available_vehicles"]) if active["available_vehicles"] else 0
        device_story = "device_limited" if 0.7 <= device_ratio <= 1.3 else "not_device_limited"

        # Real optimizer run at a realistic bigger fleet size — never
        # proposed below what's already observed (would misleadingly look
        # like coverage "drops" from buying hardware) and never above the
        # whole registered roster (there's nowhere to put more devices
        # than there are buses).
        route_demand_df = pd.DataFrame(co["route_demand"])
        investment_fleet_size = max(n_devices * INVESTMENT_MULTIPLIER, active["available_vehicles"])
        investment_fleet_size = min(investment_fleet_size, co["roster_size"]) if co["roster_size"] else investment_fleet_size
        investment_coverage_pct = active["coverage_pct"]
        if investment_fleet_size > 0 and not route_demand_df.empty:
            route_demand_df["societe"] = company
            fleet_investment = pd.DataFrame({
                "societe": [company],
                "available_vehicles": [investment_fleet_size],
                "avg_capacity": [co["avg_capacity"]],
            })
            result_inv = allocate_vehicles(route_demand_df[["route_id", "societe", "predicted_demand"]], fleet_investment)
            total_demand_inv = float(result_inv["predicted_demand"].sum())
            total_covered_inv = float(result_inv["capacity_provided"].sum())
            investment_coverage_pct = round(100 * total_covered_inv / total_demand_inv, 1) if total_demand_inv else 0.0

        overview_rows.append({
            "company": company,
            "roster_size": co["roster_size"],
            "unconfirmed_count": none_count,
            "unconfirmed_pct": round(100 * none_count / co["roster_size"], 1) if co["roster_size"] else 0.0,
            "active_vehicles": active["available_vehicles"],
            "active_coverage_pct": active["coverage_pct"],
            "model_routes": model_routes,
            "total_routes": len(co["route_demand"]),
            "device_count": n_devices,
            "device_story": device_story,
            "investment_devices": investment_fleet_size,
            "investment_coverage_pct": investment_coverage_pct,
        })
    payload["fleet_overview"] = sorted(overview_rows, key=lambda r: -r["unconfirmed_pct"])

    for company in COMPANIES:
        co_stale = stale_routes_df[stale_routes_df["societe"] == company].sort_values("days_stale", ascending=False)
        payload["companies"][company]["stale_routes"] = [
            {
                "route_id": r["route_id"],
                "origin": r["origin_fr"] or "?",
                "destination": r["destination_fr"] or "?",
                "last_seen": r["last_seen"].strftime("%Y-%m-%d"),
                "days_stale": int(r["days_stale"]),
            }
            for _, r in co_stale.iterrows()
        ]
        print(f"{company}: {len(co_stale)} stale routes (no ticket sale in >{FRESHNESS_DAYS}d)")

    # --- AI Insights: real statistical signals, computed the same
    # freshness-safe way as everything above (anchored to the dataset's
    # actual latest date, not each route's own) ---
    TREND_RECENT_DAYS, TREND_PRIOR_DAYS, TREND_THRESHOLD_PCT = 7, 23, 25
    trend_cutoff_recent = overall_max - pd.Timedelta(days=TREND_RECENT_DAYS)
    trend_cutoff_prior = overall_max - pd.Timedelta(days=TREND_RECENT_DAYS + TREND_PRIOR_DAYS)
    trend_rows = []
    for route_id, g in d.groupby("route_id"):
        recent_avg = g[g["time_bucket"] > trend_cutoff_recent]["passenger_count"].mean()
        prior_avg = g[(g["time_bucket"] > trend_cutoff_prior) & (g["time_bucket"] <= trend_cutoff_recent)]["passenger_count"].mean()
        if pd.isna(recent_avg) or pd.isna(prior_avg) or prior_avg < 5:
            continue  # too little data on either side, or too small a base, to trust a % change
        change_pct = (recent_avg - prior_avg) / prior_avg * 100
        if abs(change_pct) >= TREND_THRESHOLD_PCT:
            trend_rows.append({
                "route_id": route_id, "societe": g["societe"].iloc[0],
                "origin": g["origin_fr"].iloc[0] or "?", "destination": g["destination_fr"].iloc[0] or "?",
                "change_pct": round(change_pct, 1), "recent_avg": round(recent_avg, 1), "prior_avg": round(prior_avg, 1),
            })
    trend_df = pd.DataFrame(trend_rows)

    GOING_DARK_MIN, GOING_DARK_MAX = 31, 60
    fs_now = fleet_status["last_activity_date"].max()
    fs_days_since = (fs_now - fleet_status["last_activity_date"]).dt.days
    going_dark = fleet_status[(fs_days_since >= GOING_DARK_MIN) & (fs_days_since <= GOING_DARK_MAX)]

    for company in COMPANIES:
        insights = []
        co_stale = payload["companies"][company]["stale_routes"]
        if co_stale:
            worst = co_stale[0]
            insights.append({
                "type": "stale_routes", "severity": "warning" if len(co_stale) < 10 else "critical",
                "count": len(co_stale), "worst_route_id": worst["route_id"],
                "worst_origin": worst["origin"], "worst_destination": worst["destination"],
                "worst_days_stale": worst["days_stale"],
            })

        if not trend_df.empty:
            co_trends = trend_df[trend_df["societe"] == company].sort_values("change_pct")
            for _, r in co_trends.iterrows():
                insights.append({
                    "type": "demand_rising" if r["change_pct"] > 0 else "demand_falling",
                    "severity": "info" if r["change_pct"] > 0 else "warning",
                    "route_id": r["route_id"], "origin": r["origin"], "destination": r["destination"],
                    "change_pct": abs(r["change_pct"]),
                })

        n_dark = int((going_dark["societe"] == company).sum())
        if n_dark > 0:
            insights.append({"type": "vehicles_going_dark", "severity": "warning", "count": n_dark})

        overview_row = next((r for r in payload["fleet_overview"] if r["company"] == company), None)
        if overview_row and overview_row["device_story"] == "device_limited":
            insights.append({
                "type": "device_opportunity", "severity": "info",
                "devices": overview_row["device_count"], "investment_devices": overview_row["investment_devices"],
                "coverage_now": overview_row["active_coverage_pct"], "coverage_then": overview_row["investment_coverage_pct"],
            })

        severity_rank = {"critical": 0, "warning": 1, "info": 2}
        payload["companies"][company]["insights"] = sorted(insights, key=lambda i: severity_rank.get(i["severity"], 3))
        print(f"{company}: {len(insights)} insights")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
