"""
app.py
------
Streamlit UI for the Bus Charging Scheduler.

This file contains ONLY display logic.
All scheduling decisions happen in the scheduler/ package.

Layout:
  - Dropdown to pick a scenario
  - Tab 1: Scenario Input  — raw data as readable tables
  - Tab 2: Per-Bus Timetable — full charging timeline per bus
  - Tab 3: Per-Station View — charge order at each station A/B/C/D
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from scheduler.loader import load_scenario, parse_scenario, list_scenarios
from scheduler.dispatcher import run_scheduler
from scheduler.route import RouteCalculator

# ── Page Config ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="⚡",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────────
st.title("⚡ Bus Charging Scheduler")
st.caption("Exponent Energy — EV Bus Route Optimiser · Bengaluru ↔ Kochi")
st.divider()

# ── Scenario Selector ─────────────────────────────────────────────────
scenarios = list_scenarios('scenarios')
if not scenarios:
    st.error("No scenario files found in /scenarios folder. Check your setup.")
    st.stop()

scenario_map = {s['name']: s for s in scenarios}
selected_name = st.selectbox(
    "**Select Scenario**",
    options=list(scenario_map.keys()),
    help="Pick a scenario to load and schedule."
)
selected = scenario_map[selected_name]

# ── Load & Run (cached) ───────────────────────────────────────────────
@st.cache_data
def get_schedule(path: str):
    data = load_scenario(path)
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(
        world, segments, stations, buses, weights,
        data['meta']['scenario_id'],
        data['meta']['name'],
    )
    return data, world, segments, stations, schedule

try:
    data, world, segments, stations, schedule = get_schedule(selected['path'])
except ValueError as e:
    st.error(f"Scheduler error: {e}")
    st.stop()

route = RouteCalculator(segments, world)

# ── Three Tabs ────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📋 Scenario Input",
    "🚌 Per-Bus Timetable",
    "🔌 Per-Station View",
])

# ════════════════════════════════════════════════════════════════════════
# TAB 1 — SCENARIO INPUT
# ════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader(data['meta']['name'])
    st.write(data['meta']['description'])
    st.divider()

    col_world, col_weights, col_route = st.columns(3)

    with col_world:
        st.markdown("**🌍 World Constants**")
        wdf = pd.DataFrame([{
            'Parameter': 'Speed',
            'Value': f"{world.speed_kmph} km/h"
        }, {
            'Parameter': 'Battery Range',
            'Value': f"{world.battery_range_km} km"
        }, {
            'Parameter': 'Charge Time',
            'Value': f"{world.charge_time_min} min"
        }])
        st.dataframe(wdf, hide_index=True, use_container_width=True)

    with col_weights:
        st.markdown("**⚖️ Optimisation Weights**")
        wtdf = pd.DataFrame([
            {'Weight': 'Individual', 'Value': schedule.weights_used.individual},
            {'Weight': 'Operator',   'Value': schedule.weights_used.operator},
            {'Weight': 'Overall',    'Value': schedule.weights_used.overall},
        ])
        st.dataframe(wtdf, hide_index=True, use_container_width=True)

    with col_route:
        st.markdown("**🗺️ Route Segments**")
        seg_df = pd.DataFrame([{
            'From': s['from'], 'To': s['to'], 'Distance (km)': s['distance_km']
        } for s in data['route']['segments']])
        st.dataframe(seg_df, hide_index=True, use_container_width=True)

    st.markdown("**🚌 Bus Roster**")
    buses_df = pd.DataFrame([{
        'Bus ID':    b['id'],
        'Operator':  b['operator'].upper(),
        'Direction': '→ Kochi' if b['direction'] == 'BK' else '→ Bengaluru',
        'Departure': b['departure'],
        'Active':    '✅' if b['active'] else '❌',
    } for b in data['buses']])
    st.dataframe(buses_df, hide_index=True, use_container_width=True)

    # Summary metrics
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Buses", len(schedule.bus_schedules))
    m2.metric("BK Buses", sum(1 for bs in schedule.bus_schedules if bs.bus.direction == 'BK'))
    m3.metric("KB Buses", sum(1 for bs in schedule.bus_schedules if bs.bus.direction == 'KB'))
    m4.metric("Active Stations", sum(1 for s in stations if s.active))

# ════════════════════════════════════════════════════════════════════════
# TAB 2 — PER-BUS TIMETABLE
# ════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Per-Bus Charging Timetable")
    st.caption("All times shown as HH:MM (24-hour clock). Wait > 0 means bus queued at station.")

    rows = []
    for bs in sorted(schedule.bus_schedules, key=lambda x: x.depart_min):
        origin = route.bus_origin(bs.bus.direction)
        dest   = route.bus_destination(bs.bus.direction)

        # Add departure row
        rows.append({
            'Bus ID':   bs.bus.id,
            'Operator': bs.bus.operator.upper(),
            'Direction': f"{origin} → {dest}",
            'Event':    f"🚍 Departs {origin}",
            'Time':     route.time_to_clock(bs.depart_min),
            'Wait (min)': '—',
            'Charge (min)': '—',
        })

        for stop in bs.charging_stops:
            wait_str = f"⏳ {stop.wait_min:.0f}" if stop.wait_min > 0 else "✅ 0"
            rows.append({
                'Bus ID':   bs.bus.id,
                'Operator': bs.bus.operator.upper(),
                'Direction': f"{origin} → {dest}",
                'Event':    f"🔌 Station {stop.station_id}",
                'Time':     route.time_to_clock(stop.arrive_min),
                'Wait (min)': wait_str,
                'Charge (min)': f"{stop.charge_min:.0f}",
            })

        # Add arrival row
        rows.append({
            'Bus ID':   bs.bus.id,
            'Operator': bs.bus.operator.upper(),
            'Direction': f"{origin} → {dest}",
            'Event':    f"🏁 Arrives {dest}",
            'Time':     route.time_to_clock(bs.arrive_min),
            'Wait (min)': '—',
            'Charge (min)': '—',
        })

    timetable_df = pd.DataFrame(rows)
    st.dataframe(timetable_df, hide_index=True, use_container_width=True, height=500)

    # Summary stats
    st.divider()
    st.markdown("**Wait Time Summary by Bus**")
    summary_rows = []
    for bs in sorted(schedule.bus_schedules, key=lambda x: x.bus.id):
        summary_rows.append({
            'Bus ID':       bs.bus.id,
            'Operator':     bs.bus.operator.upper(),
            'Direction':    '→ Kochi' if bs.bus.direction == 'BK' else '→ Bengaluru',
            'Stations Used': ' → '.join(s.station_id for s in bs.charging_stops),
            'Total Wait (min)': f"{bs.total_wait_min:.0f}",
            'Trip Time (min)':  f"{bs.total_trip_min:.0f}",
            'Arrives':      route.time_to_clock(bs.arrive_min),
        })
    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

    # Operator fairness
    st.divider()
    st.markdown("**Operator Wait Fairness**")
    op_summary = schedule.operator_wait_summary
    op_rows = [{'Operator': op.upper(), 'Avg Wait (min)': f"{avg:.1f}"}
               for op, avg in sorted(op_summary.items())]
    st.dataframe(pd.DataFrame(op_rows), hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════
# TAB 3 — PER-STATION VIEW
# ════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Per-Station Charging Order")
    st.caption("Shows the sequence in which buses used each charger.")

    active_station_ids = [s.id for s in stations if s.active]

    for sid in active_station_ids:
        sq = schedule.station_queues.get(sid)
        if not sq or not sq.events:
            st.markdown(f"**Station {sid}** — no buses charged here")
            continue

        events_sorted = sorted(sq.events, key=lambda e: e['charge_start'])

        st.markdown(f"**🔌 Station {sid}** — {len(events_sorted)} buses charged")
        station_rows = []
        for i, ev in enumerate(events_sorted, 1):
            station_rows.append({
                'Order':        i,
                'Bus ID':       ev['bus_id'],
                'Operator':     ev['operator'].upper(),
                'Arrived':      route.time_to_clock(ev['arrive_min']),
                'Waited (min)': f"{ev['wait_min']:.0f}",
                'Charge Start': route.time_to_clock(ev['charge_start']),
                'Departed':     route.time_to_clock(ev['depart_min']),
            })
        st.dataframe(pd.DataFrame(station_rows), hide_index=True, use_container_width=True)
        st.write("")
