<?php
declare(strict_types=1);

require __DIR__ . '/inc/data.php';

header('Content-Type: application/json; charset=utf-8');

/**
 * Live optimizer bridge: runs the real OR-Tools solver on demand for a
 * fleet size the user picked, instead of looking up one of the 3
 * precomputed scenarios in api.php. This is a genuine subprocess call
 * per request — the calculation actually happens here, not a fake
 * loading animation over a cached answer.
 *
 * PYTHON_EXECUTABLE must point at the conda/venv Python that has
 * pandas/scikit-learn/ortools installed (see web/README.md) — adjust
 * for your machine via the WINICARI_PYTHON env var if it differs.
 */
$pythonExe = getenv('WINICARI_PYTHON') ?: 'C:\\Users\\deadx\\anaconda3\\envs\\bus-intelligence\\python.exe';
$scriptPath = realpath(__DIR__ . '/../../scripts/live_allocate.py');
const TIMEOUT_SECONDS = 20;
const MAX_VEHICLES = 500;

$data = load_fleet_data();
$companies = array_keys($data['companies']);
$company = isset($_GET['company']) ? (string) $_GET['company'] : $companies[0];
$vehiclesRaw = $_GET['vehicles'] ?? null;

if (!valid_company($data, $company)) {
    http_response_code(400);
    echo json_encode(['error' => 'Unknown company.', 'valid_companies' => $companies], JSON_UNESCAPED_UNICODE);
    exit;
}
if (!is_numeric($vehiclesRaw)) {
    http_response_code(400);
    echo json_encode(['error' => 'vehicles must be a number.'], JSON_UNESCAPED_UNICODE);
    exit;
}
$vehicles = (int) $vehiclesRaw;
if ($vehicles < 0 || $vehicles > MAX_VEHICLES) {
    http_response_code(400);
    echo json_encode(['error' => "vehicles must be between 0 and " . MAX_VEHICLES . "."], JSON_UNESCAPED_UNICODE);
    exit;
}
if ($scriptPath === false || !file_exists($pythonExe)) {
    http_response_code(500);
    echo json_encode([
        'error' => 'Live calculation is not configured on this server (Python interpreter or script not found).',
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$requestJson = json_encode(['company' => $company, 'vehicles' => $vehicles], JSON_UNESCAPED_UNICODE);

$descriptors = [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']];
$process = proc_open([$pythonExe, $scriptPath], $descriptors, $pipes, dirname($scriptPath));

if (!is_resource($process)) {
    http_response_code(500);
    echo json_encode(['error' => 'Could not start the calculation process.'], JSON_UNESCAPED_UNICODE);
    exit;
}

fwrite($pipes[0], $requestJson);
fclose($pipes[0]);
stream_set_blocking($pipes[1], false);
stream_set_blocking($pipes[2], false);

$stdout = '';
$stderr = '';
$start = microtime(true);
$timedOut = false;
while (true) {
    $status = proc_get_status($process);
    $stdout .= stream_get_contents($pipes[1]);
    $stderr .= stream_get_contents($pipes[2]);
    if (!$status['running']) {
        break;
    }
    if (microtime(true) - $start > TIMEOUT_SECONDS) {
        proc_terminate($process);
        $timedOut = true;
        break;
    }
    usleep(50000);
}
fclose($pipes[1]);
fclose($pipes[2]);
$exitCode = proc_close($process);

if ($timedOut) {
    http_response_code(504);
    echo json_encode(['error' => 'Calculation timed out.'], JSON_UNESCAPED_UNICODE);
    exit;
}
if ($exitCode !== 0) {
    http_response_code(500);
    echo json_encode(['error' => 'Calculation failed.', 'detail' => trim($stderr) ?: trim($stdout)], JSON_UNESCAPED_UNICODE);
    exit;
}

$result = json_decode($stdout, true);
if ($result === null) {
    http_response_code(500);
    echo json_encode(['error' => 'Calculation returned invalid data.'], JSON_UNESCAPED_UNICODE);
    exit;
}
if (isset($result['error'])) {
    http_response_code(400);
    echo json_encode($result, JSON_UNESCAPED_UNICODE);
    exit;
}

echo json_encode(array_merge(['company' => $company, 'live' => true], $result), JSON_UNESCAPED_UNICODE);
