<?php
declare(strict_types=1);

require __DIR__ . '/inc/data.php';

$data = load_fleet_data();
$companyOrder = ['S.R.T.K', 'S.R.T.SELIANA', 'S.T.S', 'SRT.ELGOUAFEL'];
$companies = array_values(array_filter($companyOrder, static fn($c) => valid_company($data, $c)));
$defaultCompany = $companies[0];
$defaultScenario = 'active';

$companyData = $data['companies'][$defaultCompany];
$scenarioData = $companyData['scenarios'][$defaultScenario];
$includedIds = included_vehicle_ids($companyData['vehicles'], $defaultScenario);
$mapLayer = map_layer_for_scenario($companyData, $includedIds);

$scenarios = [
    ['key' => 'active', 'label' => 'Buses confirmed working', 'desc' => 'Real activity in the last 30 days.'],
    ['key' => 'signal', 'label' => 'Buses ever seen active', 'desc' => 'Includes older activity too, not just the last 30 days.'],
    ['key' => 'roster', 'label' => 'All registered buses', 'desc' => 'Every bus on file, including ones never confirmed active.'],
];
?>
<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Winicari Fleet Planner</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500;600&family=Noto+Sans+Arabic:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>

<header class="topbar">
  <div class="brand">
    <span class="brand-mark">🚌</span>
    <div>
      <h1 data-i18n="app_title">Winicari Fleet Planner</h1>
      <p class="brand-sub" data-i18n="app_sub">See how many buses you really have — and what they can cover</p>
    </div>
  </div>
  <div class="lang-switch" role="group" aria-label="Language">
    <button type="button" class="lang-btn active" data-lang="en">EN</button>
    <button type="button" class="lang-btn" data-lang="fr">FR</button>
    <button type="button" class="lang-btn" data-lang="ar">AR</button>
  </div>
</header>

