"""
scheduler/loader.py
-------------------
Read, validate and parse scenario JSON files into typed model objects.
No scheduling logic here — only data ingestion.
"""
import json
from pathlib import Path
from typing import Tuple, List
from scheduler.models import (
    WorldConfig, Segment, Station, Bus, Weights,
    Schedule, BusSchedule, ChargingStop, StationQueue
)


def load_scenario(path: str) -> dict:
    """
    Load a scenario JSON file and return the raw dict.

    Args:
        path: File path to the scenario JSON.

    Returns:
        Raw dict of the scenario data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If required fields are missing or invalid.
    """
    with open(path) as f:
        data = json.load(f)
    _validate(data)
    return data


def parse_scenario(data: dict) -> Tuple[WorldConfig, List[Segment], List[Station], List[Bus], Weights]:
    """
    Convert a raw scenario dict into typed model objects.

    Args:
        data: Raw scenario dict from load_scenario().

    Returns:
        Tuple of (WorldConfig, segments, stations, active_buses, Weights).
        Only active buses and stations are included.
    """
    world = WorldConfig(
        speed_kmph=data['world']['speed_kmph'],
        battery_range_km=data['world']['battery_range_km'],
        charge_time_min=data['world']['charge_time_min'],
    )
    segments = [
        Segment(s['from'], s['to'], s['distance_km'])
        for s in data['route']['segments']
    ]
    stations = [
        Station(s['id'], s['num_chargers'], s['active'])
        for s in data['stations']
    ]
    buses = [
        Bus(b['id'], b['operator'], b['direction'], b['departure'], b['active'])
        for b in data['buses']
        if b['active']
    ]
    weights = Weights(**data['weights'])
    return world, segments, stations, buses, weights


def list_scenarios(scenarios_dir: str = 'scenarios') -> List[dict]:
    """
    List all available scenario files in the scenarios directory.

    Returns:
        List of dicts with keys: path, scenario_id, name.
        Sorted by scenario_id.
    """
    results = []
    for p in sorted(Path(scenarios_dir).glob('*.json')):
        try:
            data = load_scenario(str(p))
            results.append({
                'path': str(p),
                'scenario_id': data['meta']['scenario_id'],
                'name': data['meta']['name'],
            })
        except Exception:
            pass  # Skip malformed files silently
    return results


def _validate(data: dict) -> None:
    """Hard validation — raises ValueError for missing or invalid fields."""
    required_top = ['meta', 'world', 'route', 'stations', 'weights', 'buses']
    for key in required_top:
        if key not in data:
            raise ValueError(f"Scenario missing required key: '{key}'")

    required_world = ['speed_kmph', 'battery_range_km', 'charge_time_min']
    for key in required_world:
        if key not in data['world']:
            raise ValueError(f"world section missing: '{key}'")
        if data['world'][key] <= 0:
            raise ValueError(f"world.{key} must be positive, got {data['world'][key]}")

    if 'segments' not in data['route']:
        raise ValueError("route section missing 'segments'")
    if len(data['route']['segments']) < 1:
        raise ValueError("route must have at least one segment")

    required_weights = ['individual', 'operator', 'overall']
    for key in required_weights:
        if key not in data['weights']:
            raise ValueError(f"weights section missing: '{key}'")

    if len(data['buses']) == 0:
        raise ValueError("buses array is empty — nothing to schedule")
