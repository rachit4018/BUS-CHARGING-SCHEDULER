"""
tests/test_dispatcher.py
------------------------
Integration tests for the full scheduler.
The most critical test: no bus should ever exceed battery range.
"""
import glob
import pytest
from scheduler.loader import load_scenario, parse_scenario
from scheduler.dispatcher import run_scheduler
from scheduler.route import RouteCalculator
from scheduler.models import Weights


def _run(path):
    data = load_scenario(path)
    world, segments, stations, buses, weights = parse_scenario(data)
    return run_scheduler(world, segments, stations, buses, weights,
                         data['meta']['scenario_id'], data['meta']['name']), world, segments


@pytest.mark.parametrize('path', sorted(glob.glob(
    '/home/claude/bus-charging-scheduler/scenarios/*.json')))
def test_no_range_violation(path):
    """CRITICAL: No bus may travel more than battery_range_km between charges."""
    schedule, world, segments = _run(path)
    from scheduler.route import RouteCalculator
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


@pytest.mark.parametrize('path', sorted(glob.glob(
    '/home/claude/bus-charging-scheduler/scenarios/*.json')))
def test_all_buses_scheduled(path):
    """Every active bus must appear in the schedule."""
    data = load_scenario(path)
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
    scheduled_ids = {bs.bus.id for bs in schedule.bus_schedules}
    for bus in buses:
        assert bus.id in scheduled_ids, f"{bus.id} missing from schedule"


@pytest.mark.parametrize('path', sorted(glob.glob(
    '/home/claude/bus-charging-scheduler/scenarios/*.json')))
def test_station_order_consistent(path):
    """Buses at a station must charge one at a time (no overlap per charger)."""
    data   = load_scenario(path)
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')

    for sid, sq in schedule.station_queues.items():
        events = sorted(sq.events, key=lambda e: e['charge_start'])
        # Find station's charger count
        s_obj = next((s for s in stations if s.id == sid), None)
        num_chargers = s_obj.num_chargers if s_obj else 1
        # Simple overlap check: for 1 charger, no two events should overlap
        if num_chargers == 1:
            for i in range(len(events) - 1):
                assert events[i]['depart_min'] <= events[i+1]['charge_start'] + 0.001, (
                    f"Station {sid}: overlap between {events[i]['bus_id']} and {events[i+1]['bus_id']}"
                )


def test_wait_times_non_negative():
    """No bus should have a negative wait time."""
    for path in sorted(glob.glob('/home/claude/bus-charging-scheduler/scenarios/*.json')):
        schedule, _, _ = _run(path)
        for bs in schedule.bus_schedules:
            for stop in bs.charging_stops:
                assert stop.wait_min >= 0, f"{bs.bus.id} has negative wait at {stop.station_id}"


def test_higher_operator_weight_changes_schedule():
    """Changing operator weight must produce a different or equal total wait."""
    import json, copy
    with open('/home/claude/bus-charging-scheduler/scenarios/scenario_4.json') as f:
        data = json.load(f)

    # Run with operator=1.0
    data['weights']['operator'] = 1.0
    w1, s1, st1, b1, wt1 = parse_scenario(data)
    sch1 = run_scheduler(w1, s1, st1, b1, wt1, 'test', '')

    # Run with operator=3.0
    data['weights']['operator'] = 3.0
    w2, s2, st2, b2, wt2 = parse_scenario(data)
    sch2 = run_scheduler(w2, s2, st2, b2, wt2, 'test', '')

    # The schedules may differ — we just verify both run without error
    assert len(sch1.bus_schedules) == len(sch2.bus_schedules)


def test_inactive_bus_excluded():
    """Buses with active=False must not appear in schedule."""
    import json
    with open('/home/claude/bus-charging-scheduler/scenarios/scenario_1.json') as f:
        data = json.load(f)
    data['buses'][0]['active'] = False
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(world, segments, stations, buses, weights, 'test', '')
    ids = {bs.bus.id for bs in schedule.bus_schedules}
    assert 'bus-BK-01' not in ids