<main class="page">

  <section class="controls card">
    <div class="control-block">
      <label for="company-select" data-i18n="label_company">Company</label>
      <select id="company-select">
        <?php foreach ($companies as $c): ?>
          <option value="<?= htmlspecialchars($c) ?>" <?= $c === $defaultCompany ? 'selected' : '' ?>><?= htmlspecialchars($c) ?></option>
        <?php endforeach; ?>
      </select>
    </div>

    <div class="control-block">
      <span class="control-label" data-i18n="label_scenario">Which buses to count</span>
      <div class="scenario-cards" id="scenario-cards" role="radiogroup" aria-label="Which buses to count">
        <?php foreach ($scenarios as $s): ?>
          <label class="scenario-card <?= $s['key'] === $defaultScenario ? 'checked' : '' ?>">
            <input type="radio" name="scenario" value="<?= htmlspecialchars($s['key']) ?>" <?= $s['key'] === $defaultScenario ? 'checked' : '' ?>>
            <span class="s-label" data-i18n="scenario_<?= htmlspecialchars($s['key']) ?>_label"><?= htmlspecialchars($s['label']) ?></span>
            <span class="s-desc" data-i18n="scenario_<?= htmlspecialchars($s['key']) ?>_desc"><?= htmlspecialchars($s['desc']) ?></span>
          </label>
        <?php endforeach; ?>
      </div>
    </div>
  </section>

  <section class="kpis" id="kpi-row">
    <div class="kpi">
      <span class="kpi-label" data-i18n="kpi_available_label">Buses available</span>
      <span class="kpi-value mono" id="kpi-available"><?= (int)$scenarioData['available_vehicles'] ?></span>
      <span class="kpi-sub" id="kpi-available-sub"></span>
    </div>
    <div class="kpi">
      <span class="kpi-label" data-i18n="kpi_demand_label">Passengers expected per day</span>
      <span class="kpi-value mono" id="kpi-demand"><?= number_format($scenarioData['total_demand']) ?></span>
      <span class="kpi-sub" id="kpi-demand-sub"></span>
    </div>
    <div class="kpi">
      <span class="kpi-label" data-i18n="kpi_covered_label">Seats these buses provide</span>
      <span class="kpi-value mono" id="kpi-covered"><?= number_format($scenarioData['total_covered']) ?></span>
      <span class="kpi-sub" data-i18n="kpi_covered_sub">seats/day</span>
    </div>
    <div class="kpi" id="kpi-coverage-card">
      <span class="kpi-label" data-i18n="kpi_coverage_label">How much demand is covered</span>
      <span class="kpi-value mono" id="kpi-coverage"><?= round($scenarioData['coverage_pct']) ?>%</span>
      <span class="kpi-sub" id="kpi-coverage-sub"></span>
    </div>
  </section>

  <section class="card insights" id="insights-section" hidden>
    <div class="section-head">
      <h2 data-i18n="insights_title">AI Insights</h2>
      <p class="section-sub" data-i18n="insights_sub">Patterns the system found in this company's data — automatically, from the same ticket and device records used above.</p>
    </div>
    <div class="insights-list" id="insights-list"></div>
  </section>

  <section class="card">
    <div class="section-head">
      <h2 data-i18n="depot_title">Bus depot</h2>
      <p class="section-sub" data-i18n="depot_sub">Every registered bus for this company. Color shows whether it's actually been seen working.</p>
    </div>

    <div class="legend">
      <span class="legend-item"><span class="dot dot-active"></span> <span data-i18n="legend_active">Confirmed working</span></span>
      <span class="legend-item"><span class="dot dot-signal"></span> <span data-i18n="legend_signal">Seen before, not recently</span></span>
      <span class="legend-item"><span class="dot dot-none"></span> <span data-i18n="legend_none">Never confirmed</span></span>
      <span class="legend-item legend-counted"><span class="ring-sample"></span> <span data-i18n="legend_counted">Counted in current selection</span></span>
    </div>

    <div class="depot-grid" id="depot-grid"></div>

    <div class="bus-detail" id="bus-detail" hidden>
      <button type="button" class="bus-detail-close" id="bus-detail-close" aria-label="Close">×</button>
      <div class="bus-detail-body" id="bus-detail-body"></div>
    </div>
  </section>

  <section class="card">
    <div class="section-head">
      <h2 data-i18n="map_title">Where your buses are</h2>
      <p class="section-sub" data-i18n="map_sub">Last known location of buses counted in this selection, plus route end points and this company's approximate base.</p>
    </div>
    <div class="legend">
      <span class="legend-item"><span class="map-dot map-dot-bus"></span> <span data-i18n="map_legend_bus">Bus</span></span>
      <span class="legend-item"><span class="map-dot map-dot-terminal"></span> <span data-i18n="map_legend_terminal">Route end point</span></span>
      <span class="legend-item"><span class="map-dot map-dot-depot"></span> <span data-i18n="map_legend_depot">Approximate base</span></span>
    </div>
    <div id="fleet-map" class="fleet-map"></div>
    <p class="map-note" data-i18n="map_note">Bus positions come from each vehicle's most recent recorded trip — not a live GPS feed. The base marker is an approximate area (governorate town), not a street address.</p>
  </section>

  <section class="card">
    <div class="section-head">
      <h2 id="routes-title" data-i18n="routes_title">Routes</h2>
      <p class="section-sub" id="routes-sub"></p>
    </div>
    <div class="route-list" id="route-list"></div>

    <div class="timetable-panel" id="timetable-panel" hidden>
      <button type="button" class="bus-detail-close" id="timetable-close" aria-label="Close">×</button>
      <div id="timetable-body"></div>
    </div>
  </section>

  <section class="card whatif">
    <div class="section-head">
      <h2 data-i18n="whatif_title">Try a different fleet size</h2>
      <p class="section-sub" data-i18n="whatif_sub">Move the slider and press Calculate — this runs the real optimizer again, live, for whatever number of buses you choose.</p>
    </div>
    <div class="whatif-controls">
      <label for="whatif-slider" data-i18n="whatif_label">Buses to test</label>
      <div class="whatif-row">
        <input type="range" id="whatif-slider" min="0" max="80" value="10" step="1">
        <output id="whatif-value" class="mono" for="whatif-slider">10</output>
        <button type="button" id="whatif-run" class="whatif-button" data-i18n="whatif_button">Calculate</button>
      </div>
    </div>
    <div id="whatif-result" class="whatif-result" hidden></div>
  </section>

  <section class="card explain">
    <h2 data-i18n="methodology_title">How this works</h2>
    <h3 data-i18n="methodology_forecast_title">1. Predicting how many passengers to expect</h3>
    <p data-i18n="methodology_forecast_body">For each route, the system looks at its recent ticket sales history and learns the pattern. Where a route has enough history, it uses a trained forecasting model; otherwise it uses a plain recent average instead of a forecast it can't yet trust.</p>
    <h3 data-i18n="methodology_allocation_title">2. Deciding which buses go where</h3>
    <p data-i18n="methodology_allocation_body">A real optimization program works out the assignment of buses to routes that leaves the fewest passengers uncovered, solved mathematically every time you change the inputs.</p>
    <p class="explain-note" data-i18n="explain_note">
      This page reads a snapshot prepared by the operations data pipeline — it is not connected live to the
      booking system, so numbers update whenever that snapshot is refreshed, not in real time.
    </p>
  </section>

  <section class="card purpose">
    <h2 data-i18n="purpose_title">What this is meant to show</h2>
    <p data-i18n="purpose_body">Two things, side by side: how well confirmed-working buses can cover real demand, and how much of the registered fleet can't currently be confirmed at all.</p>
  </section>

  <section class="card devices">
    <div class="section-head">
      <h2 data-i18n="devices_title">Tracking devices — and what more would be worth</h2>
      <p class="section-sub" data-i18n="devices_intro">Every bus that shows up as active or trackable does so because it's carrying one of your GPS/ticketing devices.</p>
    </div>
    <div id="devices-table" class="devices-table"></div>
    <p class="devices-caveat" data-i18n="devices_caveat"></p>
  </section>

  <section class="card conclusions">
    <h2 data-i18n="conclusions_title">Conclusions &amp; recommendations</h2>
    <p class="conclusions-intro" data-i18n="conclusions_intro"></p>
    <ol class="conclusions-list">
      <li data-i18n="conclusions_point_1"></li>
      <li data-i18n="conclusions_point_2"></li>
      <li data-i18n="conclusions_point_3"></li>
      <li data-i18n="conclusions_point_4"></li>
      <li data-i18n="conclusions_point_5"></li>
    </ol>
  </section>

