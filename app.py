"""
app.py
------
Streamlit UI for the Bus Charging Scheduler.
Display only — all scheduling logic lives in scheduler/ package.

5 Tabs:
  1. Scenario Input     — raw input as readable tables
  2. Per-Bus Timetable  — full charging timeline per bus
  3. Per-Station View   — charge order at each station
  4. Station Health     — load analysis, overload detection
  5. Driver Advisories  — 10km-before-station messages per bus
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from scheduler.loader import load_scenario, parse_scenario, list_scenarios
from scheduler.dispatcher import run_scheduler
from scheduler.route import RouteCalculator
from scheduler.advisor import analyse_station_load, generate_driver_advisories

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Bus Charging Scheduler")
st.caption("Exponent Energy — EV Bus Route Optimiser · Bengaluru ↔ Kochi")
st.divider()

# ── Scenario Selector ─────────────────────────────────────────────────
scenarios = list_scenarios('scenarios')
if not scenarios:
    st.error("No scenario files found in /scenarios folder.")
    st.stop()

scenario_map  = {s['name']: s for s in scenarios}
selected_name = st.selectbox("**Select Scenario**", options=list(scenario_map.keys()))
selected      = scenario_map[selected_name]

# ── Load & Run ────────────────────────────────────────────────────────
@st.cache_data
def get_schedule(path: str):
    data = load_scenario(path)
    world, segments, stations, buses, weights = parse_scenario(data)
    schedule = run_scheduler(
        world, segments, stations, buses, weights,
        data['meta']['scenario_id'], data['meta']['name'],
    )
    return data, world, segments, stations, schedule

try:
    data, world, segments, stations, schedule = get_schedule(selected['path'])
except ValueError as e:
    st.error(f"Scheduler error: {e}")
    st.stop()

route = RouteCalculator(segments, world)

# ── Five Tabs ────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 Scenario Input",
    "🚌 Per-Bus Timetable",
    "🔌 Per-Station View",
    "📊 Station Health",
    "📡 Driver Advisories",
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
        st.dataframe(pd.DataFrame([
            {'Parameter': 'Speed',          'Value': f"{world.speed_kmph} km/h"},
            {'Parameter': 'Battery Range',  'Value': f"{world.battery_range_km} km"},
            {'Parameter': 'Charge Time',    'Value': f"{world.charge_time_min} min"},
        ]), hide_index=True, use_container_width=True)

    with col_weights:
        st.markdown("**⚖️ Optimisation Weights**")
        st.dataframe(pd.DataFrame([
            {'Weight': 'Individual', 'Value': schedule.weights_used.individual},
            {'Weight': 'Operator',   'Value': schedule.weights_used.operator},
            {'Weight': 'Overall',    'Value': schedule.weights_used.overall},
            {'Weight': 'Load Balance', 'Value': schedule.weights_used.load_balance},
        ]), hide_index=True, use_container_width=True)

    with col_route:
        st.markdown("**🗺️ Route Segments**")
        st.dataframe(pd.DataFrame([{
            'From': s['from'], 'To': s['to'], 'Distance (km)': s['distance_km']
        } for s in data['route']['segments']]), hide_index=True, use_container_width=True)

    st.markdown("**🚌 Bus Roster**")
    st.dataframe(pd.DataFrame([{
        'Bus ID':    b['id'],
        'Operator':  b['operator'].upper(),
        'Direction': '→ Kochi' if b['direction'] == 'BK' else '→ Bengaluru',
        'Departure': b['departure'],
        'Active':    '✅' if b['active'] else '❌',
    } for b in data['buses']]), hide_index=True, use_container_width=True)

    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Buses",     len(schedule.bus_schedules))
    m2.metric("BK Buses",        sum(1 for bs in schedule.bus_schedules if bs.bus.direction == 'BK'))
    m3.metric("KB Buses",        sum(1 for bs in schedule.bus_schedules if bs.bus.direction == 'KB'))
    m4.metric("Active Stations", sum(1 for s in stations if s.active))

# ════════════════════════════════════════════════════════════════════════
# TAB 2 — PER-BUS TIMETABLE
# ════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Per-Bus Charging Timetable")
    st.caption("All times in HH:MM. ⏳ = waited for charger. ✅ = no wait.")

    rows = []
    for bs in sorted(schedule.bus_schedules, key=lambda x: x.depart_min):
        origin = route.bus_origin(bs.bus.direction)
        dest   = route.bus_destination(bs.bus.direction)
        rows.append({
            'Bus ID': bs.bus.id, 'Operator': bs.bus.operator.upper(),
            'Direction': f"{origin}→{dest}", 'Event': f"🚍 Departs {origin}",
            'Time': route.time_to_clock(bs.depart_min),
            'Wait (min)': '—', 'Charge (min)': '—',
        })
        for stop in bs.charging_stops:
            rows.append({
                'Bus ID': bs.bus.id, 'Operator': bs.bus.operator.upper(),
                'Direction': f"{origin}→{dest}",
                'Event': f"🔌 Station {stop.station_id}",
                'Time': route.time_to_clock(stop.arrive_min),
                'Wait (min)': f"⏳ {stop.wait_min:.0f}" if stop.wait_min > 0 else "✅ 0",
                'Charge (min)': f"{stop.charge_min:.0f}",
            })
        rows.append({
            'Bus ID': bs.bus.id, 'Operator': bs.bus.operator.upper(),
            'Direction': f"{origin}→{dest}", 'Event': f"🏁 Arrives {dest}",
            'Time': route.time_to_clock(bs.arrive_min),
            'Wait (min)': '—', 'Charge (min)': '—',
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=500)

    st.divider()
    st.markdown("**Wait Time Summary**")
    st.dataframe(pd.DataFrame([{
        'Bus ID':            bs.bus.id,
        'Operator':          bs.bus.operator.upper(),
        'Direction':         '→ Kochi' if bs.bus.direction == 'BK' else '→ Bengaluru',
        'Stations Used':     ' → '.join(s.station_id for s in bs.charging_stops),
        'Total Wait (min)':  f"{bs.total_wait_min:.0f}",
        'Trip Time (min)':   f"{bs.total_trip_min:.0f}",
        'Arrives':           route.time_to_clock(bs.arrive_min),
    } for bs in sorted(schedule.bus_schedules, key=lambda x: x.bus.id)]),
    hide_index=True, use_container_width=True)

    st.divider()
    st.markdown("**Operator Fairness**")
    op_summary = schedule.operator_wait_summary
    st.dataframe(pd.DataFrame([
        {'Operator': op.upper(), 'Avg Wait (min)': f"{avg:.1f}"}
        for op, avg in sorted(op_summary.items())
    ]), hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════
# TAB 3 — PER-STATION VIEW
# ════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Per-Station Charging Order")
    st.caption("Sequence in which buses used each charger.")

    for sid in [s.id for s in stations if s.active]:
        sq = schedule.station_queues.get(sid)
        if not sq or not sq.events:
            st.markdown(f"**Station {sid}** — no buses charged here")
            continue
        events_sorted = sorted(sq.events, key=lambda e: e['charge_start'])
        st.markdown(f"**🔌 Station {sid}** — {len(events_sorted)} buses")
        st.dataframe(pd.DataFrame([{
            'Order':         i,
            'Bus ID':        ev['bus_id'],
            'Operator':      ev['operator'].upper(),
            'Arrived':       route.time_to_clock(ev['arrive_min']),
            'Waited (min)':  f"{ev['wait_min']:.0f}",
            'Charge Start':  route.time_to_clock(ev['charge_start']),
            'Departed':      route.time_to_clock(ev['depart_min']),
        } for i, ev in enumerate(events_sorted, 1)]),
        hide_index=True, use_container_width=True)
        st.write("")

# ════════════════════════════════════════════════════════════════════════
# TAB 4 — STATION HEALTH
# ════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("📊 Station Health Analysis")
    st.caption(
        "Analyses how well load is distributed across stations. "
        "Detects overloaded stations even when another station was available."
    )

    load_analysis = analyse_station_load(schedule, stations, route)

    # Summary cards across the top
    cols = st.columns(len(stations))
    verdict_colors = {
        'well_used':      '🟢',
        'congested':      '🟡',
        'overloaded':     '🔴',
        'underutilised':  '🔵',
        'unused':         '⚪',
        'offline':        '⛔',
    }
    for col, station in zip(cols, stations):
        info = load_analysis.get(station.id, {})
        verdict = info.get('verdict', 'unknown')
        icon    = verdict_colors.get(verdict, '❓')
        col.metric(
            label=f"{icon} Station {station.id}",
            value=f"{info.get('total_buses', 0)} buses",
            delta=f"avg wait {info.get('avg_wait', 0):.0f} min",
            delta_color="inverse",
        )

    st.divider()

    # Detailed breakdown per station
    for station in stations:
        info    = load_analysis.get(station.id, {})
        verdict = info.get('verdict', 'unknown')
        icon    = verdict_colors.get(verdict, '❓')

        with st.expander(
            f"{icon} Station {station.id} — {verdict.upper()} "
            f"({info.get('total_buses',0)} buses, avg wait {info.get('avg_wait',0):.0f} min)",
            expanded=(verdict in ['overloaded', 'congested'])
        ):
            if verdict in ['unused', 'offline']:
                st.info(info.get('suggestion', ''))
                continue

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Buses",     info.get('total_buses', 0))
            c2.metric("Avg Wait",        f"{info.get('avg_wait', 0):.1f} min")
            c3.metric("Max Wait",        f"{info.get('max_wait', 0):.1f} min")
            c4.metric("Buses Waited",    f"{info.get('contended_buses', 0)}")

            peak = info.get('peak_window')
            if peak:
                st.caption(
                    f"📈 Peak window starts at {peak['start']} — "
                    f"{peak['bus_count']} buses in a 60-min window"
                )

            # Suggestion box
            if verdict == 'overloaded':
                st.error(f"⚠️ {info.get('suggestion', '')}")
            elif verdict == 'congested':
                st.warning(f"⚠️ {info.get('suggestion', '')}")
            elif verdict == 'underutilised':
                st.info(f"ℹ️ {info.get('suggestion', '')}")
            else:
                st.success(f"✅ {info.get('suggestion', '')}")

    st.divider()

    # Overall distribution table
    st.markdown("**Distribution Summary**")
    summary_rows = []
    for station in stations:
        info = load_analysis.get(station.id, {})
        summary_rows.append({
            'Station':          station.id,
            'Buses Charged':    info.get('total_buses', 0),
            'Total Wait (min)': info.get('total_wait', 0),
            'Avg Wait (min)':   info.get('avg_wait', 0),
            'Max Wait (min)':   info.get('max_wait', 0),
            'Contention %':     f"{info.get('utilisation_pct', 0)}%",
            'Status':           info.get('verdict', '').upper(),
        })
    st.dataframe(pd.DataFrame(summary_rows), hide_index=True, use_container_width=True)

    # Imbalance warning
    bus_counts = [
        load_analysis[s.id]['total_buses']
        for s in stations
        if s.active and load_analysis[s.id]['verdict'] != 'offline'
    ]
    if bus_counts and max(bus_counts) > 0:
        imbalance = max(bus_counts) - min(bus_counts)
        if imbalance > 5:
            st.warning(
                f"⚠️ **Load Imbalance Detected:** The busiest station handled "
                f"{max(bus_counts)} buses while the least-used handled {min(bus_counts)}. "
                f"Consider tuning the individual or overall weights to redistribute load."
            )

# ════════════════════════════════════════════════════════════════════════
# TAB 5 — DRIVER ADVISORIES
# ════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("📡 Driver Advisories")
    st.caption(
        f"Messages sent to each driver **{10}km before each station** they pass. "
        "Tells them whether to stop and charge, skip to the next station, or just note they're passing."
    )

    advisory_km = st.slider(
        "Advisory distance before station (km)",
        min_value=5, max_value=30, value=10, step=5,
        help="How far before the station the driver receives the message"
    )

    advisories = generate_driver_advisories(schedule, stations, route, advisory_km=advisory_km)

    # Colour map for action types
    action_style = {
        'STOP — CHARGE NOW':    ('🟢', 'success'),
        'STOP — SHORT WAIT':    ('🟡', 'warning'),
        'STOP — LONG WAIT':     ('🔴', 'error'),
        'SKIP — PROCEED TO NEXT': ('🔵', 'info'),
        'HEADS UP — PASSING STATION': ('⚪', None),
    }

    # Filter options
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        show_direction = st.selectbox(
            "Filter by direction",
            ['All', '→ Kochi (BK)', '→ Bengaluru (KB)']
        )
    with col_filter2:
        show_action = st.selectbox(
            "Filter by action",
            ['All', 'STOP — CHARGE NOW', 'STOP — SHORT WAIT',
             'STOP — LONG WAIT', 'SKIP — PROCEED TO NEXT', 'HEADS UP — PASSING STATION']
        )

    st.divider()

    # Display per bus
    for bs in sorted(schedule.bus_schedules, key=lambda x: x.depart_min):
        bus     = bs.bus
        origin  = route.bus_origin(bus.direction)
        dest    = route.bus_destination(bus.direction)
        dir_str = '→ Kochi (BK)' if bus.direction == 'BK' else '→ Bengaluru (KB)'

        # Apply direction filter
        if show_direction != 'All' and show_direction != dir_str:
            continue

        bus_advs = advisories.get(bus.id, [])

        # Apply action filter
        if show_action != 'All':
            bus_advs = [a for a in bus_advs if a['action'] == show_action]

        if not bus_advs:
            continue

        with st.expander(
            f"🚌 {bus.id} | {bus.operator.upper()} | {origin} → {dest} | "
            f"Departs {bs.bus.departure} | {len(bus_advs)} advisories",
            expanded=False
        ):
            for adv in bus_advs:
                icon, style = action_style.get(adv['action'], ('⚪', None))
                msg = (
                    f"**{adv['advisory_clock']}** — "
                    f"{icon} **{adv['action']}** at Station {adv['station_id']}  \n"
                    f"{adv['message']}  \n"
                    f"Range remaining at advisory point: **{adv['range_remaining_km']} km**"
                )
                if style == 'success':
                    st.success(msg)
                elif style == 'warning':
                    st.warning(msg)
                elif style == 'error':
                    st.error(msg)
                elif style == 'info':
                    st.info(msg)
                else:
                    st.markdown(f"_{msg}_")

    st.divider()

    # Full advisory table
    st.markdown("**All Advisories — Full Table**")
    all_rows = []
    for bs in schedule.bus_schedules:
        for adv in advisories.get(bs.bus.id, []):
            if show_action != 'All' and adv['action'] != show_action:
                continue
            all_rows.append({
                'Bus ID':          bs.bus.id,
                'Operator':        bs.bus.operator.upper(),
                'Direction':       '→ Kochi' if bs.bus.direction == 'BK' else '→ Bengaluru',
                'Station':         adv['station_id'],
                'Advisory At':     adv['advisory_clock'],
                'Action':          adv['action'],
                'Range Left (km)': adv['range_remaining_km'],
                'Wait Expected':   f"{adv['wait_expected_min']:.0f} min" if adv['in_charging_plan'] else '—',
            })

    if all_rows:
        st.dataframe(
            pd.DataFrame(all_rows),
            hide_index=True,
            use_container_width=True,
            height=400,
        )
