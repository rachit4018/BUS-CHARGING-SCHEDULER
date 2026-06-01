# Architecture — Bus Charging Scheduler

## Scheduling Approach: Event-Driven Greedy Simulation

### What it is
Buses are sorted by departure time and processed chronologically.
For each bus, all valid charging plans are generated and scored using
a weighted cost function. The lowest-cost plan is assigned.
Bus simulation then computes exact timestamps, updating charger
availability so subsequent buses see accurate wait times.

### Why this approach
- **Scalable**: handles any number of buses, stations, routes, operators
  without changing the engine. Just add data.
- **Extensible**: adding a new cost rule = one new function + one line
  in `_plan_cost()`. No structural changes.
- **Deterministic**: same input always produces same output.
  Makes testing trivial and reactive rescheduling easy.
- **Reactive-ready**: the scheduler is a pure function. To reschedule
  reactively (bus delay, station outage), inject the new event and
  call `run_scheduler()` again from the point of change.

### Trade-offs accepted
Greedy processing (earliest departure first) may not find the
globally optimal schedule. In practice this is acceptable because:
1. The cost function makes locally good decisions
2. Changing weights dynamically adjusts the global behaviour
3. Global optimality would require exponential search — not practical at scale

---

## Three-Layer Design

```
Layer 1: Data          scenarios/*.json
          │             self-contained world description per scenario
          │
Layer 2: Scheduler     scheduler/
          │             pure Python — no UI dependency
          │             models.py → loader.py → route.py → planner.py → dispatcher.py
          │
Layer 3: UI            app.py
                        Streamlit — display only, calls scheduler, never contains logic
```

These layers never bleed into each other. The scheduler has zero
knowledge that Streamlit exists.

---

## Data Structure Design

Every scenario is a JSON file with six sections:

| Section    | Purpose                                     | Why separate            |
|------------|---------------------------------------------|-------------------------|
| `meta`     | Scenario identity                           | Human readability       |
| `world`    | Physical constants (speed, range, charge)   | Single source of truth  |
| `route`    | Ordered segment list with per-segment dist  | Handles any route shape |
| `stations` | Array with id, num_chargers, active flag    | Supports N stations     |
| `weights`  | Cost function weights                       | Per-scenario tuning     |
| `buses`    | Array with operator, direction, departure   | Supports N buses        |

Key design decisions:
- **Route as segment list**: changing a distance = one number. Adding
  a station = split one segment into two.
- **Operator as string label**: new operator = just use the new name.
  Never branch on operator name in code.
- **Active flags on stations and buses**: disable without deleting.
- **Weights in scenario file**: changing operator=1.0 to operator=2.0
  is the *entire* change to reprioritise operator fairness.

---

## Anticipated Changes & How the Design Handles Them

| Change | Handled by | Code change needed? |
|--------|-----------|---------------------|
| Station goes offline | `stations[].active = false` | None |
| Station gets extra charger | `stations[].num_chargers = 2` | None |
| Station relocated | Edit `segments[].distance_km` | None |
| New station inserted | Split segment, add to stations[] | None |
| Bus speed changes | `world.speed_kmph = N` | None |
| Bus breaks down | `buses[].active = false` | None |
| New operator | Just use new name string | None |
| More buses | Add entries to buses[] | None |
| Arrival deadline per bus | Add `latest_arrival` field | Loader + 1 cost fn |
| Priority buses | Add `priority` field per bus | 1 cost function |
| Time-of-day electricity cost | Add `cost_schedule` to station | 1 cost function |
| Driver shift limits | Add `max_hours` per bus | 1 hard constraint fn |
| Multiple routes sharing stations | Stations independent of route | Loader refactor |
| Partial/variable charging | Replace `charge_time_min` with rate | 1 function change |
| Fast vs slow chargers | Add `charger_type` per station | 1 cost fn modifier |
| Weather/traffic (variable speed) | `speed_kmph` per segment | Loader + route calc |
| Station queue capacity limit | Add `max_queue` per station | 1 hard constraint |
| New soft rule | Write fn + 1 line in `_plan_cost()` | 1 function + 1 line |
| Real-time rescheduling | Inject event, call `run_scheduler()` | None (pure fn) |
| Reactive station outage | Set active=false, re-run | None |

---

## How to Change a Weight (Code Example)

**In the JSON file only:**
```json
"weights": { "individual": 1.0, "operator": 2.0, "overall": 1.0 }
```

That is the complete change. No Python files touched.

---

## How to Add a New Rule (Code Example)

Adding "penalise buses that arrive after 23:00":

**1. In scenario JSON:**
```json
"weights": { "individual": 1.0, "operator": 1.0, "overall": 1.0, "lateness": 0.5 }
```

**2. In models.py — add field with default:**
```python
@dataclass
class Weights:
    individual: float
    operator:   float
    overall:    float
    lateness:   float = 0.0
```

**3. In dispatcher.py — add isolated function:**
```python
def _cost_lateness(plan, bus, route, world, charger_free) -> float:
    arrival = _cost_overall(plan, bus, route, world, charger_free)
    deadline = 23 * 60
    return max(0.0, arrival - deadline)
```

**4. One line in `_plan_cost()`:**
```python
return (
    weights.individual * individual_cost +
    weights.operator   * operator_cost   +
    weights.overall    * overall_cost    +
    weights.lateness   * _cost_lateness(plan, bus, route, world, charger_free)
)
```

No other changes. The engine does not need a rewrite.

---

## Assumptions Made

1. **Speed is constant** — no traffic, no variation between buses.
2. **Charging always fills to full** — always exactly 25 minutes.
3. **No partial charging** — a bus either charges fully or skips the station.
4. **Buses travel in route order** — no backtracking.
5. **Origin endpoints (Bengaluru, Kochi) always have slow chargers** — every bus starts with full battery.
6. **Greedy departure order** — earliest-departing buses are scheduled first. This may not be globally optimal but is operationally natural and scalable.
7. **Wait time penalty is linear** — each minute of waiting adds cost proportional to the individual weight.
8. **Inactive buses are silently skipped** — no error, no placeholder in schedule.
9. **Clock times wrap at midnight** — schedules that run past 00:00 will increment the hour beyond 24 (treated as minutes from epoch).

---

## Reactive Scheduling (Future Extension)

The dispatcher is already structured for reactive use:

```python
# Static (today):
schedule = run_scheduler(world, segments, stations, buses, weights, id, name)

# Reactive (future) — same function, injected state:
buses[3].active = False          # bus-BK-04 broke down
stations[1].active = False       # station B went offline
schedule = run_scheduler(...)    # recompute from updated data
```

No engine changes needed. The pure function model makes this trivial.
