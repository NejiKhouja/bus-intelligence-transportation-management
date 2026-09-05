# Winicari Fleet Planner (web app)

A simple, 2D fleet-allocation dashboard for non-technical staff — pick a
company and how strictly to count "available" buses, see the real
optimizer output for that fleet size, try any other fleet size with a
genuine live recalculation, and see where those buses actually are on a
map. Available in English, French, and Arabic (with full RTL layout for
Arabic).

## Stack

- **Backend**: PHP 8.2, no framework.
  - `public/api.php` reads `data/fleet_data.json` (built by
    `scripts/build_demo_payload.py` + `scripts/build_map_data.py`,
    merged) and serves company/scenario slices as JSON, including a
    `map` layer (bus locations, route terminals, approximate depot)
    already filtered to the vehicles counted under the selected
    scenario, and a `demand_source` per route (`model` or `average` —
    see below).
  - `public/timetable.php` reads `data/timetable_data.json` (built by
    `scripts/build_timetable.py` from real ticket `sold_at` timestamps)
    and serves an hourly departure suggestion table for one route —
    service window, peak hour, suggested departures per hour with
    actual clock times. Only routes with enough hourly ticket history
    get one; the UI says so plainly when a route doesn't.
  - `public/optimize.php` — the **live** optimizer. Runs
    `scripts/live_allocate.py` as a real subprocess per request (via
    `proc_open`, array-form command, no shell string — not
    shell-injectable) for whatever fleet size the "Try a different
    fleet size" slider asks for, not a precomputed lookup. Needs a
    Python interpreter with pandas/scikit-learn/ortools on the server;
    set `WINICARI_PYTHON` if it isn't the hardcoded default path (see
    the constant at the top of that file). ~0.8s round trip measured
    locally (mostly Python interpreter startup, not the solve itself).
  - Neither endpoint talks to MongoDB directly — the Python pipeline
    already did the cleaning (operator aliases, sentinel vehicle codes)
    and holds the trained model; PHP only serves/re-runs against that
    trusted snapshot.
- **Demand numbers**: `scripts/predict_next_day_demand.py` uses the
  trained model (`models/demand/histgb_v1.joblib`, evaluated in
  `docs/baseline_results.md` — 14.4% better than a naive baseline) for
  the 33 routes it was actually trained on (>=200 days of history).
  Every other route — most of them, e.g. only 2/22 for SRT.ELGOUAFEL —
  keeps the recent-30-day average instead of a prediction from a model
  that never saw that route. The UI shows a small badge on each route
  so it's clear which numbers are which; nothing is silently upgraded
  to "model" that isn't.
- **AI Insights**: `scripts/build_demo_payload.py` computes a per-company
  list of automatically-detected findings — stale routes (no ticket
  activity in 45+ days), routes with demand up/down 25%+ in the last
  week vs. the three weeks before it, vehicles that were active but have
  gone quiet for 31–60 days, and (where the numbers support it) a device
  investment opportunity. All of it comes from the same freshness-
  anchored ticket/device data as the rest of the page — no separate
  model, just systematic comparison that would be tedious to do by hand
  per company. Rendered as a severity-coded card list (critical/warning/
  info) at the top of the page, right under the KPIs.
- **Frontend**: plain HTML/CSS/JS, no build step, no framework.
  - 2D grid of bus icons for the depot (deliberately not 3D — simplified
    for non-technical users).
  - Leaflet map (OpenStreetMap tiles) with small pseudo-3D bus icon
    markers (isometric-shaded SVG, not a WebGL scene), plus terminal and
    approximate-depot markers.
  - `assets/i18n.js` — a plain key/value dictionary (112 keys × 3
    languages, verified equal coverage programmatically) with a
    `t(lang, key, vars)` helper and RTL flip
    (`document.documentElement.dir`) for Arabic. Route names switch to
    the real Arabic place names from `winicari.ligne.orar/desar` when
    Arabic is selected, not a translation of the French ones.

## Where the map data comes from (and its real limits)

- **Bus locations**: each vehicle's last matched stop from its most
  recent reconstructed trip (reference DB) — more current than the raw
  `winicari.position` live feed (stale, and missing one of the four
  companies entirely). Verified 100% resolvable for all 4 companies (58
  vehicles). Only vehicles counted under the selected scenario are shown.
- **Terminals**: first/last stop per line, for lines with resolved
  geometry (varies 34/42–88/111 lines per company — the rest have no
  coordinate data anywhere in the source system).
- **Depot**: ONE approximate marker per company at its governorate
  capital (`OpenData.Delegation`) — there is no real depot address
  anywhere in the source data. Always labeled "approximate", never
  presented as an exact location.

## Run it locally

```bash
php -S localhost:8091 -t web/public
```
then open http://localhost:8091/index.php

Or drop `web/public/` into your XAMPP `htdocs/` (alongside `web/data/`,
one level up, since `inc/data.php` reads `../../data/fleet_data.json`
relative to `public/`) and open it through Apache instead.

## Refreshing the data

```bash
python scripts/build_demo_payload.py
python scripts/build_map_data.py
python -c "
import json
p = json.load(open('data/processed/demo_payload.json', encoding='utf-8'))
m = json.load(open('data/processed/map_data.json', encoding='utf-8'))
for co, v in m.items():
    if co in p['companies']: p['companies'][co]['map'] = v
json.dump(p, open('data/processed/demo_payload.json', 'w', encoding='utf-8'), ensure_ascii=False)
"
cp data/processed/demo_payload.json web/data/fleet_data.json
```

## Files

```
web/
├── data/fleet_data.json        snapshot (gitignored data, see above)
└── public/
    ├── index.php                page shell, renders first paint server-side
    ├── api.php                  GET ?company=&scenario= -> JSON (incl. map layer, insights)
    ├── timetable.php             GET ?company=&route_id= -> JSON hourly timetable
    ├── inc/data.php             shared data-loading/validation/map-filter helpers
    └── assets/
        ├── style.css            single light theme, RTL-aware (logical properties)
        ├── i18n.js               EN/FR/AR dictionary + apply/RTL logic
        └── app.js                rendering, Leaflet map, language switching
```

## What has been verified, and how

PHP syntax (`php -l`), live HTTP responses and JSON structure (curl
against the PHP dev server), JS syntax (`node --check`), dictionary
key-parity across all 3 languages (verified programmatically, not
eyeballed), and the live CDN URLs for Leaflet and the Google Fonts used
(checked with real HTTP requests, not assumed — this caught a wrong
Three.js version in an earlier pass).

The app has also been exercised in a real headless browser
(Playwright/Chromium) against the local PHP dev server: switching
between all 4 companies, all 3 scenarios, and all 3 languages (incl.
RTL), reading back rendered DOM content and console/page errors rather
than just HTTP responses. That caught a real bug the JSON-only checks
above couldn't have: `classList.add('')` threw whenever a company's
coverage percentage landed strictly between 60–100% (S.T.S did, after
the freshness-anchoring fix changed its numbers), which silently broke
the *entire* page re-render for that company on selection — not just
the KPI card. Fixed in `app.js` by guarding the two `classList.add`
calls instead of always calling one. Manual eyeballing in a real browser
window (not just Chromium headless) is still worth doing before showing
anyone, especially for how the map markers and RTL layout actually look.
