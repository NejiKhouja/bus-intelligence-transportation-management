<?php
declare(strict_types=1);

require __DIR__ . '/inc/data.php';

header('Content-Type: application/json; charset=utf-8');

$fleetData = load_fleet_data();
$companies = array_keys($fleetData['companies']);
$company = isset($_GET['company']) ? (string) $_GET['company'] : '';
$routeId = isset($_GET['route_id']) ? (string) $_GET['route_id'] : '';

if (!valid_company($fleetData, $company)) {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown company.', 'valid_companies' => $companies], JSON_UNESCAPED_UNICODE);
    exit;
}
if ($routeId === '') {
    http_response_code(400);
    echo json_encode(['error' => 'route_id is required.'], JSON_UNESCAPED_UNICODE);
    exit;
}

$timetables = load_timetable_data();
$timetable = $timetables[$company][$routeId] ?? null;

if ($timetable === null) {
    http_response_code(404);
    echo json_encode([
        'error' => 'No suggested timetable for this route — not enough hourly ticket history to build one confidently.',
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

echo json_encode(array_merge(['company' => $company], $timetable), JSON_UNESCAPED_UNICODE);
