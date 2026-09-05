<?php
declare(strict_types=1);

require __DIR__ . '/inc/data.php';

header('Content-Type: application/json; charset=utf-8');

try {
    $data = load_fleet_data();
} catch (RuntimeException $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Could not load fleet data on the server.'], JSON_UNESCAPED_UNICODE);
    exit;
}

$companies = array_keys($data['companies']);
$company = isset($_GET['company']) ? (string) $_GET['company'] : $companies[0];
$scenario = isset($_GET['scenario']) ? (string) $_GET['scenario'] : 'active';

if (!valid_company($data, $company)) {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown company.', 'valid_companies' => $companies], JSON_UNESCAPED_UNICODE);
    exit;
}
if (!valid_scenario($scenario)) {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown scenario.', 'valid_scenarios' => VALID_SCENARIOS], JSON_UNESCAPED_UNICODE);
    exit;
}

$companyData = $data['companies'][$company];
$scenarioData = $companyData['scenarios'][$scenario];
$includedIds = included_vehicle_ids($companyData['vehicles'], $scenario);

// json_decode(..., true) silently turns numeric-string object keys like
// "220" into PHP integer array keys — array_keys() would then return int
// 220, not string "220", and a strict in_array() against route_id (a
// string) would always fail. Cast explicitly rather than rely on loose
// comparison.
$timetableRouteIds = array_map('strval', array_keys(load_timetable_data()[$company] ?? []));
$routesWithTimetableFlag = array_map(static function (array $r) use ($timetableRouteIds) {
    $r['has_timetable'] = in_array((string) $r['route_id'], $timetableRouteIds, true);
    return $r;
}, $scenarioData['routes']);

echo json_encode([
    'company' => $company,
    'company_full_name' => $companyData['full_name'] ?? $company,
    'company_full_name_ar' => $companyData['full_name_ar'] ?? $company,
    'scenario' => $scenario,
    'roster_size' => $companyData['roster_size'],
    'vehicles' => $companyData['vehicles'],
    'included_vehicle_ids' => $includedIds,
    'summary' => [
        'available_vehicles' => $scenarioData['available_vehicles'],
        'avg_capacity' => $scenarioData['avg_capacity'],
        'total_demand' => $scenarioData['total_demand'],
        'total_covered' => $scenarioData['total_covered'],
        'coverage_pct' => $scenarioData['coverage_pct'],
        'total_shortfall' => $scenarioData['total_shortfall'],
    ],
    'routes' => $routesWithTimetableFlag,
    'map' => map_layer_for_scenario($companyData, $includedIds),
    'insights' => $companyData['insights'] ?? [],
], JSON_UNESCAPED_UNICODE);
