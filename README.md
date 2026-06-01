# ⚡ Bus Charging Scheduler — Exponent Energy

A scheduling system for electric buses running the **Bengaluru → Kochi** route,
with charging stations at A, B, C, and D.

**Live App:** [rachit-pandya-bus-charging-scheduler-y8k8vhzs2msascijngengr.streamlit.app](https://rachit-pandya-bus-charging-scheduler-y8k8vhzs2msascijngengr.streamlit.app/)
**GitHub:** [github.com/rachit4018/bus-charging-scheduler](https://github.com/rachit4018/BUS-CHARGING-SCHEDULER)

---

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USERNAME/bus-charging-scheduler
cd bus-charging-scheduler
pip install -r requirements.txt
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

To run the scenario builder tool alongside:
```bash
streamlit run scenario_builder.py --server.port 8502
```

Open [http://localhost:8502](http://localhost:8502) in a second browser tab.

---

## What the App Does

The app has **5 tabs**:

| Tab | What it shows |
|-----|--------------|
| 📋 Scenario Input | Raw scenario data — buses, weights, route, world constants |
| 🚌 Per-Bus Timetable | Full charging timeline per bus with wait times |
| 🔌 Per-Station View | Order in which buses used each charger |
| 📊 Station Health | Load analysis — detects overloaded and underutilised stations |
| 📡 Driver Advisories | Messages sent 10km before each station telling drivers whether to stop or skip |

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

**Option A — Use the Scenario Builder (recommended)**
1. Run `streamlit run scenario_builder.py --server.port 8502`
2. Fill in the bus roster table row by row
3. Click Generate JSON → Download
4. Drop the file into `scenarios/` folder
5. Reload the main app — it appears in the dropdown automatically

**Option B — Edit JSON directly**
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
  "operator":   1.0,
  "overall":    1.0,
  "lateness":   0.5
}
```

**Step 2** — Add field to `Weights` dataclass in `scheduler/models.py`:
```python
@dataclass
class Weights:
    individual: float
    operator:   float
    overall:    float
    lateness:   float = 0.0   # default keeps existing scenarios working
```

**Step 3** — Add isolated cost function in `scheduler/dispatcher.py`:
```python
def _cost_lateness(plan, bus, route, world, charger_free) -> float:
    predicted_arrival = _cost_overall(plan, bus, route, world, charger_free)
    deadline = 23 * 60  # 23:00
    return max(0.0, predicted_arrival - deadline)
```

**Step 4** — Add one line to `_plan_cost()` in `scheduler/dispatcher.py`:
```python
return (
    weights.individual * individual_cost +
    weights.operator   * operator_cost   +
    weights.overall    * overall_cost    +
    weights.lateness   * _cost_lateness(plan, bus, route, world, charger_free)
)
```

No engine changes. No data format changes.

---

## How to Add a New Station

In your scenario JSON, split one segment into two and add the station:

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

## How to Take a Station Offline

```json
{"id": "B", "num_chargers": 1, "active": false}
```

The scheduler automatically excludes inactive stations from all charging plans.
If no valid plan exists after the change, the scheduler raises an explicit error.

---

## Running Tests

```bash
pytest tests/ -v
```

Expected: **49 tests passing**

Key tests:
- `test_no_range_violation` — parametrized across all 5 scenarios, critical safety check
- `test_station_order_consistent` — no charger overlap at any station
- `test_inactive_bus_excluded` — inactive buses never appear in schedule
- `test_higher_operator_weight_changes_schedule` — weight sensitivity

---

## Project Structure

```
bus-charging-scheduler/
├── scenarios/               # JSON scenario files (one per scenario)
│   ├── scenario_1.json      # Even spacing — baseline
│   ├── scenario_2.json      # Bunched start
│   ├── scenario_3.json      # Asymmetric load
│   ├── scenario_4.json      # Operator heavy (KPN dominant)
│   └── scenario_5.json      # Worst case convergence
├── scheduler/
│   ├── models.py            # Data classes — no logic
│   ├── loader.py            # JSON reader + validator
│   ├── route.py             # Distance & travel time calculations
│   ├── planner.py           # Valid charging plan generator
│   ├── dispatcher.py        # Event-driven scheduler + cost function
│   └── advisor.py           # Station health analysis + driver advisories
├── tests/                   # 49 unit + integration tests
├── docs/                    # Auto-generated API documentation
├── app.py                   # Streamlit UI — 5 tabs, display only
├── scenario_builder.py      # Separate tool — table to JSON converter
├── requirements.txt
├── README.md
└── ARCHITECTURE.md
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