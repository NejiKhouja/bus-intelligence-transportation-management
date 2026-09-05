(function () {
  "use strict";

  var t = window.I18N.t;
  var lang = 'en';
  try { lang = localStorage.getItem('winicari-lang') || 'en'; } catch (e) {}

  var state = {
    company: window.__INITIAL__.company,
    scenario: window.__INITIAL__.scenario
  };
  var vehicleLookup = {};
  var lastPayload = window.__INITIAL__;

  var els = {
    companySelect: document.getElementById('company-select'),
    scenarioCards: document.querySelectorAll('.scenario-card'),
    kpiAvailable: document.getElementById('kpi-available'),
    kpiAvailableSub: document.getElementById('kpi-available-sub'),
    kpiDemand: document.getElementById('kpi-demand'),
    kpiDemandSub: document.getElementById('kpi-demand-sub'),
    kpiCovered: document.getElementById('kpi-covered'),
    kpiCoverage: document.getElementById('kpi-coverage'),
    kpiCoverageSub: document.getElementById('kpi-coverage-sub'),
    kpiCoverageCard: document.getElementById('kpi-coverage-card'),
    depotGrid: document.getElementById('depot-grid'),
    busDetail: document.getElementById('bus-detail'),
    busDetailBody: document.getElementById('bus-detail-body'),
    busDetailClose: document.getElementById('bus-detail-close'),
    routesTitle: document.getElementById('routes-title'),
    routesSub: document.getElementById('routes-sub'),
    routeList: document.getElementById('route-list'),
    insightsSection: document.getElementById('insights-section'),
    insightsList: document.getElementById('insights-list'),
    footerNote: document.getElementById('footer-note'),
    langButtons: document.querySelectorAll('.lang-btn'),
    whatifSlider: document.getElementById('whatif-slider'),
    whatifValue: document.getElementById('whatif-value'),
    whatifRun: document.getElementById('whatif-run'),
    whatifResult: document.getElementById('whatif-result')
  };

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtInt(n) { return Math.round(n).toLocaleString('en-US'); }
  function companyDisplayName(payload) {
    if (lang === 'ar') return payload.company_full_name_ar || payload.company;
    return payload.company;
  }
  function routeOrigin(r) { return lang === 'ar' ? (r.origin_ar || r.origin) : r.origin; }
  function routeDestination(r) { return lang === 'ar' ? (r.destination_ar || r.destination) : r.destination; }

  /* ================= language switching ================= */
  function setLang(newLang) {
    lang = newLang;
    try { localStorage.setItem('winicari-lang', lang); } catch (e) {}
    els.langButtons.forEach(function (b) { b.classList.toggle('active', b.dataset.lang === lang); });
    window.I18N.applyStaticTranslations(lang);
    render(lastPayload);
    renderDevicesTable();
  }
  els.langButtons.forEach(function (b) {
    b.addEventListener('click', function () { setLang(b.dataset.lang); });
  });

  /* ================= main render ================= */
  var lastSyncedWhatifCompany = null;

  function render(payload) {
    lastPayload = payload;
    vehicleLookup = {};
    payload.vehicles.forEach(function (v) { vehicleLookup[v.vehicle_id] = v; });
    var includedSet = new Set(payload.included_vehicle_ids);

    renderKpis(payload);
    renderInsights(payload);
    renderDepot(payload.vehicles, includedSet);
    renderRoutes(payload);
    renderMap(payload.map);
    els.busDetail.hidden = true;
    if (timetableEls.panel) timetableEls.panel.hidden = true;
    els.footerNote.textContent = t(lang, 'footer_showing', { company: companyDisplayName(payload) });

    // Only reset the what-if slider when the company actually changed —
    // not on every scenario/language switch, which would wipe out
    // whatever fleet size the user was experimenting with.
    if (payload.company !== lastSyncedWhatifCompany) {
      lastSyncedWhatifCompany = payload.company;
      syncWhatifRangeToCompany(payload);
    }
  }

  function renderKpis(payload) {
    var summary = payload.summary;
    els.kpiAvailable.textContent = fmtInt(summary.available_vehicles);
    els.kpiAvailableSub.textContent = t(lang, 'kpi_available_sub', { roster: fmtInt(payload.roster_size) });
    els.kpiDemand.textContent = fmtInt(summary.total_demand);
    els.kpiDemandSub.textContent = t(lang, 'kpi_demand_sub', { routes: payload.routes.length });
    els.kpiCovered.textContent = fmtInt(summary.total_covered);
    els.kpiCoverage.textContent = Math.round(summary.coverage_pct) + '%';
    els.kpiCoverageSub.textContent = summary.total_shortfall > 0
      ? t(lang, 'kpi_coverage_short', { n: fmtInt(summary.total_shortfall) })
      : t(lang, 'kpi_coverage_full');
    els.kpiCoverageCard.classList.remove('good', 'critical');
    if (summary.coverage_pct >= 100) els.kpiCoverageCard.classList.add('good');
    else if (summary.coverage_pct < 60) els.kpiCoverageCard.classList.add('critical');
  }

  /* ================= AI insights ================= */
  var INSIGHT_ICONS = {
    stale_routes: '🕓',
    demand_falling: '📉',
    demand_rising: '📈',
    vehicles_going_dark: '📡',
    device_opportunity: '🔧'
  };

  function insightText(insight) {
    switch (insight.type) {
      case 'stale_routes':
        return t(lang, 'insight_stale_routes', {
          count: insight.count, route: insight.worst_route_id,
          origin: insight.worst_origin, destination: insight.worst_destination,
          days: insight.worst_days_stale
        });
      case 'demand_falling':
        return t(lang, 'insight_demand_falling', {
          route: insight.route_id, origin: insight.origin, destination: insight.destination,
          pct: Math.round(insight.change_pct)
        });
      case 'demand_rising':
        return t(lang, 'insight_demand_rising', {
          route: insight.route_id, origin: insight.origin, destination: insight.destination,
          pct: Math.round(insight.change_pct)
        });
      case 'vehicles_going_dark':
        return t(lang, 'insight_vehicles_going_dark', { count: insight.count });
      case 'device_opportunity':
        return t(lang, 'insight_device_opportunity', {
          devices: insight.devices, investment: insight.investment_devices,
          coverage_now: Math.round(insight.coverage_now), coverage_then: Math.round(insight.coverage_then)
        });
      default:
        return '';
    }
  }

  function renderInsights(payload) {
    var insights = payload.insights || [];
    if (!insights.length) {
      els.insightsSection.hidden = true;
      els.insightsList.innerHTML = '';
      return;
    }
    els.insightsSection.hidden = false;
    var html = '';
    insights.forEach(function (insight) {
      var severity = insight.severity || 'info';
      var icon = INSIGHT_ICONS[insight.type] || '•';
      html += '<div class="insight-card insight-' + escapeHtml(severity) + '">' +
        '<span class="insight-icon">' + icon + '</span>' +
        '<div class="insight-body">' +
        '<span class="insight-pill">' + escapeHtml(t(lang, 'insight_severity_' + severity)) + '</span>' +
        '<p>' + escapeHtml(insightText(insight)) + '</p>' +
        '</div></div>';
    });
    els.insightsList.innerHTML = html;
  }

  /* ================= depot grid ================= */
  function renderDepot(vehicles, includedSet) {
    var html = '';
    vehicles.forEach(function (v) {
      var classes = ['bus-cell', v.status];
      if (includedSet.has(v.vehicle_id)) classes.push('counted');
      html += '<button type="button" class="' + classes.join(' ') + '" data-vehicle-id="' +
        escapeHtml(v.vehicle_id) + '" title="' + escapeHtml(v.vehicle_id) + '">' +
        '<span class="glyph">🚌</span></button>';
    });
    els.depotGrid.innerHTML = html;
  }

  els.depotGrid.addEventListener('click', function (e) {
    var cell = e.target.closest('.bus-cell');
    if (!cell) return;
    document.querySelectorAll('.bus-cell.selected').forEach(function (c) { c.classList.remove('selected'); });
    cell.classList.add('selected');
    showBusDetail(vehicleLookup[cell.dataset.vehicleId]);
  });
  els.busDetailClose.addEventListener('click', function () {
    els.busDetail.hidden = true;
    document.querySelectorAll('.bus-cell.selected').forEach(function (c) { c.classList.remove('selected'); });
  });

  function statusLabel(status) {
    return { active: t(lang, 'legend_active'), signal: t(lang, 'legend_signal'), none: t(lang, 'legend_none') }[status] || status;
  }

  function showBusDetail(v) {
    if (!v) return;
    els.busDetailBody.innerHTML =
      '<dl>' +
      '<dt>' + t(lang, 'bus_number') + '</dt><dd>' + escapeHtml(v.vehicle_id) + '</dd>' +
      '<dt>' + t(lang, 'bus_plate') + '</dt><dd>' + (v.matricule ? escapeHtml(v.matricule) : t(lang, 'bus_plate_missing')) + '</dd>' +
      '<dt>' + t(lang, 'bus_seats') + '</dt><dd>' + escapeHtml(v.capacity) + '</dd>' +
      '<dt>' + t(lang, 'bus_status') + '</dt><dd class="status-' + v.status + '">' + statusLabel(v.status) + '</dd>' +
      '<dt>' + t(lang, 'bus_last_seen') + '</dt><dd>' + (v.last_activity ? escapeHtml(v.last_activity) : t(lang, 'bus_last_seen_missing')) + '</dd>' +
      '</dl>';
    els.busDetail.hidden = false;
  }

  /* ================= routes ================= */
  function renderRoutes(payload) {
    els.routesSub.textContent = payload.routes.length
      ? t(lang, 'routes_sub', { routes: payload.routes.length, buses: payload.summary.available_vehicles })
      : '';
    els.routeList.innerHTML = buildRouteListHtml(payload.routes);
  }

  function sourceBadgeHtml(source) {
    if (!source) return '';
    var cls = source === 'model' ? 'model' : 'average';
    var label = source === 'model' ? t(lang, 'demand_source_model') : t(lang, 'demand_source_average');
    return '<span class="source-badge ' + cls + '">' + label + '</span>';
  }

  function buildRouteListHtml(routes) {
    if (!routes.length) {
      return '<div class="route-empty">' + t(lang, 'routes_empty') + '</div>';
    }
    var maxDemand = Math.max.apply(null, routes.map(function (r) { return r.predicted_demand; }));
    var html = '';
    routes.forEach(function (r) {
      var coveredWidth = Math.min(100, (r.capacity_provided / maxDemand) * 100);
      var demandMarkerPct = Math.min(100, (r.predicted_demand / maxDemand) * 100);
      var pct = Math.round(r.coverage_ratio * 100);
      var pctClass = pct >= 100 ? 'full' : (pct > 0 ? 'partial' : 'none');
      var barClass = pct >= 100 ? '' : 'short';
      html += '<div class="route-row">' +
        '<div class="route-row-head">' +
        '<span><span class="route-path">' + escapeHtml(routeOrigin(r)) + ' → ' + escapeHtml(routeDestination(r)) + '</span> ' +
        '<span class="route-code">#' + escapeHtml(r.route_id) + '</span>' + sourceBadgeHtml(r.demand_source) + '</span>' +
        '<span class="route-nums">' + r.assigned_vehicles + ' ' + t(lang, 'route_buses') +
        ' · <span class="pct ' + pctClass + '">' + pct + '%</span> ' + t(lang, 'route_covered') + '</span>' +
        '</div>' +
        '<div class="route-bar-track"><div class="route-bar-fill ' + barClass + '" style="width:' + coveredWidth + '%"></div>' +
        '<div class="route-bar-marker" style="inset-inline-start:' + demandMarkerPct + '%"></div></div>' +
        '<button type="button" class="timetable-link" data-route-id="' + escapeHtml(r.route_id) +
        '" data-origin="' + escapeHtml(routeOrigin(r)) + '" data-destination="' + escapeHtml(routeDestination(r)) + '">' +
        t(lang, 'timetable_link') + '</button>' +
        '</div>';
    });
    return html;
  }

  /* ================= suggested timetable ================= */
  var timetableEls = {
    panel: document.getElementById('timetable-panel'),
    body: document.getElementById('timetable-body'),
    close: document.getElementById('timetable-close')
  };

  document.addEventListener('click', function (e) {
    var link = e.target.closest('.timetable-link');
    if (!link) return;
    openTimetable(link.dataset.routeId, link.dataset.origin, link.dataset.destination);
  });
  timetableEls.close.addEventListener('click', function () { timetableEls.panel.hidden = true; });

  function openTimetable(routeId, origin, destination) {
    timetableEls.panel.hidden = false;
    timetableEls.body.innerHTML = '<div class="whatif-loading"><span class="whatif-spinner"></span></div>';
    timetableEls.panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    var url = 'timetable.php?company=' + encodeURIComponent(state.company) + '&route_id=' + encodeURIComponent(routeId);
    fetch(url)
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (res) { renderTimetable(res.ok, res.body, origin, destination); })
      .catch(function (err) { renderTimetable(false, { error: err.message }, origin, destination); });
  }

  function renderTimetable(ok, data, origin, destination) {
    if (!ok || data.error) {
      timetableEls.body.innerHTML =
        '<h3>' + t(lang, 'timetable_title', { origin: origin, destination: destination }) + '</h3>' +
        '<p class="whatif-error">' + escapeHtml(data.error || t(lang, 'timetable_unavailable')) + '</p>';
      return;
    }
    var rowsHtml = data.hourly.map(function (h) {
      return '<div class="ttable-row">' +
        '<span class="mono">' + String(h.hour).padStart(2, '0') + ':00</span>' +
        '<span class="mono">' + Math.round(h.predicted_passengers) + '</span>' +
        '<span class="mono">' + h.suggested_departures + '</span>' +
        '<span class="mono">' + h.times.join(', ') + '</span>' +
        '</div>';
    }).join('');

    timetableEls.body.innerHTML =
      '<h3>' + t(lang, 'timetable_title', { origin: origin, destination: destination }) + '</h3>' +
      '<p class="section-sub">' + t(lang, 'timetable_sub', { n: data.ticket_sample_size }) + '</p>' +
      '<div class="ttable-stats">' +
      '<div><span class="ttable-stat-label">' + t(lang, 'timetable_service_span') + '</span>' +
      '<span class="mono">' + String(data.service_start_hour).padStart(2, '0') + ':00–' + String(data.service_end_hour).padStart(2, '0') + ':00</span></div>' +
      '<div><span class="ttable-stat-label">' + t(lang, 'timetable_peak') + '</span>' +
      '<span class="mono">' + String(data.peak_hour).padStart(2, '0') + ':00</span></div>' +
      '<div><span class="ttable-stat-label">' + t(lang, 'timetable_total') + '</span>' +
      '<span class="mono">' + data.total_suggested_departures + '</span></div>' +
      '</div>' +
      '<div class="ttable">' +
      '<div class="ttable-row ttable-head">' +
      '<span>' + t(lang, 'timetable_col_hour') + '</span>' +
      '<span>' + t(lang, 'timetable_col_passengers') + '</span>' +
      '<span>' + t(lang, 'timetable_col_departures') + '</span>' +
      '<span>' + t(lang, 'timetable_col_times') + '</span>' +
      '</div>' + rowsHtml + '</div>' +
      '<p class="explain-note">' + t(lang, 'timetable_caveat') + '</p>';
  }

  /* ================= map ================= */
  var leafletMap = null;
  var markerLayer = null;
  var terminalDivIcon = null;
  var depotDivIcon = null;

  function initMap() {
    // Guarded with typeof, not a bare `L...` reference: if the Leaflet CDN
    // script failed to load, `L` doesn't exist at all, and touching it
    // directly would throw and abort this whole file — taking down the
    // KPIs/depot/routes/language switching with it, not just the map.
    if (typeof L === 'undefined') return;
    leafletMap = L.map('fleet-map', { scrollWheelZoom: false });
    leafletMap.setView([34.6, 9.3], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(leafletMap);
    markerLayer = L.layerGroup().addTo(leafletMap);

    terminalDivIcon = L.divIcon({
      html: '<svg width="18" height="24" viewBox="0 0 18 24" xmlns="http://www.w3.org/2000/svg">' +
        '<path d="M9 24c0-6 8-10 8-16A8 8 0 1 0 1 8c0 6 8 10 8 16Z" fill="#2a78d6"/>' +
        '<circle cx="9" cy="8" r="3.2" fill="#fff"/></svg>',
      className: 'terminal-map-icon', iconSize: [18, 24], iconAnchor: [9, 24], popupAnchor: [0, -20]
    });
    depotDivIcon = L.divIcon({
      html: '<svg width="22" height="22" viewBox="0 0 22 22" xmlns="http://www.w3.org/2000/svg">' +
        '<rect x="2" y="2" width="18" height="18" rx="5" fill="#1a1a18"/>' +
        '<path d="M6 12 L11 7 L16 12 V16 H6 Z" fill="#fff"/></svg>',
      className: 'depot-map-icon', iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -12]
    });
  }

  function busIconHtml(color) {
    return (
      '<svg width="28" height="26" viewBox="0 0 28 26" xmlns="http://www.w3.org/2000/svg">' +
      '<ellipse cx="14" cy="23" rx="9" ry="2" fill="rgba(20,20,15,0.28)"/>' +
      '<path d="M5 9 L9 5 L25 5 L23 9 Z" fill="' + shade(color, -10) + '"/>' +
      '<path d="M22 8 L25 5 L25 15 L23 17 Z" fill="' + shade(color, -28) + '"/>' +
      '<rect x="5" y="9" width="18" height="10" rx="2.4" fill="' + color + '"/>' +
      '<rect x="7" y="10.6" width="14" height="3.6" rx="1" fill="rgba(255,255,255,0.88)"/>' +
      '<circle cx="9.5" cy="20" r="2.1" fill="#1c1c1a"/>' +
      '<circle cx="18.5" cy="20" r="2.1" fill="#1c1c1a"/>' +
      '</svg>'
    );
  }
  function shade(hex, amt) {
    var c = hex.replace('#', '');
    var num = parseInt(c, 16);
    var r = Math.max(0, Math.min(255, (num >> 16) + amt));
    var g = Math.max(0, Math.min(255, ((num >> 8) & 0xff) + amt));
    var b = Math.max(0, Math.min(255, (num & 0xff) + amt));
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }
  var STATUS_COLOR = { active: '#0ca30c', signal: '#b8790a', none: '#8c8b85' };

  function busDivIcon(status) {
    return L.divIcon({
      html: busIconHtml(STATUS_COLOR[status] || STATUS_COLOR.none),
      className: 'bus-map-icon',
      iconSize: [28, 26],
      iconAnchor: [14, 22],
      popupAnchor: [0, -20]
    });
  }
  function renderMap(mapData) {
    if (!leafletMap || !markerLayer) return;
    markerLayer.clearLayers();
    if (!mapData) return;

    var bounds = [];

    (mapData.bus_locations || []).forEach(function (b) {
      var v = vehicleLookup[b.vehicle_id];
      var status = v ? v.status : 'active';
      var marker = L.marker([b.lat, b.lon], { icon: busDivIcon(status) });
      marker.bindPopup(
        '<b>' + t(lang, 'bus_number') + ' ' + escapeHtml(b.vehicle_id) + '</b><br>' +
        t(lang, 'map_popup_near') + ': ' + escapeHtml(b.near || '—') + '<br>' +
        t(lang, 'map_popup_last_seen') + ': ' + escapeHtml(b.last_seen)
      );
      marker.addTo(markerLayer);
      bounds.push([b.lat, b.lon]);
    });

    (mapData.terminals || []).forEach(function (term) {
      var marker = L.marker([term.lat, term.lon], { icon: terminalDivIcon });
      marker.bindPopup('<b>' + escapeHtml(term.name) + '</b><br>' + t(lang, 'map_popup_terminal_label'));
      marker.addTo(markerLayer);
      bounds.push([term.lat, term.lon]);
    });

    if (mapData.depot) {
      var d = mapData.depot;
      var marker = L.marker([d.lat, d.lon], { icon: depotDivIcon });
      marker.bindPopup('<b>' + escapeHtml(d.name) + '</b><br>' + t(lang, 'map_popup_depot_label'));
      marker.addTo(markerLayer);
      bounds.push([d.lat, d.lon]);
    }

    if (bounds.length) {
      leafletMap.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
    }
    setTimeout(function () { leafletMap.invalidateSize(); }, 50);
  }

  /* ================= fetch + wire-up ================= */
  function loadAndRender(company, scenario) {
    var url = 'api.php?company=' + encodeURIComponent(company) + '&scenario=' + encodeURIComponent(scenario);
    fetch(url)
      .then(function (res) {
        if (!res.ok) throw new Error('Server returned ' + res.status);
        return res.json();
      })
      .then(function (payload) {
        if (payload.error) throw new Error(payload.error);
        render(payload);
      })
      .catch(function (err) {
        els.routeList.innerHTML = '<div class="route-empty">' + t(lang, 'error_loading', { err: escapeHtml(err.message) }) + '</div>';
      });
  }

  els.companySelect.addEventListener('change', function () {
    state.company = els.companySelect.value;
    loadAndRender(state.company, state.scenario);
  });

  els.scenarioCards.forEach(function (card) {
    var input = card.querySelector('input');
    card.addEventListener('click', function () {
      els.scenarioCards.forEach(function (c) { c.classList.remove('checked'); });
      card.classList.add('checked');
      input.checked = true;
      state.scenario = input.value;
      loadAndRender(state.company, state.scenario);
    });
  });

  /* ================= what-if live optimizer ================= */
  function syncWhatifRangeToCompany(payload) {
    var cap = Math.max(20, Math.min(200, payload.roster_size));
    els.whatifSlider.max = String(cap);
    var v = Math.min(payload.summary.available_vehicles || 10, cap);
    els.whatifSlider.value = String(v);
    els.whatifValue.textContent = String(v);
    els.whatifResult.hidden = true;
    els.whatifResult.innerHTML = '';
  }

  els.whatifSlider.addEventListener('input', function () {
    els.whatifValue.textContent = els.whatifSlider.value;
  });

  els.whatifRun.addEventListener('click', function () {
    var n = parseInt(els.whatifSlider.value, 10);
    els.whatifRun.disabled = true;
    els.whatifSlider.disabled = true;
    els.whatifResult.hidden = false;
    els.whatifResult.innerHTML =
      '<div class="whatif-loading"><span class="whatif-spinner"></span>' +
      t(lang, 'whatif_calculating', { n: n }) + '</div>';

    var url = 'optimize.php?company=' + encodeURIComponent(state.company) + '&vehicles=' + n;
    var startedAt = Date.now();
    fetch(url)
      .then(function (res) { return res.json().then(function (body) { return { ok: res.ok, body: body }; }); })
      .then(function (res) {
        // A near-instant response still gets a brief, real loading state —
        // long enough to register as "something happened", short enough
        // not to feel laggy. Not simulating work that didn't happen: the
        // subprocess call and OR-Tools solve already took real time; this
        // just keeps very fast responses from looking like a UI glitch.
        var elapsed = Date.now() - startedAt;
        var minDelay = Math.max(0, 350 - elapsed);
        setTimeout(function () { renderWhatifResult(res.ok, res.body, n); }, minDelay);
      })
      .catch(function (err) {
        renderWhatifResult(false, { error: err.message }, n);
      });
  });

  function renderWhatifResult(ok, body, n) {
    els.whatifRun.disabled = false;
    els.whatifSlider.disabled = false;

    if (!ok || body.error) {
      els.whatifResult.innerHTML = '<div class="whatif-error">' + t(lang, 'whatif_error', { err: escapeHtml(body.error || 'unknown') }) + '</div>';
      return;
    }
    var summary = body.summary;
    var html = '<div class="whatif-badge">' + t(lang, 'whatif_badge') + '</div>';
    html += '<div class="kpis" style="margin-bottom:12px">' +
      kpiCardHtml(t(lang, 'kpi_available_label'), fmtInt(summary.available_vehicles), '') +
      kpiCardHtml(t(lang, 'kpi_demand_label'), fmtInt(summary.total_demand), '') +
      kpiCardHtml(t(lang, 'kpi_covered_label'), fmtInt(summary.total_covered), '') +
      kpiCardHtml(t(lang, 'kpi_coverage_label'), Math.round(summary.coverage_pct) + '%',
        summary.total_shortfall > 0 ? t(lang, 'kpi_coverage_short', { n: fmtInt(summary.total_shortfall) }) : t(lang, 'kpi_coverage_full')) +
      '</div>';
    html += '<p class="whatif-note">' + t(lang, 'whatif_result_note', { n: n }) + '</p>';
    html += '<div class="route-list">' + buildRouteListHtml(body.routes) + '</div>';
    els.whatifResult.innerHTML = html;
  }

  function kpiCardHtml(label, value, sub) {
    return '<div class="kpi"><span class="kpi-label">' + label + '</span>' +
      '<span class="kpi-value mono">' + value + '</span>' +
      '<span class="kpi-sub">' + sub + '</span></div>';
  }

  /* ================= devices / fleet overview table ================= */
  function renderDevicesTable() {
    var el = document.getElementById('devices-table');
    if (!el) return;
    var rows = window.__FLEET_OVERVIEW__ || [];
    if (!rows.length) { el.innerHTML = ''; return; }

    var head = '<div class="dtable-row dtable-head">' +
      '<span>' + t(lang, 'devices_table_company') + '</span>' +
      '<span>' + t(lang, 'devices_table_devices') + '</span>' +
      '<span>' + t(lang, 'devices_table_active') + '</span>' +
      '<span>' + t(lang, 'devices_table_coverage_now') + '</span>' +
      '<span>' + t(lang, 'devices_table_investment') + '</span>' +
      '<span>' + t(lang, 'devices_table_coverage_then') + '</span>' +
      '<span>' + t(lang, 'devices_table_story') + '</span>' +
      '</div>';

    var body = rows.map(function (r) {
      var isLimited = r.device_story === 'device_limited';
      var storyLabel = isLimited ? t(lang, 'devices_story_limited') : t(lang, 'devices_story_not_limited');
      var adviceKey = isLimited ? 'devices_row_advice_limited' : 'devices_row_advice_not_limited';
      var advice = t(lang, adviceKey, {
        company: r.company, devices: r.device_count, active: r.active_vehicles,
        coverage_now: r.active_coverage_pct, investment: r.investment_devices, coverage_then: r.investment_coverage_pct
      });
      return '<div class="dtable-row">' +
        '<span class="dtable-company">' + escapeHtml(r.company) + '</span>' +
        '<span class="mono">' + r.device_count + '</span>' +
        '<span class="mono">' + r.active_vehicles + '</span>' +
        '<span class="mono">' + Math.round(r.active_coverage_pct) + '%</span>' +
        '<span class="mono">' + r.investment_devices + '</span>' +
        '<span class="mono">' + Math.round(r.investment_coverage_pct) + '%</span>' +
        '<span><span class="story-pill ' + (isLimited ? 'limited' : '') + '">' + storyLabel + '</span></span>' +
        '<span class="dtable-advice">' + escapeHtml(advice) + '</span>' +
        '</div>';
    }).join('');

    el.innerHTML = head + body;
  }

  /* ================= boot ================= */
  els.langButtons.forEach(function (b) { b.classList.toggle('active', b.dataset.lang === lang); });
  window.I18N.applyStaticTranslations(lang);
  initMap();
  render(window.__INITIAL__);
  renderDevicesTable();
})();
