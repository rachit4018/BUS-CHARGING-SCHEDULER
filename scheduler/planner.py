"""
scheduler/planner.py
--------------------
Generates ALL valid charging plans for a given bus.

A charging plan is a tuple of station IDs the bus will charge at,
in travel order. A plan is VALID if and only if no gap between
consecutive checkpoints (origin → s1 → s2 → ... → destination)
exceeds the battery range.

The planner does NOT choose which plan to use — that is the
dispatcher's job. The planner just enumerates all valid options,
giving the dispatcher full freedom to optimise.
"""
from itertools import combinations
from typing import List, Tuple
from scheduler.models import Bus, Station, WorldConfig
from scheduler.route import RouteCalculator


# Type alias: a charging plan is a tuple of station ID strings
Plan = Tuple[str, ...]


def generate_valid_plans(
    bus: Bus,
    route: RouteCalculator,
    stations: List[Station],
    world: WorldConfig,
) -> List[Plan]:
    """
    Return all valid charging station combinations for a bus.

    Args:
        bus:      The bus to plan for (direction determines route).
        route:    RouteCalculator for distance lookups.
        stations: All stations (active and inactive mixed).
        world:    WorldConfig with battery_range_km.

    Returns:
        List of valid plans, each a tuple of station IDs in travel order.
        Empty list means no valid plan exists — this is an error condition
        the dispatcher must handle (e.g. station outage makes trip impossible).

    Example:
        >>> plans = generate_valid_plans(bus_bk01, route, stations, world)
        >>> print(plans)
        [('A', 'C'), ('A', 'D'), ('B', 'D'), ('A', 'B', 'C'), ...]
    """
    origin = route.bus_origin(bus.direction)
    dest   = route.bus_destination(bus.direction)

    # Only active stations that lie on this bus's path, in travel order
    all_intermediate = route.stops_between(origin, dest)
    active_ids       = {s.id for s in stations if s.active}
    available        = [s for s in all_intermediate if s in active_ids]

    valid_plans: List[Plan] = []

    # Try all combinations of 1, 2, 3, ... stations
    # Minimum 1 stop (though range math will usually require 2+)
    for r in range(1, len(available) + 1):
        for combo in combinations(available, r):
            # combo is already in route order because available is ordered
            checkpoints = [origin] + list(combo) + [dest]
            if route.validate_range(checkpoints, world.battery_range_km):
                valid_plans.append(combo)

    return valid_plans


def minimum_stops_required(
    bus: Bus,
    route: RouteCalculator,
    world: WorldConfig,
) -> int:
    """
    Calculate the theoretical minimum number of charging stops required.

    This is a pure math calculation — does not account for station availability.
    Useful for validation and UI display.

    Args:
        bus:   The bus (for direction).
        route: RouteCalculator for distance.
        world: WorldConfig for battery_range_km.

    Returns:
        Minimum number of charging stops (integer, always >= 1 for this route).

    Example:
        >>> minimum_stops_required(bk_bus, route, world)
        2  # 540km trip / 240km battery needs at least 2 stops
    """
    import math
    origin = route.bus_origin(bus.direction)
    dest   = route.bus_destination(bus.direction)
    total_dist = route.distance(origin, dest)
    # Ceil of (total / range) - 1 gives minimum intermediate stops
    return math.ceil(total_dist / world.battery_range_km) - 1


def explain_plan(
    plan: Plan,
    bus: Bus,
    route: RouteCalculator,
    world: WorldConfig,
) -> List[dict]:
    """
    Return a human-readable breakdown of each leg in a charging plan.

    Args:
        plan:  A valid charging plan tuple.
        bus:   The bus following this plan.
        route: RouteCalculator.
        world: WorldConfig.

    Returns:
        List of dicts with keys: from, to, distance_km, valid.
    """
    origin = route.bus_origin(bus.direction)
    dest   = route.bus_destination(bus.direction)
    checkpoints = [origin] + list(plan) + [dest]
    legs = []
    for i in range(len(checkpoints) - 1):
        dist = route.distance(checkpoints[i], checkpoints[i + 1])
        legs.append({
            'from': checkpoints[i],
            'to':   checkpoints[i + 1],
            'distance_km': dist,
            'valid': dist <= world.battery_range_km,
        })
    return legs
