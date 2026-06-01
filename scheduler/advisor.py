"""
scheduler/advisor.py
--------------------
Two responsibilities:

1. STATION LOAD ANALYSER
   After the schedule is computed, analyses whether buses were
   distributed well across stations or if one station got overloaded
   while another was underutilised.

2. DRIVER ADVISORY GENERATOR
   For each bus, generates advisory messages at the point 10km
   before each station it passes through — telling the driver:
   - STOP HERE   → charge at this station
   - SKIP AHEAD  → this station is busy, go to next one
   - HEADS UP    → charging at next station, this one is free but not needed

These advisories simulate what a real-time dispatch system would
send to a driver's dashboard 10km before each station.
"""

from typing import List, Dict, Tuple
from scheduler.models import Schedule, BusSchedule, ChargingStop, Station
from scheduler.route import RouteCalculator


# ── Station Load Analysis ─────────────────────────────────────────────

def analyse_station_load(
    schedule: Schedule,
    stations: List[Station],
    route: RouteCalculator,
) -> Dict[str, dict]:
    """
    Analyse how load is distributed across stations.

    For each station returns:
      - total_buses:     how many buses charged there
      - total_wait:      sum of all wait times at this station
      - avg_wait:        average wait per bus
      - max_wait:        worst single wait
      - peak_window:     busiest 60-minute window
      - utilisation_pct: what % of available charging slots were contended
      - verdict:         'well_used' | 'overloaded' | 'underutilised' | 'unused'
      - suggestion:      human-readable explanation

    Args:
        schedule: Completed schedule from run_scheduler().
        stations: List of Station objects.
        route:    RouteCalculator (for context).

    Returns:
        Dict keyed by station_id.
    """
    results = {}

    for station in stations:
        if not station.active:
            results[station.id] = {
                'total_buses': 0, 'total_wait': 0, 'avg_wait': 0,
                'max_wait': 0, 'peak_window': None,
                'utilisation_pct': 0, 'verdict': 'offline',
                'suggestion': 'Station is inactive.',
            }
            continue

        sq = schedule.station_queues.get(station.id)
        events = sq.events if sq else []

        if not events:
            results[station.id] = {
                'total_buses': 0, 'total_wait': 0, 'avg_wait': 0,
                'max_wait': 0, 'peak_window': None,
                'utilisation_pct': 0, 'verdict': 'unused',
                'suggestion': 'No buses charged here. Consider whether this station is reachable given current route and battery range.',
            }
            continue

        total_buses   = len(events)
        total_wait    = sum(e['wait_min'] for e in events)
        avg_wait      = total_wait / total_buses
        max_wait      = max(e['wait_min'] for e in events)
        contended     = sum(1 for e in events if e['wait_min'] > 0)
        utilisation   = round(contended / total_buses * 100)

        # Find busiest 60-min window
        peak_window = _find_peak_window(events, window_min=60)

        # Verdict
        if avg_wait > 30:
            verdict    = 'overloaded'
            suggestion = (
                f"Station {station.id} is overloaded — average wait {avg_wait:.0f} min. "
                f"Consider adding a charger (num_chargers: {station.num_chargers + 1}) "
                f"or redistributing buses to neighbouring stations via weight tuning."
            )
        elif avg_wait > 10:
            verdict    = 'congested'
            suggestion = (
                f"Station {station.id} is congested — average wait {avg_wait:.0f} min. "
                f"Increasing the individual weight may steer some buses to less-busy stations."
            )
        elif total_buses < 2:
            verdict    = 'underutilised'
            suggestion = (
                f"Station {station.id} handled only {total_buses} bus(es). "
                f"It may be too close or too far from other stations for most valid plans to use it."
            )
        else:
            verdict    = 'well_used'
            suggestion = f"Station {station.id} is well utilised with avg wait {avg_wait:.0f} min."

        results[station.id] = {
            'total_buses':      total_buses,
            'total_wait':       round(total_wait, 1),
            'avg_wait':         round(avg_wait, 1),
            'max_wait':         round(max_wait, 1),
            'contended_buses':  contended,
            'utilisation_pct':  utilisation,
            'peak_window':      peak_window,
            'verdict':          verdict,
            'suggestion':       suggestion,
        }

    return results


def _find_peak_window(events: list, window_min: int = 60) -> dict:
    """Find the 60-minute window with the most simultaneous charging activity."""
    if not events:
        return None
    times = sorted(e['charge_start'] for e in events)
    best_start = times[0]
    best_count = 1
    for t in times:
        window_end = t + window_min
        count = sum(1 for e in events
                    if e['charge_start'] >= t and e['charge_start'] < window_end)
        if count > best_count:
            best_count = count
            best_start = t
    h = int(best_start) // 60
    m = int(best_start) % 60
    return {'start': f"{h:02d}:{m:02d}", 'bus_count': best_count}


# ── Driver Advisory Generator ─────────────────────────────────────────

