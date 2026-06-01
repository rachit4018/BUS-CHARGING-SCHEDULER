"""
scheduler/dispatcher.py
-----------------------
Event-driven bus charging scheduler.

Architecture:
  1. Sort buses by departure time (chronological order).
  2. For each bus, generate all valid charging plans (planner.py).
  3. Score each plan using the cost function (individual + operator + overall).
  4. Assign the lowest-cost plan to the bus.
  5. Simulate the bus following that plan — compute exact timestamps.
  6. Update charger availability so the next bus sees accurate wait times.
  7. Repeat until all buses are scheduled.

The scheduler is a PURE FUNCTION:
  - Takes scenario data, returns a Schedule object.
  - No side effects, no global state.
  - Calling it twice with the same input produces the same output.
  - This makes reactive rescheduling trivial: inject new events, call again.

Cost function weights come from the scenario JSON — never hardcoded here.
Adding a new cost component = one new function + one line in _plan_cost().
"""
from collections import defaultdict
from typing import List, Dict, Tuple
from scheduler.models import (
    WorldConfig, Segment, Station, Bus, Weights,
    ChargingStop, BusSchedule, StationQueue, Schedule,
)
from scheduler.route import RouteCalculator
from scheduler.planner import generate_valid_plans, Plan


# ── Public Entry Point ────────────────────────────────────────────────

def run_scheduler(
    world:       WorldConfig,
    segments:    List[Segment],
    stations:    List[Station],
    buses:       List[Bus],
    weights:     Weights,
    scenario_id: str,
    scenario_name: str = '',
) -> Schedule:
    """
    Run the complete scheduling simulation for one scenario.

    Args:
        world:         Physical constants (speed, range, charge time).
        segments:      Ordered route segments.
        stations:      All stations (active and inactive).
        buses:         All active buses to schedule.
        weights:       Cost function weights (individual, operator, overall).
        scenario_id:   Identifier for this scenario.
        scenario_name: Human-readable name for display.

    Returns:
        Schedule object containing per-bus timelines and per-station queues.

    Raises:
        ValueError: If any bus has no valid charging plan (impossible trip).
    """
    route = RouteCalculator(segments, world)

    # charger_free[station_id] = list of free-at times, one per charger
    # e.g. station A with 2 chargers: [0.0, 0.0] means both free at t=0
    charger_free: Dict[str, List[float]] = {
        s.id: [0.0] * s.num_chargers
        for s in stations if s.active
    }

    # Track per-operator wait times for cost function
    op_waits: Dict[str, List[float]] = defaultdict(list)

    bus_schedules: List[BusSchedule] = []
    station_queues: Dict[str, StationQueue] = {
        s.id: StationQueue(s.id) for s in stations if s.active
    }

    # Process buses in chronological departure order
    sorted_buses = sorted(buses, key=lambda b: _parse_time(b.departure))

    for bus in sorted_buses:
        plans = generate_valid_plans(bus, route, stations, world)

        if not plans:
            raise ValueError(
                f"No valid charging plan for {bus.id} — "
                f"check station coverage (all stations may be inactive or too far apart)."
            )

        # Score every valid plan and pick the lowest-cost one
        best_plan = min(
            plans,
            key=lambda p: _plan_cost(p, bus, route, world, charger_free, op_waits, weights)
        )

        # Simulate this bus following the chosen plan
        bs = _simulate_bus(bus, best_plan, route, world, charger_free, station_queues)
        op_waits[bus.operator].append(bs.total_wait_min)
        bus_schedules.append(bs)

    total_time = max(bs.arrive_min for bs in bus_schedules) if bus_schedules else 0.0

    return Schedule(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        bus_schedules=bus_schedules,
        station_queues=station_queues,
        total_network_time_min=total_time,
        weights_used=weights,
    )


# ── Cost Function ─────────────────────────────────────────────────────

def _plan_cost(
    plan:         Plan,
    bus:          Bus,
    route:        RouteCalculator,
    world:        WorldConfig,
    charger_free: Dict[str, List[float]],
    op_waits:     Dict[str, List[float]],
    weights:      Weights,
) -> float:
    """
    Compute the cost of assigning 'plan' to 'bus' given current sim state.

    Lower cost = better plan. The scheduler picks the minimum.

    Cost components:
      1. individual  — predicted wait time for this bus across all stops
      2. operator    — how much this worsens the operator's average wait
      3. overall     — predicted contribution to total network time

    To add a new cost component:
      1. Write a new _cost_XXX() function below.
      2. Add: + weights.new_weight * _cost_XXX(...)  to the return below.
      3. Add 'new_weight' to the scenario JSON weights section.
      No other changes needed.
    """
    individual_cost = _cost_individual(plan, bus, route, world, charger_free)
    operator_cost   = _cost_operator(individual_cost, bus, op_waits)
    overall_cost    = _cost_overall(plan, bus, route, world, charger_free)

    return (
        weights.individual * individual_cost +
        weights.operator   * operator_cost   +
        weights.overall    * overall_cost
    )


def _cost_individual(plan, bus, route, world, charger_free) -> float:
    """
    Predict the total wait time for this bus following this plan.
    Uses a dry-run simulation — does NOT mutate charger_free.
    """
    origin = route.bus_origin(bus.direction)
    current_time = _parse_time(bus.departure)
    current_loc  = origin
    total_wait   = 0.0

    # Snapshot charger state for dry-run
    cf_snapshot = {sid: list(times) for sid, times in charger_free.items()}

    for station_id in plan:
        if station_id not in cf_snapshot:
            continue  # inactive station — should not appear in valid plans
        travel   = route.travel_time(current_loc, station_id)
        arrive   = current_time + travel
        free_at  = min(cf_snapshot[station_id])
        wait     = max(0.0, free_at - arrive)
        total_wait  += wait
        charge_end   = arrive + wait + world.charge_time_min
        # Update snapshot
        idx = cf_snapshot[station_id].index(min(cf_snapshot[station_id]))
        cf_snapshot[station_id][idx] = charge_end
        current_time = charge_end
        current_loc  = station_id

    return total_wait


