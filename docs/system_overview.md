# System Overview — Data, Models, and Why

A single narrative document tying together everything the other `docs/*.md`
files cover piece by piece: where the data comes from, what had to be fixed
before it could be trusted, which models were chosen and why, how they were
trained and evaluated, and what "AI" actually means in this system versus
what's deliberately plain arithmetic. Written for someone deciding whether to
trust this system with real operational decisions — every number below is
reproducible from a script named next to it, not a claim taken on faith.

This project is a separate, read-only layer next to BUS Software's existing
AI stack (RAG chatbot, ETA/delay prediction, anomaly detection). It never
writes to MongoDB or to the sibling `winicari` repo's reference database —
both are read-only inputs.

---

## 1. Data: what exists, and what was chosen

### 1.1 The raw sources

Three MongoDB databases and one SQLite reference database, read from
`mongodb://localhost:27017` and a sibling repo respectively:

| Source | What it holds | Why it was used |
|---|---|---|
| `winicari` | Live ops: vehicles, routes, stops, fares, ~1 week of rolling live GPS/tickets | The only source for vehicle/route master data (capacity, operator, stop sequence) |
| `Historique_Tickets` | Yearly ticket sales archive, 2019–2026 (~5.5M rows) | The only demand signal that exists — no separate "ridership" dataset |
| `Historique_pos` | Daily GPS ping collections, 2022–2026 | Only historical location signal; used to reconstruct trips, not read raw |
| `OpenData` (Tunisian gov't data) | Geocoded stops, governorate boundaries, a weather/holiday calendar | Fills in coordinates and calendar context nothing else in the system has |
| Reference DB (sibling `winicari` repo, SQLite) | Cleaned companies, clustered stops, resolved line geometry, reconstructed trips | Built by the sibling project's own delay/ETA/anomaly work — reusing it read-only avoided re-solving already-solved problems (see §1.3) |

Full field-level detail: `docs/data_dictionary.md`. Full collection
inventory with row counts: `docs/database.md`.

**Why ticket sales, not a GPS-derived ridership estimate, is the demand
signal.** GPS tells you where a bus was, not how many passengers boarded.
Ticket sales are the only direct passenger-count record in the entire
platform. This does undercount demand that never got ticketed (turned-away
passengers, informal transport) — a real limitation, noted rather than
hidden, and not fixable without a different data source.

**Why the reference DB, not re-deriving everything from raw Mongo.** The
sibling repo already spent effort clustering four overlapping, disagreeing
stop tables (`Station`, `Station2`, `Station_new`, `Station_sts` — 2,898 /
2,525 / 1,212 / 1,113 rows, no shared key) into one clustered `stops` table
(3,248 rows, DBSCAN by 150m proximity, confidence-tiered), and reconstructing
47,567 real bus trips with matched per-stop timing from raw GPS pings —
something nothing in raw Mongo provides directly. Rebuilding that here would
have been redundant work with a real chance of disagreeing with the sibling
project's own delay/ETA model, which depends on the same reconstruction being
consistent. `src/database/reference_db.py` reads it read-only; if it's not
present (`reference_db.is_available()` returns false), the raw-Mongo
extraction functions are the fallback.

### 1.2 Why these specific companies, and why 4 not 10

Winicari serves ~10 regional operators. The demo/planning layer scopes to 4
(`S.R.T.K`, `S.R.T.SELIANA`, `S.T.S`, `SRT.ELGOUAFEL`) — not an arbitrary
sample, but the ones with resolvable company identity and enough ticket/GPS
history to support anything beyond a placeholder screen. Nothing prevents
extending to the other 6; they simply weren't verified to have usable data
before deciding to build on top of them.

### 1.3 Data quality problems found, and how each was handled

None of these were assumed — each was checked against real data before
deciding how to handle it (`scripts/explore_database.py`,
`scripts/generate_quality_report.py`, both re-runnable).

| Problem | Evidence | Fix |
|---|---|---|
| Same operator, different name strings | `S.R.T.GAFSA` and `SRT.ELGOUAFEL` are the same company; `winicari`/`Winicari` is a platform placeholder, not a real operator | `cleaning.normalize_societe_name()` / `extraction.build_company_alias_map()` |
| Corrupted field names | `winicari.klm`'s operator field is `Soci�t�` — legacy-codepage mojibake | Accessed defensively; never assumed the literal accented key |
| Epoch-date artifact | 192 tickets (2025/2026, all one operator's devices) carry a literal `1970/01/01 01:00:00` — a device clock-reset, not a real sale date; each is a duplicate of a real ticket under the same identity | `parse_flexible_datetime()` rejects any parsed year outside 2015–2035 rather than silently accepting it as real |
| Sentinel / non-vehicle codes | Vehicle codes `"0"`, `"9999"`, `"1111"`, `"11111"`, `"111"` reused across multiple unrelated companies — impossible for a real plate — and `"0"`'s matricule literally means "counter" in French: the office ticket counter, not a bus. It shows up as `is_recently_active=True` constantly, since counter sales never stop | Excluded before any fleet/demand computation (`SENTINEL_VEHICLE_IDS` in `scripts/build_demo_payload.py`); verified against `vehicles.parquet` before excluding, not assumed |
| `fonctionnel` flag is unreliable | Of 162 vehicles marked `fonctionnel=True`, 125 (77%) show **no recent activity** under an evidence-based check | Replaced by `derive_fleet_operational_status()`, combining GPS-trip activity (69 vehicles) with an 8-year ticket-sales fallback (157 more) — see §1.4 |
| GPS speed outliers | One vehicle logged a 530 km/h jump (30.86°N→34.38°N in 2 minutes) in one day's collection | Rare (0.016% of a 5,000-row sample >120 km/h) but filtered downstream; never trusted raw |
| `trip_stops` bad-leg patterns | ~12% of matched-to-matched stop pairs actually skip 1+ unmatched stops in between (not a real single leg); a separate class has a genuine dark-period gap. The worst case found was a 10.8h "leg" that isn't real | Both excluded by default in `travel_times_from_trip_stops()` (`exclude_skipped_stops`, `exclude_dark_gaps`), cutting max leg duration from ~10.8h to ~6.5h |
| `trip_stops.dist_m` looked like leg distance but isn't | Checked against the sibling repo's own code: it's the distance from a GPS fix to the stop it matched — a match-quality metric computed once per stop, not a leg length | Renamed to `arrival_match_distance_m` in this project's output so the wrong assumption can't silently propagate |
| 2023 ticket volume dip | 491k tickets in 2023 vs 1.27M (2022) and 1.08M (2024) | Confirmed as a ticketing-machine outage, not a real demand drop, before deciding to downweight 2023 rather than treat it as signal |
| **Demand-averaging window anchored to the wrong date (the most serious bug found this session)** | The "recent 30-day average" for each route was computed relative to *that route's own* last-seen date, not the dataset's real end date. A route last active 831 days ago still produced a "recent" average from a handful of days near its own stale cutoff, presented as current. Checked broadly: 60/106 routes (57%) across all 4 companies hadn't reported in 14+ days as of the real snapshot end date; S.T.S specifically had only 6–7 of 38 routes genuinely current | Fixed in two parts, both in `scripts/build_demo_payload.py`: (1) the averaging window is now anchored to `demand["time_bucket"].max()` — the dataset's one real end date — for every route, not each route's own; (2) routes with no ticket activity within `FRESHNESS_DAYS=45` of that real end date are excluded from demand/allocation entirely and instead surfaced explicitly as a "stale routes" list, visible in the UI rather than silently smoothed into an average that misrepresents them |
| `classList.add('')` frontend bug (found via browser testing, not a data bug) | Threw a JS exception — silently breaking the entire page re-render — whenever a company's coverage percentage landed strictly between 60–100%, which S.T.S's numbers did after the freshness fix above changed them | Guarded the two `classList.add` calls in `app.js` instead of always calling one; caught by headless-browser testing across all 4 companies, not by the JSON-only checks that had been relied on before |

### 1.4 Vehicle operational status — a second-order derived signal

`winicari.bus.fonctionnel` can't be trusted (above), so operational status is
derived from actual evidence instead:

1. **GPS trips** (`derive_operational_vehicles()`): a vehicle with a
   reconstructed trip in the last 30 days (relative to the *data's* latest
   date, not today's wall-clock date — the dataset itself ends months before
   "now"). Covers 69 vehicles.
2. **Ticket sales fallback** (`derive_operational_vehicles_from_tickets()`):
   for vehicles with no GPS history at all, the same recency check against
   ticket sales across all 8 years of `Historique_Tickets`. Covers another
   157.

Combined (`derive_fleet_operational_status()`): 226 of 762 unique
vehicle records (30%) have *some* activity signal. The remaining 536 (70%)
show **zero** activity in either signal, across the full 8-year archive —
not a coverage gap in the analysis, but evidence that most of `winicari.bus`
isn't a current, pruned fleet list. This is flagged for the business
directly (`docs/roadmap.md`, item 1) rather than assumed away — vehicle
allocation is planned against whichever subset the business confirms is
real, and the demo UI's three scenarios (`active`/`signal`/`roster`) exist
specifically so this uncertainty is shown, not hidden behind one number.

### 1.5 Tracking devices — a hard physical constraint, not a modeling choice

BUS Software supplies the GPS/ticketing hardware each operator uses.
`winicari.appareil` (one document per physical device) is queried directly
by `device_counts_by_company()` and cross-checked against the "active
vehicle" count per company: S.T.S has exactly 5 devices and exactly 5
"active" vehicles — not a coincidence. That company's usable fleet is
capped by device supply, not by how many of its 370 registered buses still
physically run.

This matters because it changes the recommendation. A company whose active
count is far below its registered roster could mean "buses are broken and
retired" (nothing to sell) or "there aren't enough devices to see/count more
of them" (a purchasable fix). The two stories look identical in a raw
active-vs-roster comparison but require opposite advice, so the system
distinguishes them with a ratio check, not a threshold guess:

```
device_ratio = devices / active_vehicles
device_limited      if 0.7 <= device_ratio <= 1.3   (devices and active count nearly match)
not_device_limited  otherwise
```

A naive `active <= devices` check was tried first and rejected: it would
have also flagged SRT.ELGOUAFEL (29 devices, 9 active) as device-limited,
when that company visibly has *spare* device capacity — the opposite
conclusion. The ratio check was verified against the two clearest real
cases before trusting it: S.T.S (ratio 1.0 → correctly `device_limited`)
and SRT.ELGOUAFEL (ratio 3.2 → correctly `not_device_limited`).

For companies flagged `device_limited`, the system runs the real optimizer
a second time at a larger fleet size (`INVESTMENT_MULTIPLIER = 2`× current
devices, capped at the company's full roster — never proposed below what's
already observed, which would misleadingly look like buying hardware
*reduces* coverage) and reports the resulting coverage percentage next to
today's, so the business case for more devices is a computed number, not a
sales pitch.

---

## 2. Feature engineering

### 2.1 Demand forecasting (`src/features/demand_features.py`)

From `transformations.aggregate_demand()` output (`route_id, time_bucket,
passenger_count, revenue`):

- **Calendar**: day-of-week, `is_weekend` (Friday/Saturday — Tunisia's actual
  weekend, not the Western Saturday/Sunday default).
- **Lags**: `passenger_count` shifted 1 and 7 days per route
  (`lag_1`, `lag_7`) — the most recent value and the same weekday last week,
  the two anchors a transit-demand series is dominated by.
- **`route_id` as a categorical feature**, not one-hot encoded — passed
  directly to `HistGradientBoostingRegressor(categorical_features=
  ["route_id"])`, which handles high-cardinality categoricals natively
  without exploding the feature space the way one-hot would across ~100+
  routes.

**Deliberately not done**: a holiday/school-break join from
`OpenData.historiqueJourMeteo`. That calendar is recorded per weather
*station*, and whether station-level coverage lines up cleanly with
route-level demand was never validated — shipping an unvalidated join would
have been a worse choice than leaving it out and saying so.

### 2.2 Travel time (`src/features/travel_time_features.py`)

Hour-of-day and day-of-week extracted from `segment_start` /
`departure_time`. Grain is deliberately `(line_id, from_stop_id, to_stop_id,
hour, dow)`, not `(line_id, hour, dow)` — a route's individual legs vary
wildly in length, so "the route's average" would blend a 3-minute hop with a
40-minute one into a meaningless number. A specific stop-to-stop leg at a
specific hour/weekday is the right unit to predict.

### 2.3 Filtering thresholds, and why they're where they are

Both baselines filter to groups with enough history to support a meaningful
train/test split, not an arbitrary round number:

- Demand: routes with **≥200 daily observations** (33 of 106 routes,
  16,062/17,884 eligible rows) — anything sparser can't support a 56-day
  holdout and a lag-7 feature without mostly-empty test windows.
- Travel time: leg-groups with **≥30 occurrences** (373 of many more
  possible (line, from_stop, to_stop) combinations, 170,681 rows) — same
  reasoning, scaled to how much faster individual legs accumulate
  observations than whole-route daily totals.

---

## 3. Model choice, and why

### 3.1 Why gradient-boosted trees, not something else

`HistGradientBoostingRegressor` (scikit-learn) was chosen over deep
learning, linear models, or LightGBM/XGBoost specifically:

- **The data is tabular, mixed-type, and mid-sized** (tens of thousands of
  rows, a handful of features) — exactly the regime where gradient-boosted
  trees consistently outperform neural networks, which need far more data
  and tuning to earn their added complexity here.
- **Native categorical support** matters concretely: `route_id` has no
  natural ordering and moderate cardinality. One-hot encoding it would
  balloon the feature space; a plain integer encoding would invent a false
  ordering. `HistGradientBoostingRegressor`'s built-in categorical handling
  avoids both.
- **No feature scaling needed** — tree splits are scale-invariant, one less
  preprocessing step (and one less place to introduce a train/serve
  mismatch) than a linear or neural approach would require.
- **scikit-learn over LightGBM/XGBoost**: scikit-learn was already a
  dependency; `HistGradientBoostingRegressor` gets within the same
  ballpark of accuracy as either on data this size. Pulling in a new
  dependency for a marginal, unproven gain wasn't justified — noted
  explicitly in `src/models/demand_forecasting.py` as a decision to
  revisit if accuracy ever proves insufficient, not a permanent choice.

### 3.2 The baseline discipline — and what it caught

Every model is scored against the simplest rule that could plausibly work,
on the exact same test rows, before being trusted:

- **Demand**: naive "same value 7 days ago" (`lag_7`). A transit demand
  series is strongly weekly-periodic — Monday looks like last Monday far
  more than it looks like yesterday — so this is a genuinely hard baseline
  to beat, not a strawman.
- **Travel time**: historical mean per `(line, from_stop, to_stop, hour,
  dow)` — the average of exactly the same grain the model predicts at.

This discipline is what separates the two models' outcomes:

| | Demand (HistGB) | Travel time (HistGB) |
|---|---|---|
| Baseline MAE | 39.38 | 93.9s |
| Model MAE | 33.71 | 86.9s |
| Improvement | **14.4%** | 7.4% |
| Verdict | **Ships** — meaningful, consistent margin | **Held back** — doesn't clearly beat the mean rule |

The demand model earns its place: a trained model that's meaningfully more
accurate than "assume this week looks like last week" is worth the added
complexity and the risk of it being wrong in a new way a human wouldn't be.

The travel-time model does not clear that bar. 7.4% is a real but thin
margin, and thinner than the demand model's, on a target (travel time) where
the historical-mean baseline is already strong because traffic patterns
repeat closely by hour and weekday. Shipping it as an equal, unlabeled
alternative to the mean would mean presenting a number that isn't
dependably better than the simple one already available — a worse choice
than not shipping it at all. This isn't a permanent rejection: as noted in
`docs/baseline_results.md`, more data or better features (e.g. leg distance
computed from stop coordinates rather than the mismeasured `dist_m` field —
see §1.3) could close that gap; the model artifact is kept
(`models/travel_time/histgb_v1.joblib`) specifically so re-evaluating it
later doesn't mean retraining from scratch. A compromise middle path — an
"Experimental" label rather than full withdrawal — was discussed and left as
a future option rather than something to ship silently.

### 3.3 Evaluation metrics, and why MAPE is misleading here

MAE and RMSE are the primary metrics; MAPE is reported but explicitly
flagged as unreliable for this data, not silently trusted:

- The 33 scored demand routes range from ~13 to ~2,841 daily passengers
  (median 49). MAPE blows up on the low-volume end — a miss of 3 passengers
  on a true value of 1 is a "300% error" that says nothing useful about
  whether the model is good. MAE/RMSE, in absolute passenger counts, are
  the metrics that actually answer "how far off is a typical prediction."
- A per-route-normalized or log-scale target would likely tame MAPE
  further, but wasn't pursued — it wasn't needed to answer the one question
  that mattered (does a learned model beat the naive rule), and adding it
  without a reason would have been unnecessary complexity.

---

## 4. Training process

Both baselines follow the same three-step process
(`scripts/train_demand_baseline.py`, `scripts/train_travel_time_baseline.py`,
both re-runnable end to end):

1. **Filter to groups with enough history** (§2.3), then compute features.
2. **Time-based split, not random** — a demand or travel-time model
   evaluated on randomly held-out rows would leak future information into
   training (a lag feature computed using a value that's actually in the
   "test" set). Demand uses a **per-route** cutoff: each route's own last 56
   days held out, everything before it for training — necessary because
   different routes have different history lengths and end dates. Travel
   time uses a **global** cutoff (last 8 weeks of the overall date range)
   instead, since the historical-mean baseline doesn't depend on per-group
   temporal continuity the way the demand model's lag features do.
3. **Score baseline and model on the identical test rows** — the same rows,
   the same target values, so the comparison in §3.2 isn't comparing two
   different samples.

Both scripts are deterministic given the same input parquet files
(`random_state=0` on the model, no random splitting) and write both the
trained model artifact (`models/<task>/histgb_v1.joblib`, via `joblib`) and
the results table back into `docs/baseline_results.md` — the numbers in this
document and in that one are the same run, not independently transcribed.

At inference time (`scripts/predict_next_day_demand.py`), the exact training
`route_id` categorical dtype is reconstructed (same sorted set of eligible
route IDs) before calling `.predict()` — scikit-learn's categorical
handling encodes categories by their position in a fixed category list, so
predicting with a differently-ordered or differently-populated category set
would silently misencode `route_id` into the wrong integer code and produce
confident, wrong predictions with no error raised. This was verified, not
assumed: the model's predictions on held-out data show 33 distinct
prediction *patterns*, one per trained route, confirming it's actually using
`route_id` rather than collapsing every route into one shared estimate.

---

## 5. The optimization layer — why OR-Tools, not a bigger model

Scheduling and vehicle allocation are **combinatorial decisions under hard
constraints** (a vehicle can't serve two routes at once; a route's assigned
capacity can't exceed how many vehicles the company actually has). A machine
learning model predicts *uncertain* quantities — demand, travel time — well,
but has no natural way to *guarantee* a hard constraint is respected; it
would need to be coerced into it with penalty terms and post-hoc clipping,
which is both less reliable and less interpretable than a solver built for
exactly this class of problem.

So the system is deliberately two separate layers, not one combined model:
ML predicts the environment (demand); OR-Tools' CP-SAT solver
(`src/optimization/vehicle_optimizer.py`) decides the assignment under
constraints, exactly and provably optimal for a problem this size (dozens of
routes, a handful of companies) — not a heuristic approximation.

**The model**: vehicles within a company are treated as fungible (a
*count* per route, not specific vehicle IDs assigned) — reasonable since
capacity barely varies within a company. For each route, an integer decision
variable (how many vehicles to assign) and a shortfall variable (unmet
demand) are linked by `shortfall >= demand - assigned * avg_capacity`, one
capacity constraint per company (`sum(assigned) <= available_vehicles`), and
the objective minimizes total shortfall across all routes. Solved in well
under a second for the problem sizes here (`max_time_in_seconds = 30` as a
safety cap, never approached in practice); solver status is checked and
raises rather than silently returning a non-optimal or infeasible result.

This same solver is what runs live, per request, behind the "try a different
fleet size" slider in the web app (`web/public/optimize.php` →
`scripts/live_allocate.py`, via `proc_open`) — not a precomputed lookup
table. Whatever number of buses the user asks about gets a real, freshly
solved allocation.

A worked example of its output — 4 companies, 146 routes, 69 confirmed
operational vehicles, 37.0% demand coverage at that fleet size — is in
`docs/optimization_results.md`; the low coverage number there reflects a
real capacity constraint (most of the registered fleet has no confirmed
activity signal, §1.4), not a solver weakness.

---

## 6. The demo/planning layer — turning the pipeline into everyday decisions

Everything above answers "does the model beat a baseline." This section is
about what was built on top of it to make the pipeline's output actually
useful day to day for non-technical staff — the part of the "go wild, be
creative" request that's genuinely new, not a restatement of the ML/
optimization work above.

### 6.1 Suggested timetables (`scripts/build_timetable.py`)

The daily demand number by itself doesn't tell an operator when to run
buses. This turns it into clock times:

1. **Hourly demand shape** per route — the real proportion of ticket sales
   falling in each hour of day, computed from all three persisted ticket
   years (2024–2026) rather than the 30-day window the daily figures use,
   because hourly patterns are noisier and need more history to be stable.
   Hours under 1.5% of a route's traffic are dropped as noise, not real
   service (`MIN_HOUR_SHARE`).
2. That shape is applied to the route's already-computed `predicted_demand`
   (model-based or recent-average, whichever applies — carried through
   unchanged, not recomputed) to get expected passengers per hour.
3. **Suggested departures per hour** = `ceil(passengers_that_hour /
   avg_capacity)`, spaced evenly across the hour into real clock times
   (e.g. 2 departures in the 07:00 hour → `07:00`, `07:30`).

A real bug was caught and fixed here during this session: the ceiling
calculation was originally written as `-(-int(passengers) // int(
avg_capacity))` — a common ceiling-division idiom, except `int(passengers)`
truncates *before* the division happens, so 54.8 passengers (needing 2
buses at 54-seat capacity) computed as needing only 1. Fixed with
`math.ceil(passengers / avg_capacity)`, which does the division in floating
point first. This under-coverage bug would have silently suggested too few
departures on any route whose hourly passenger count wasn't a clean
multiple of bus capacity — most of them.

Explicitly **not** solved: which specific bus serves which suggested
departure, turnaround time between trips, or driver shifts — none of that
data exists yet to validate against (`docs/optimization_problem.md`,
Problems 1/3). This is a demand-driven frequency suggestion, stated as
that, not a fully constrained operational roster.

### 6.2 AI Insights — automatic, per-company findings

The most direct answer to "where is the AI in this, and what would help
every day": rather than making a human read through dozens of routes and
vehicles per company looking for problems, the system computes and
surfaces them automatically, every time the snapshot refreshes. This is
built from the same freshness-anchored data as everything above — no new
model, and it isn't presented as one. It's systematic statistical
comparison applied consistently across every route and vehicle, the kind of
scan that's tedious and error-prone to do by hand across 4 companies and
100+ routes, done exactly the same way every time instead. Five finding
types, each severity-ranked (`critical` > `warning` > `info`) so the most
urgent shows first:

1. **Stale routes** — routes with no ticket activity in `FRESHNESS_DAYS`
   (45) or more, already computed for the freshness fix in §1.3, surfaced
   directly instead of just silently excluded. `critical` if 10+ routes are
   stale for a company, `warning` otherwise.
2. **Demand rising / falling** — per route, the last 7 days' average demand
   compared to the 23 days before that (so a full ~30-day window split
   recent-vs-prior). Flagged only when the prior-period average is at least
   5 passengers/day (too small a base makes a percentage change noise, not
   signal) and the change is 25% or more in either direction — thresholds
   chosen to surface real shifts, not weekday-to-weekday jitter.
3. **Vehicles going dark** — vehicles whose last confirmed activity was
   31–60 days ago (relative to the fleet-wide latest activity date, not
   today). The window's lower bound (31) deliberately excludes vehicles
   already counted as recently active elsewhere in the UI, so this doesn't
   duplicate that signal; the upper bound (60) keeps it to vehicles that
   plausibly still matter operationally, rather than ones long since
   written off.
4. **Device investment opportunity** — for companies flagged
   `device_limited` (§1.5), the computed before/after coverage percentages
   from the real second optimizer run.

Each finding is a plain, typed record (route/vehicle IDs, counts,
percentages — no free text generated) rendered by the frontend into
severity-coded cards, and templated into English, French, and Arabic
through the same `t(lang, key, vars)` i18n system the rest of the page uses —
never machine-translated at request time, and never presented with false
precision (percentages are rounded for display, not implying more accuracy
than the underlying 7-day sample supports).

**Why this wasn't built as a chatbot.** BUS Software's existing AI layer
already includes a RAG chatbot; duplicating that here would be redundant
scope, not a new feature, and was explicitly ruled out for that reason.

**What was verified before shipping this.** The computed insight counts (12
for S.R.T.K, 1 for S.R.T.SELIANA, 6 for S.T.S, 5 for SRT.ELGOUAFEL) were
read back and checked by hand for plausibility — route IDs and companies
match, percentages fall in a believable range, staleness figures agree with
the routes already flagged in §1.3 — before wiring into the UI. The full
page was then exercised in a real headless browser (Playwright/Chromium)
across all 4 companies and all 3 languages, reading back actual rendered
DOM content rather than trusting the JSON response alone. That's what
caught the `classList.add('')` bug in §1.3 — a bug the API-only checks used
throughout the rest of this project could not have found, because the API
response itself was correct; only the frontend's *handling* of one specific
value range was broken.

---

## 7. What this system is not

Said plainly, for anyone deciding how much to trust it:

- **The demand model is a next-day forecast for 33 routes** (those with
  enough history) — every other route uses a recent average, clearly
  labeled as such in the UI (`demand_source: "average"` vs `"model"`), never
  silently upgraded.
- **The travel-time model is not in production** — it exists, it's
  evaluated, and it's held back because it doesn't clearly beat a simple
  historical average (§3.2).
- **AI Insights is rule-based statistical detection, not a trained model.**
  It's accurately called "intelligent" in the sense of automatically
  surfacing what a human analyst would have to dig for — but it is
  thresholds and comparisons on real data, not a black box, and that's a
  deliberate choice: for a system a client will act on financially (buying
  devices, retiring vehicles), an inspectable rule a person can double-check
  is more trustworthy than a model whose reasoning can't be shown.
- **Driver scheduling isn't attempted** — no driver availability data exists
  anywhere in the platform (`docs/optimization_problem.md`, Problem 3).
- **This is a snapshot, not a live feed.** Every number on the page reflects
  whenever `scripts/build_demo_payload.py` was last run, not the current
  moment — stated explicitly in the UI's methodology section, not left
  implicit.

---

## 8. Reproducing every number in this document

```bash
python scripts/train_demand_baseline.py          # -> docs/baseline_results.md, models/demand/histgb_v1.joblib
python scripts/train_travel_time_baseline.py      # -> docs/baseline_results.md, models/travel_time/histgb_v1.joblib
python scripts/generate_quality_report.py         # -> docs/data_quality_report.md
python scripts/run_vehicle_allocation.py          # -> docs/optimization_results.md
python scripts/build_demo_payload.py              # -> data/processed/demo_payload.json (incl. insights)
python scripts/build_timetable.py                 # -> data/processed/timetable_data.json
python scripts/build_map_data.py                  # -> data/processed/map_data.json
```

Nothing in this document is a projection or an estimate presented as
measured — every figure above is the literal output of one of these
scripts, re-runnable against the live database at any time.