def generate_driver_advisories(
    schedule:      Schedule,
    stations:      List[Station],
    route:         RouteCalculator,
    advisory_km:   float = 10.0,
) -> Dict[str, List[dict]]:
    """
    Generate advisory messages sent to each driver 10km before
    every station they pass through on their route.

    The advisory tells the driver:
      STOP HERE   → you are scheduled to charge here, charger will be free
      STOP + WAIT → you are scheduled here but expect a wait
      SKIP AHEAD  → charger busy, you have enough range, go to next station
      HEADS UP    → you pass this station but are not scheduled to charge here

    Args:
        schedule:    Completed schedule.
        stations:    All stations.
        route:       RouteCalculator.
        advisory_km: Distance before station to send advisory (default 10km).

    Returns:
        Dict keyed by bus_id, each value is a list of advisory dicts.
        Each advisory dict has:
          station_id, advisory_time_min, advisory_clock,
          action, message, range_remaining_km
    """
    advisories: Dict[str, List[dict]] = {}
    active_station_ids = {s.id for s in stations if s.active}

    for bs in schedule.bus_schedules:
        bus         = bs.bus
        origin      = route.bus_origin(bus.direction)
        dest        = route.bus_destination(bus.direction)
        all_stops   = route.stops_between(origin, dest)
        charge_ids  = {stop.station_id for stop in bs.charging_stops}
        bus_advisories = []

        # Track range remaining as bus travels
        # Starts full (battery_range_km), decremented by each leg
        # Recharged to full at each charging stop
        # We approximate range_remaining from the schedule timestamps

        for station_id in all_stops:
            if station_id not in active_station_ids:
                continue

            # Distance from origin to this station
            dist_to_station = route.distance(origin, station_id)
            # Distance from origin to advisory point (10km before station)
            dist_to_advisory = dist_to_station - advisory_km
            if dist_to_advisory < 0:
                dist_to_advisory = 0

            # Time bus reaches advisory point
            advisory_time = bs.depart_min + (dist_to_advisory / route.world.speed_kmph * 60)

            # Adjust for charging stops already done before this station
            extra_time = sum(
                (stop.wait_min + stop.charge_min)
                for stop in bs.charging_stops
                if route.distance(origin, stop.station_id) < dist_to_station
            )
            advisory_time += extra_time

            # Determine range remaining at advisory point
            # Find last charge point before this station
            last_charge_dist = 0.0
            for stop in bs.charging_stops:
                d = route.distance(origin, stop.station_id)
                if d < dist_to_station:
                    last_charge_dist = d
            range_remaining = route.world.battery_range_km - (dist_to_station - last_charge_dist)

            # Distance to next station after this one
            remaining_stops = [
                s for s in all_stops
                if route.distance(origin, s) > dist_to_station
                and s in active_station_ids
            ]
            next_station   = remaining_stops[0] if remaining_stops else dest
            dist_to_next   = route.distance(station_id, next_station)
            can_skip       = (dist_to_next + advisory_km) <= route.world.battery_range_km

            # Determine action
            if station_id in charge_ids:
                # Find this stop's wait time
                stop_obj = next(s for s in bs.charging_stops if s.station_id == station_id)
                if stop_obj.wait_min == 0:
                    action  = 'STOP — CHARGE NOW'
                    colour  = 'green'
                    message = (
                        f"Charger at {station_id} is free when you arrive. "
                        f"Stop and charge. Departs {_to_clock(stop_obj.depart_min)}."
                    )
                elif stop_obj.wait_min <= 10:
                    action  = 'STOP — SHORT WAIT'
                    colour  = 'orange'
                    message = (
                        f"Expect {stop_obj.wait_min:.0f} min wait at {station_id}. "
                        f"Still worth stopping — range to next station is {dist_to_next:.0f}km."
                    )
                else:
                    action  = 'STOP — LONG WAIT'
                    colour  = 'red'
                    message = (
                        f"Charger at {station_id} is busy — {stop_obj.wait_min:.0f} min wait expected. "
                        f"You are scheduled here. If another bus finishes early, wait time may reduce."
                    )
            elif can_skip and range_remaining > dist_to_next + advisory_km:
                action  = 'SKIP — PROCEED TO NEXT'
                colour  = 'blue'
                message = (
                    f"You have {range_remaining:.0f}km range. "
                    f"Station {station_id} is not in your plan — proceed to {next_station} "
                    f"({dist_to_next:.0f}km ahead). Charger availability there looks better."
                )
            else:
                action  = 'HEADS UP — PASSING STATION'
                colour  = 'grey'
                message = (
                    f"Passing station {station_id}. Not in your charging plan. "
                    f"Range remaining: {range_remaining:.0f}km."
                )

            bus_advisories.append({
                'station_id':        station_id,
                'advisory_time_min': round(advisory_time, 1),
                'advisory_clock':    _to_clock(advisory_time),
                'action':            action,
                'colour':            colour,
                'message':           message,
                'range_remaining_km': round(range_remaining, 1),
                'wait_expected_min': (
                    next(s.wait_min for s in bs.charging_stops if s.station_id == station_id)
                    if station_id in charge_ids else 0
                ),
                'in_charging_plan':  station_id in charge_ids,
            })

        # Sort by advisory time
        bus_advisories.sort(key=lambda x: x['advisory_time_min'])
        advisories[bus.id] = bus_advisories

    return advisories


def _to_clock(minutes: float) -> str:
    h = int(minutes) // 60
    m = int(minutes) % 60
    return f"{h:02d}:{m:02d}"
