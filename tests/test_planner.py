"""
tests/test_planner.py
---------------------
Unit tests for the charging plan generator.
"""
import pytest
from scheduler.models import Segment, WorldConfig, Bus, Station
from scheduler.route import RouteCalculator
from scheduler.planner import generate_valid_plans, minimum_stops_required

@pytest.fixture
def setup():
    segments = [
        Segment('Bengaluru','A',100), Segment('A','B',120),
        Segment('B','C',100), Segment('C','D',120), Segment('D','Kochi',100),
    ]
    world    = WorldConfig(60, 240, 25)
    route    = RouteCalculator(segments, world)
    stations = [
        Station('A',1,True), Station('B',1,True),
        Station('C',1,True), Station('D',1,True),
    ]
    bk_bus = Bus('bus-BK-01','kpn','BK','19:00',True)
    kb_bus = Bus('bus-KB-01','kpn','KB','19:00',True)
    return route, world, stations, bk_bus, kb_bus

def test_generates_plans_for_BK_bus(setup):
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    assert len(plans) > 0

def test_generates_plans_for_KB_bus(setup):
    route, world, stations, _, kb_bus = setup
    plans = generate_valid_plans(kb_bus, route, stations, world)
    assert len(plans) > 0

def test_plan_AC_is_valid(setup):
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    assert ('A','C') in plans

def test_plan_BD_is_valid(setup):
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    assert ('B','D') in plans

def test_plan_AD_is_invalid(setup):
    """A→D = 340km which exceeds 240km battery."""
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    assert ('A','D') not in plans

def test_single_stop_C_is_invalid(setup):
    """Bengaluru→C = 320km exceeds range."""
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    assert ('C',) not in plans

def test_all_plans_respect_range(setup):
    """Every generated plan must have all legs within battery range."""
    route, world, stations, bk_bus, _ = setup
    plans = generate_valid_plans(bk_bus, route, stations, world)
    for plan in plans:
        checkpoints = ['Bengaluru'] + list(plan) + ['Kochi']
        for i in range(len(checkpoints)-1):
            dist = route.distance(checkpoints[i], checkpoints[i+1])
            assert dist <= world.battery_range_km, f"Plan {plan} has invalid leg {checkpoints[i]}→{checkpoints[i+1]} = {dist}km"

def test_no_plans_when_all_stations_inactive(setup):
    route, world, _, bk_bus, _ = setup
    inactive = [Station('A',1,False), Station('B',1,False), Station('C',1,False), Station('D',1,False)]
    plans = generate_valid_plans(bk_bus, route, inactive, world)
    assert plans == []

def test_minimum_stops_BK(setup):
    route, world, _, bk_bus, _ = setup
    assert minimum_stops_required(bk_bus, route, world) == 2

def test_kb_plans_in_reverse_order(setup):
    """KB bus plans should have stations in D,C,B,A order."""
    route, world, stations, _, kb_bus = setup
    plans = generate_valid_plans(kb_bus, route, stations, world)
    for plan in plans:
        indices = [['D','C','B','A'].index(s) for s in plan]
        assert indices == sorted(indices), f"KB plan {plan} not in reverse order"