def _cost_operator(individual_cost, bus, op_waits) -> float:
    """
    Penalise plans that worsen operator-level fairness.
    Computes how much this bus's predicted wait exceeds its operator's current average.
    """
    existing = op_waits.get(bus.operator, [])
    if not existing:
        return individual_cost  # first bus from this operator — no comparison yet
    current_avg = sum(existing) / len(existing)
    return max(0.0, individual_cost - current_avg)


def _cost_overall(plan, bus, route, world, charger_free) -> float:
    """
    Estimate this bus's contribution to total network completion time.
    Approximated as predicted arrival time at destination.
    """
    origin = route.bus_origin(bus.direction)
    dest   = route.bus_destination(bus.direction)
    current_time = _parse_time(bus.departure)
    current_loc  = origin
    cf_snapshot  = {sid: list(t) for sid, t in charger_free.items()}

    for station_id in plan:
        if station_id not in cf_snapshot:
            continue
        travel   = route.travel_time(current_loc, station_id)
        arrive   = current_time + travel
        free_at  = min(cf_snapshot[station_id])
        wait     = max(0.0, free_at - arrive)
        charge_end = arrive + wait + world.charge_time_min
        idx = cf_snapshot[station_id].index(min(cf_snapshot[station_id]))
        cf_snapshot[station_id][idx] = charge_end
        current_time = charge_end
        current_loc  = station_id

    final_travel = route.travel_time(current_loc, dest)
    return current_time + final_travel


# ── Bus Simulation ────────────────────────────────────────────────────

def _simulate_bus(
    bus:            Bus,
    plan:           Plan,
    route:          RouteCalculator,
    world:          WorldConfig,
    charger_free:   Dict[str, List[float]],
    station_queues: Dict[str, StationQueue],
) -> BusSchedule:
    """
    Simulate one bus following its assigned plan.
    MUTATES charger_free — marks chargers as occupied.
    Records all charging events in station_queues.
    """
    origin       = route.bus_origin(bus.direction)
    dest         = route.bus_destination(bus.direction)
    current_time = _parse_time(bus.departure)
    current_loc  = origin
    stops: List[ChargingStop] = []

    for station_id in plan:
        travel     = route.travel_time(current_loc, station_id)
        arrive     = current_time + travel
        free_at    = min(charger_free[station_id])
        wait       = max(0.0, free_at - arrive)
        charge_end = arrive + wait + world.charge_time_min

        # Lock the charger that was freed earliest
        idx = charger_free[station_id].index(min(charger_free[station_id]))
        charger_free[station_id][idx] = charge_end

        stop = ChargingStop(
            station_id = station_id,
            arrive_min = arrive,
            wait_min   = wait,
            charge_min = world.charge_time_min,
            depart_min = charge_end,
        )
        stops.append(stop)

        # Log in station queue
        station_queues[station_id].events.append({
            'bus_id':       bus.id,
            'operator':     bus.operator,
            'arrive_min':   arrive,
            'wait_min':     wait,
            'charge_start': arrive + wait,
            'depart_min':   charge_end,
        })

        current_time = charge_end
        current_loc  = station_id

    final_travel = route.travel_time(current_loc, dest)
    arrive_dest  = current_time + final_travel
    total_wait   = sum(s.wait_min for s in stops)

    return BusSchedule(
        bus            = bus,
        charging_stops = stops,
        depart_min     = _parse_time(bus.departure),
        arrive_min     = arrive_dest,
        total_wait_min = total_wait,
    )


# ── Helpers ───────────────────────────────────────────────────────────

def _parse_time(time_str: str) -> float:
    """Convert 'HH:MM' clock string to minutes from midnight."""
    h, m = map(int, time_str.split(':'))
    return float(h * 60 + m)


def _cost_station_load(
    plan, bus, route, world, charger_free
) -> float:
    """
    Penalise plans that send this bus to an already-congested station.
    Looks at how many buses are already queued at each station in the plan
    and adds a penalty proportional to that queue length.
    """
    penalty = 0.0
    origin       = route.bus_origin(bus.direction)
    current_loc  = origin
    current_time = _parse_time(bus.departure)
    cf_snapshot  = {sid: list(t) for sid, t in charger_free.items()}

    for station_id in plan:
        if station_id not in cf_snapshot:
            continue
        travel  = route.travel_time(current_loc, station_id)
        arrive  = current_time + travel
        free_at = min(cf_snapshot[station_id])

        # How many charger slots are busy when this bus arrives?
        busy_slots = sum(1 for t in cf_snapshot[station_id] if t > arrive)
        total_slots = len(cf_snapshot[station_id])

        # Congestion ratio — 0.0 means station is free, 1.0 means all chargers busy
        congestion = busy_slots / total_slots
        penalty += congestion * 20  # 20 min equivalent penalty per busy slot

        wait       = max(0.0, free_at - arrive)
        charge_end = arrive + wait + world.charge_time_min
        idx        = cf_snapshot[station_id].index(min(cf_snapshot[station_id]))
        cf_snapshot[station_id][idx] = charge_end
        current_time = charge_end
        current_loc  = station_id

    return penalty