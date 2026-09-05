<?php
declare(strict_types=1);

const VALID_SCENARIOS = ['active', 'signal', 'roster'];

/**
 * Loads the pre-computed fleet/allocation snapshot produced by the Python
 * pipeline (scripts/build_demo_payload.py -> data/processed/demo_payload.json,
 * copied here as web/data/fleet_data.json). This PHP layer only reads and
 * serves that trusted, already-cleaned snapshot — it does not connect to
 * MongoDB directly, so it never has to re-solve the data-quality problems
 * (operator aliases, sentinel vehicle codes, etc.) already handled upstream.
 */
function load_fleet_data(): array
{
    static $data = null;
    if ($data === null) {
        $path = __DIR__ . '/../../data/fleet_data.json';
        $raw = file_get_contents($path);
        if ($raw === false) {
            throw new RuntimeException("Fleet data file not found at $path");
        }
        $decoded = json_decode($raw, true);
        if (!is_array($decoded)) {
            throw new RuntimeException('Fleet data file is not valid JSON.');
        }
        $data = $decoded;
    }
    return $data;
}

/**
 * Suggested departure timetable per route (scripts/build_timetable.py) —
 * real hourly ticket-sale patterns applied to each route's predicted
 * demand, turned into clock-time departure suggestions. Missing entries
 * (some routes never generated one — too little hourly history) are a
 * real absence, not an error; the caller should treat a missing route
 * as "not enough data for a timetable" rather than retry.
 */
function load_timetable_data(): array
{
    static $data = null;
    if ($data === null) {
        $path = __DIR__ . '/../../data/timetable_data.json';
        $raw = file_get_contents($path);
        $data = $raw === false ? [] : (json_decode($raw, true) ?? []);
    }
    return $data;
}

function valid_company(array $data, string $company): bool
{
    return isset($data['companies'][$company]);
}

function valid_scenario(string $scenario): bool
{
    return in_array($scenario, VALID_SCENARIOS, true);
}

/** Vehicle ids counted as "available" under a scenario, computed once here
 * so the frontend never has to re-implement this business rule in JS. */
function included_vehicle_ids(array $vehicles, string $scenario): array
{
    $ids = array_values(array_map(
        static fn(array $v) => $v['vehicle_id'],
        array_filter($vehicles, static function (array $v) use ($scenario): bool {
            if ($scenario === 'roster') return true;
            if ($scenario === 'signal') return in_array($v['status'], ['active', 'signal'], true);
            return $v['status'] === 'active';
        })
    ));
    return $ids;
}

/** Map layer for a company, with bus locations narrowed to whichever
 * vehicles are actually counted under the selected scenario — a bus
 * location only exists for vehicles with a resolvable last trip (58 of
 * ~250 across all 4 companies), a strictly smaller set than any
 * scenario's fleet count, so this is always a subset, never padded. */
function map_layer_for_scenario(array $companyData, array $includedIds): array
{
    $map = $companyData['map'] ?? ['bus_locations' => [], 'terminals' => [], 'depot' => null];
    $includedSet = array_flip($includedIds);
    $map['bus_locations'] = array_values(array_filter(
        $map['bus_locations'],
        static fn(array $b) => isset($includedSet[$b['vehicle_id']])
    ));
    return $map;
}
