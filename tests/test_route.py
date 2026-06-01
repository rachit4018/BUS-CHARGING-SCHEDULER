"""
tests/test_route.py
-------------------
Unit tests for RouteCalculator.
Run with: pytest tests/test_route.py -v
"""
import pytest
from scheduler.models import Segment, WorldConfig
from scheduler.route import RouteCalculator

# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def standard_route():
    segments = [
        Segment('Bengaluru', 'A',     100),
        Segment('A',         'B',     120),
        Segment('B',         'C',     100),
        Segment('C',         'D',     120),
        Segment('D',         'Kochi', 100),
    ]
    world = WorldConfig(speed_kmph=60, battery_range_km=240, charge_time_min=25)
    return RouteCalculator(segments, world)

# ── Distance Tests ────────────────────────────────────────────────────

def test_distance_first_segment(standard_route):
    assert standard_route.distance('Bengaluru', 'A') == 100

def test_distance_two_segments(standard_route):
    assert standard_route.distance('Bengaluru', 'B') == 220

def test_distance_full_route(standard_route):
    assert standard_route.distance('Bengaluru', 'Kochi') == 540

def test_distance_middle_segment(standard_route):
    assert standard_route.distance('A', 'D') == 340

def test_distance_is_symmetric(standard_route):
    assert standard_route.distance('B', 'Bengaluru') == standard_route.distance('Bengaluru', 'B')

def test_distance_adjacent(standard_route):
    assert standard_route.distance('C', 'D') == 120

# ── Travel Time Tests ─────────────────────────────────────────────────

def test_travel_time_100km_at_60kmh(standard_route):
    # 100km at 60km/h = 100 minutes
    assert standard_route.travel_time('Bengaluru', 'A') == pytest.approx(100.0)

def test_travel_time_full_route(standard_route):
    # 540km at 60km/h = 540 minutes
    assert standard_route.travel_time('Bengaluru', 'Kochi') == pytest.approx(540.0)

# ── stops_between Tests ───────────────────────────────────────────────

def test_stops_between_full_BK(standard_route):
    stops = standard_route.stops_between('Bengaluru', 'Kochi')
    assert stops == ['A', 'B', 'C', 'D']

def test_stops_between_full_KB(standard_route):
    stops = standard_route.stops_between('Kochi', 'Bengaluru')
    assert stops == ['D', 'C', 'B', 'A']

def test_stops_between_partial(standard_route):
    stops = standard_route.stops_between('A', 'D')
    assert stops == ['B', 'C']

# ── Direction Tests ───────────────────────────────────────────────────

def test_bus_origin_BK(standard_route):
    assert standard_route.bus_origin('BK') == 'Bengaluru'

def test_bus_origin_KB(standard_route):
    assert standard_route.bus_origin('KB') == 'Kochi'

def test_bus_destination_BK(standard_route):
    assert standard_route.bus_destination('BK') == 'Kochi'

def test_bus_destination_KB(standard_route):
    assert standard_route.bus_destination('KB') == 'Bengaluru'

# ── Range Validation Tests ────────────────────────────────────────────

def test_validate_range_valid_plan(standard_route):
    # Bengaluru→A (100km) ✓, A→C (220km) ✓, C→Kochi (220km) ✓
    assert standard_route.validate_range(['Bengaluru','A','C','Kochi'], 240) is True

def test_validate_range_invalid_plan(standard_route):
    # Bengaluru→B = 220km ✓, B→Kochi = 320km ✗
    assert standard_route.validate_range(['Bengaluru','B','Kochi'], 240) is False

def test_validate_range_exact_boundary(standard_route):
    # Bengaluru→B = 220km, under 240 — valid
    assert standard_route.validate_range(['Bengaluru','B','D','Kochi'], 240) is True

# ── Clock Conversion ──────────────────────────────────────────────────

def test_time_to_clock_even_hour(standard_route):
    assert standard_route.time_to_clock(1140) == '19:00'

def test_time_to_clock_with_minutes(standard_route):
    assert standard_route.time_to_clock(1155) == '19:15'

def test_time_to_clock_midnight(standard_route):
    assert standard_route.time_to_clock(0) == '00:00'
