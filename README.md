# ⚡ Bus Charging Scheduler — Exponent Energy

A scheduling system for electric buses running the **Bengaluru → Kochi** route,
with charging stations at A, B, C, and D.

**Live App:** [your-app.streamlit.app](https://your-app.streamlit.app)

---

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USERNAME/bus-charging-scheduler
cd bus-charging-scheduler
pip install -r requirements.txt
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## How to Change a Weight

Open any scenario file, e.g. `scenarios/scenario_4.json`:

```json
"weights": {
  "individual": 1.0,
  "operator": 2.0,
  "overall": 1.0
}
```

Change any value. Reload the app. Schedule updates automatically.
**Zero code changes needed.** Weights live entirely in data.

---

## How to Add a New Scenario

1. Copy `scenarios/scenario_1.json` to `scenarios/scenario_6.json`
2. Edit the `buses` array with new departure times
3. Update `meta.scenario_id` and `meta.name`
4. Reload the app — it appears in the dropdown automatically

---

## How to Add a New Soft Rule

**Example: penalise buses that arrive too late**

**Step 1** — Add weight to scenario JSON:
```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0,
  "lateness": 0.5
}
```

**Step 2** — Add weight field to `Weights` dataclass in `scheduler/models.py`:
```python
@dataclass
class Weights:
    individual: float
    operator:   float
    overall:    float
    lateness:   float = 0.0   # new field with default
```

**Step 3** — Add cost component to `dispatcher.py`:
```python
# Define the new cost function (isolated, testable)
def _cost_lateness(plan, bus, route, world, charger_free) -> float:
    predicted_arrival = _cost_overall(plan, bus, route, world, charger_free)
    deadline = 23 * 60  # 23:00 hard deadline
    return max(0.0, predicted_arrival - deadline)

# Add one line to _plan_cost():
return (
    weights.individual * individual_cost +
    weights.operator   * operator_cost   +
    weights.overall    * overall_cost    +
    weights.lateness   * _cost_lateness(...)   # ← new line
)
```

No engine changes. No data format changes. Just a new function and one line.

---

## How to Add a New Station

In your scenario JSON, add to `route.segments` and `stations`:

```json
"segments": [
  {"from": "Bengaluru", "to": "A",  "distance_km": 100},
  {"from": "A",         "to": "A2", "distance_km": 60},
  {"from": "A2",        "to": "B",  "distance_km": 60},
  ...
],
"stations": [
  {"id": "A",  "num_chargers": 1, "active": true},
  {"id": "A2", "num_chargers": 2, "active": true},
  ...
]
```

Zero code changes. The scheduler handles any number of stations.

---

## Running Tests

```bash
pytest tests/ -v
```

Expected: **49 tests passing**

Key tests:
- `test_no_range_violation` — parametrized across all 5 scenarios, critical safety check
- `test_station_order_consistent` — no charger overlap
- `test_inactive_bus_excluded` — fleet management
- `test_higher_operator_weight_changes_schedule` — weight sensitivity

---

## Project Structure

```
bus-charging-scheduler/
├── scenarios/          # JSON scenario files (one per scenario)
├── scheduler/
│   ├── models.py       # Data classes — no logic
│   ├── loader.py       # JSON reader + validator
│   ├── route.py        # Distance & travel time calculations
│   ├── planner.py      # Valid charging plan generator
│   └── dispatcher.py   # Event-driven scheduler + cost function
├── tests/              # 49 unit + integration tests
├── docs/               # Auto-generated API documentation
├── app.py              # Streamlit UI (display only)
└── ARCHITECTURE.md     # Framework choice + design decisions
```

---

## Generating API Documentation

```bash
pip install pdoc
pdoc scheduler --output-dir docs/ --format markdown
```

Or for HTML:
```bash
pdoc scheduler --output-dir docs/html
```
