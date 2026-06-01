"""
tests/test_dispatcher.py
------------------------
Integration tests for the full scheduler.
The most critical test: no bus should ever exceed battery range.
Run with: pytest tests/ -v
"""
import glob
import json
import pytest
from pathlib import Path
from scheduler.loader import load_scenario, parse_scenario
from scheduler.dispatcher import run_scheduler
from scheduler.route import RouteCalculator
from scheduler.models import Weights

# ── Path helper — works on any machine ───────────────────────────────
# Resolves to the scenarios/ folder relative to this test file's location
SCENARIOS_DIR = Path(__file__).parent.parent / 'scenarios'
SCENARIO_GLOB = str(SCENARIOS_DIR / '*.json')


def _run(path):
    data = load_scenario(str(path))
    world, segments, stations, buses, weights = parse_scenario(data)
    return (
        run_scheduler(world, segments, stations, buses, weights,
                      data['meta']['scenario_id'], data['meta']['name']),
        world,
        segments,
        stations,
    )


# ── Critical Safety Tests ─────────────────────────────────────────────

@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_no_range_violation(path):
    """CRITICAL: No bus may travel more than battery_range_km between charges."""
    schedule, world, segments, _ = _run(path)
    route = RouteCalculator(segments, world)

    for bs in schedule.bus_schedules:
        origin = route.bus_origin(bs.bus.direction)
        dest   = route.bus_destination(bs.bus.direction)
        points = [origin] + [s.station_id for s in bs.charging_stops] + [dest]
        for i in range(len(points) - 1):
            dist = route.distance(points[i], points[i + 1])
            assert dist <= world.battery_range_km, (
                f"{bs.bus.id}: leg {points[i]}→{points[i+1]} = {dist:.0f}km "
                f"exceeds {world.battery_range_km}km range"
            )


@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_all_buses_scheduled(path):
    """Every active bus must appear in the schedule."""
    data = load_scenario(str(path))
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
    scheduled_ids = {bs.bus.id for bs in schedule.bus_schedules}
    for bus in buses:
        assert bus.id in scheduled_ids, f"{bus.id} missing from schedule"


@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_station_order_consistent(path):
    """Buses at a station must charge one at a time — no charger overlap."""
    schedule, world, segments, stations = _run(path)

    for sid, sq in schedule.station_queues.items():
        events = sorted(sq.events, key=lambda e: e['charge_start'])
        s_obj  = next((s for s in stations if s.id == sid), None)
        num_chargers = s_obj.num_chargers if s_obj else 1
        if num_chargers == 1:
            for i in range(len(events) - 1):
                assert events[i]['depart_min'] <= events[i + 1]['charge_start'] + 0.001, (
                    f"Station {sid}: overlap between "
                    f"{events[i]['bus_id']} and {events[i+1]['bus_id']}"
                )


@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_wait_times_non_negative(path):
    """No bus should have a negative wait time at any station."""
    schedule, _, _, _ = _run(path)
    for bs in schedule.bus_schedules:
        for stop in bs.charging_stops:
            assert stop.wait_min >= 0, (
                f"{bs.bus.id} has negative wait ({stop.wait_min}) at {stop.station_id}"
            )


@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_charging_stops_in_route_order(path):
    """Each bus must visit charging stations in route order — no backtracking."""
    schedule, world, segments, _ = _run(path)
    route = RouteCalculator(segments, world)

    for bs in schedule.bus_schedules:
        origin = route.bus_origin(bs.bus.direction)
        stops  = [s.station_id for s in bs.charging_stops]
        dists  = [route.distance(origin, sid) for sid in stops]
        assert dists == sorted(dists), (
            f"{bs.bus.id}: charging stops not in route order — {stops}"
        )


@pytest.mark.parametrize('path', sorted(glob.glob(SCENARIO_GLOB)))
def test_depart_equals_arrive_plus_wait_plus_charge(path):
    """depart_min must equal arrive_min + wait_min + charge_min for every stop."""
    schedule, _, _, _ = _run(path)
    for bs in schedule.bus_schedules:
        for stop in bs.charging_stops:
            expected = stop.arrive_min + stop.wait_min + stop.charge_min
            assert abs(stop.depart_min - expected) < 0.001, (
                f"{bs.bus.id} at {stop.station_id}: "
                f"depart {stop.depart_min} != arrive+wait+charge {expected}"
            )


# ── Weight Sensitivity Tests ──────────────────────────────────────────

def test_higher_operator_weight_runs_without_error():
    """Changing operator weight must produce a valid schedule."""
    path = SCENARIOS_DIR / 'scenario_4.json'
    with open(path) as f:
        data = json.load(f)

    for op_weight in [1.0, 2.0, 3.0]:
        data['weights']['operator'] = op_weight
        world, segments, stations, buses, weights = parse_scenario(data)
        schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
        assert len(schedule.bus_schedules) == len(buses), (
            f"operator_weight={op_weight}: bus count mismatch"
        )


def test_different_weights_can_produce_different_schedules():
    """operator=1.0 and operator=3.0 should both produce valid schedules."""
    path = SCENARIOS_DIR / 'scenario_4.json'
    with open(path) as f:
        data = json.load(f)

    data['weights']['operator'] = 1.0
    world, segs, sts, buses, wt = parse_scenario(data)
    sch1 = run_scheduler(world, segs, sts, buses, wt, 'test', '')

    data['weights']['operator'] = 3.0
    world, segs, sts, buses, wt = parse_scenario(data)
    sch2 = run_scheduler(world, segs, sts, buses, wt, 'test', '')

    assert len(sch1.bus_schedules) == len(sch2.bus_schedules)


# ── Fleet Management Tests ────────────────────────────────────────────

def test_inactive_bus_excluded():
    """Buses with active=False must not appear in the schedule."""
    path = SCENARIOS_DIR / 'scenario_1.json'
    with open(path) as f:
        data = json.load(f)
    data['buses'][0]['active'] = False
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
    ids = {bs.bus.id for bs in schedule.bus_schedules}
    assert 'bus-BK-01' not in ids


def test_inactive_station_excluded_from_plans():
    """Buses must never be assigned to charge at an inactive station."""
    path = SCENARIOS_DIR / 'scenario_1.json'
    with open(path) as f:
        data = json.load(f)
    # Take station A offline
    data['stations'][0]['active'] = False
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
    for bs in schedule.bus_schedules:
        stop_ids = [s.station_id for s in bs.charging_stops]
        assert 'A' not in stop_ids, (
            f"{bs.bus.id} charged at inactive station A"
        )


def test_schedule_total_time_is_positive():
    """Total network time must be a positive number."""
    path = SCENARIOS_DIR / 'scenario_1.json'
    schedule, _, _, _ = _run(path)
    assert schedule.total_network_time_min > 0


def test_operator_wait_summary_covers_all_operators():
    """operator_wait_summary must include every operator that has buses."""
    path = SCENARIOS_DIR / 'scenario_1.json'
    schedule, _, _, _ = _run(path)
    operators_in_schedule = {bs.bus.operator for bs in schedule.bus_schedules}
    operators_in_summary  = set(schedule.operator_wait_summary.keys())
    assert operators_in_schedule == operators_in_summary
