"""
scheduler/route.py
------------------
Route distance and travel time calculations.

The RouteCalculator answers one question:
given any two points on the route, how far apart are they
and how long does it take to travel between them?

Everything downstream — range checks, arrival times,
wait time computation — depends on this module.
"""
from typing import List
from scheduler.models import Segment, WorldConfig


class RouteCalculator:
    """
    Precomputes cumulative distances along a route for O(1) lookups.

    Works for both directions (BK and KB) — direction is passed
    per query, not baked into the calculator.
    """

    def __init__(self, segments: List[Segment], world: WorldConfig):
        """
        Args:
            segments: Ordered list of route segments (Bengaluru→A→B→...→Kochi).
            world:    WorldConfig for speed.
        """
        self.world    = world
        self.segments = segments

        # Ordered list of all stop names in BK direction
        self.stops = [segments[0].from_loc] + [s.to_loc for s in segments]

        # Cumulative distance from origin (Bengaluru) to each stop
        self._cum: dict = {}
        total = 0.0
        for i, stop in enumerate(self.stops):
            self._cum[stop] = total
            if i < len(segments):
                total += segments[i].distance_km

    # ── Public API ────────────────────────────────────────────────────

    def distance(self, from_stop: str, to_stop: str) -> float:
        """
        Distance in km between any two stops on the route.
        Order does not matter — always returns a positive value.

        Args:
            from_stop: Name of the starting stop.
            to_stop:   Name of the ending stop.

        Returns:
            Distance in km (always positive).

        Example:
            >>> calc.distance('Bengaluru', 'B')   # → 220.0
            >>> calc.distance('B', 'Bengaluru')   # → 220.0
        """
        return abs(self._cum[to_stop] - self._cum[from_stop])

    def travel_time(self, from_stop: str, to_stop: str) -> float:
        """
        Travel time in minutes between two stops.

        Args:
            from_stop: Name of the starting stop.
            to_stop:   Name of the ending stop.

        Returns:
            Travel time in minutes.
        """
        return self.distance(from_stop, to_stop) / self.world.speed_kmph * 60

    def stops_between(self, origin: str, destination: str) -> List[str]:
        """
        All intermediate stops between origin and destination
        (exclusive of both endpoints), in travel order.

        Works for both BK and KB directions.

        Args:
            origin:      Starting point of this bus's journey.
            destination: Ending point of this bus's journey.

        Returns:
            List of stop names in travel order (origin and destination excluded).

        Example:
            >>> calc.stops_between('Bengaluru', 'Kochi')  # → ['A','B','C','D']
            >>> calc.stops_between('Kochi', 'Bengaluru')  # → ['D','C','B','A']
        """
        idx_o = self.stops.index(origin)
        idx_d = self.stops.index(destination)
        if idx_o < idx_d:
            return self.stops[idx_o + 1: idx_d]
        else:
            return self.stops[idx_d + 1: idx_o][::-1]

    def bus_origin(self, direction: str) -> str:
        """
        Return the starting endpoint for a given direction.

        Args:
            direction: 'BK' or 'KB'.

        Returns:
            'Bengaluru' for BK, 'Kochi' for KB.
        """
        return self.stops[0] if direction == 'BK' else self.stops[-1]

    def bus_destination(self, direction: str) -> str:
        """
        Return the ending endpoint for a given direction.

        Args:
            direction: 'BK' or 'KB'.

        Returns:
            'Kochi' for BK, 'Bengaluru' for KB.
        """
        return self.stops[-1] if direction == 'BK' else self.stops[0]

    def validate_range(self, checkpoints: List[str], max_range: float) -> bool:
        """
        Check that no consecutive pair of checkpoints exceeds max_range km.

        Args:
            checkpoints: Ordered list of stops (origin + charging stations + destination).
            max_range:   Maximum allowed distance between any two consecutive stops.

        Returns:
            True if all gaps are within range, False otherwise.
        """
        for i in range(len(checkpoints) - 1):
            if self.distance(checkpoints[i], checkpoints[i + 1]) > max_range:
                return False
        return True

    def time_to_clock(self, minutes: float) -> str:
        """
        Convert minutes-from-midnight to a human-readable clock string.

        Args:
            minutes: Minutes since midnight (e.g. 1200 = 20:00).

        Returns:
            Clock string in HH:MM format.

        Example:
            >>> calc.time_to_clock(1200)  # → '20:00'
            >>> calc.time_to_clock(75)    # → '01:15'
        """
        h = int(minutes) // 60
        m = int(minutes) % 60
        return f"{h:02d}:{m:02d}"