</main>

<footer class="foot">
  <span data-i18n="app_title">Winicari Fleet Planner</span>
  <span id="footer-note">Snapshot data</span>
</footer>

<script>
  window.__INITIAL__ = {
    company: <?= json_encode($defaultCompany, JSON_UNESCAPED_UNICODE) ?>,
    company_full_name: <?= json_encode($companyData['full_name'] ?? $defaultCompany, JSON_UNESCAPED_UNICODE) ?>,
    company_full_name_ar: <?= json_encode($companyData['full_name_ar'] ?? $defaultCompany, JSON_UNESCAPED_UNICODE) ?>,
    scenario: <?= json_encode($defaultScenario) ?>,
    roster_size: <?= (int)$companyData['roster_size'] ?>,
    vehicles: <?= json_encode($companyData['vehicles'], JSON_UNESCAPED_UNICODE) ?>,
    included_vehicle_ids: <?= json_encode($includedIds, JSON_UNESCAPED_UNICODE) ?>,
    summary: <?= json_encode([
        'available_vehicles' => $scenarioData['available_vehicles'],
        'avg_capacity' => $scenarioData['avg_capacity'],
        'total_demand' => $scenarioData['total_demand'],
        'total_covered' => $scenarioData['total_covered'],
        'coverage_pct' => $scenarioData['coverage_pct'],
        'total_shortfall' => $scenarioData['total_shortfall'],
    ], JSON_UNESCAPED_UNICODE) ?>,
    routes: <?= json_encode($scenarioData['routes'], JSON_UNESCAPED_UNICODE) ?>,
    map: <?= json_encode($mapLayer, JSON_UNESCAPED_UNICODE) ?>,
    insights: <?= json_encode($companyData['insights'] ?? [], JSON_UNESCAPED_UNICODE) ?>
  };
  window.__FLEET_OVERVIEW__ = <?= json_encode($data['fleet_overview'] ?? [], JSON_UNESCAPED_UNICODE) ?>;
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script src="assets/i18n.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
