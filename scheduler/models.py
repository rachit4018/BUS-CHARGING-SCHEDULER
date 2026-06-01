"""
scheduler/models.py
-------------------
Pure data classes for the Bus Charging Scheduler.
No logic here — only structure.
"""
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class WorldConfig:
    """Physical constants for the simulation world."""
    speed_kmph: float
    battery_range_km: float
    charge_time_min: float


@dataclass
class Segment:
    """One road segment between two consecutive stops."""
    from_loc: str
    to_loc: str
    distance_km: float


@dataclass
class Station:
    """A charging station along the route."""
    id: str
    num_chargers: int
    active: bool


@dataclass
class Bus:
    """A bus making the trip in one direction."""
    id: str
    operator: str
    direction: str   # 'BK' = Bengaluru→Kochi, 'KB' = Kochi→Bengaluru
    departure: str   # clock string e.g. '19:00'
    active: bool


@dataclass
class Weights:
    """Tunable cost-function weights — live in scenario JSON, not code."""
    individual: float
    operator: float
    overall: float
    load_balance: float


@dataclass
class ChargingStop:
    """One charging event for one bus at one station. Times in minutes from 00:00."""
    station_id: str
    arrive_min: float
    wait_min: float
    charge_min: float
    depart_min: float


@dataclass
class BusSchedule:
    """Complete charging timeline for one bus."""
    bus: Bus
    charging_stops: List[ChargingStop]
    depart_min: float
    arrive_min: float
    total_wait_min: float

    @property
    def total_trip_min(self) -> float:
        return self.arrive_min - self.depart_min


@dataclass
class StationQueue:
    """Ordered log of all buses that charged at one station."""
    station_id: str
    events: List[dict] = field(default_factory=list)


@dataclass
class Schedule:
    """Complete scheduler output for one scenario."""
    scenario_id: str
    scenario_name: str
    bus_schedules: List[BusSchedule]
    station_queues: Dict[str, StationQueue]
    total_network_time_min: float
    weights_used: Weights

    @property
    def total_wait_all_buses(self) -> float:
        return sum(bs.total_wait_min for bs in self.bus_schedules)

    @property
    def operator_wait_summary(self) -> Dict[str, float]:
        totals: Dict[str, list] = {}
        for bs in self.bus_schedules:
            totals.setdefault(bs.bus.operator, []).append(bs.total_wait_min)
        return {op: sum(w)/len(w) for op, w in totals.items()}
