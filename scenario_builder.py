"""
scenario_builder.py
-------------------
A separate Streamlit tool to build new scenario JSON files
by filling in a table — exactly like the assessment PDF tables.

Run with:
    streamlit run scenario_builder.py

Workflow:
  1. Fill in scenario name, description, weights
  2. Add buses row by row in the table editor
  3. Click Generate JSON
  4. Copy the JSON or download it as a file
  5. Drop it into scenarios/ folder — app.py picks it up automatically
"""

import streamlit as st
import json
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Scenario Builder",
    page_icon="🛠️",
    layout="wide"
)

st.title("🛠️ Scenario Builder")
st.caption("Fill in the table → get a ready-to-use scenario JSON file")
st.divider()

# ── SECTION 1: META ───────────────────────────────────────────────────
st.subheader("1. Scenario Identity")
col1, col2 = st.columns(2)
with col1:
    scenario_id   = st.text_input("Scenario ID", value="scenario_6",
                                   help="e.g. scenario_6 — used as filename")
    scenario_name = st.text_input("Scenario Name", value="Scenario 6 — Custom",
                                   help="Human readable name shown in the dropdown")
with col2:
    scenario_desc = st.text_area("Description", value="Custom scenario added during interview.",
                                  height=100)

st.divider()

# ── SECTION 2: WORLD CONSTANTS ────────────────────────────────────────
st.subheader("2. World Constants")
col1, col2, col3 = st.columns(3)
with col1:
    speed      = st.number_input("Speed (km/h)", value=60, min_value=1, max_value=200)
with col2:
    bat_range  = st.number_input("Battery Range (km)", value=240, min_value=1)
with col3:
    charge_time = st.number_input("Charge Time (min)", value=25, min_value=1)

st.divider()

# ── SECTION 3: ROUTE ─────────────────────────────────────────────────
st.subheader("3. Route Segments")
st.caption("Add or edit segments. Order matters — top to bottom is Bengaluru→Kochi direction.")

default_segments = pd.DataFrame([
    {"From": "Bengaluru", "To": "A",     "Distance (km)": 100},
    {"From": "A",         "To": "B",     "Distance (km)": 120},
    {"From": "B",         "To": "C",     "Distance (km)": 100},
    {"From": "C",         "To": "D",     "Distance (km)": 120},
    {"From": "D",         "To": "Kochi", "Distance (km)": 100},
])

segments_df = st.data_editor(
    default_segments,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "From":          st.column_config.TextColumn("From",         required=True),
        "To":            st.column_config.TextColumn("To",           required=True),
        "Distance (km)": st.column_config.NumberColumn("Distance (km)", min_value=1, required=True),
    }
)

st.divider()

# ── SECTION 4: STATIONS ───────────────────────────────────────────────
st.subheader("4. Stations")
st.caption("Must match the intermediate stops in your route segments above.")

default_stations = pd.DataFrame([
    {"Station ID": "A", "Num Chargers": 1, "Active": True},
    {"Station ID": "B", "Num Chargers": 1, "Active": True},
    {"Station ID": "C", "Num Chargers": 1, "Active": True},
    {"Station ID": "D", "Num Chargers": 1, "Active": True},
])

stations_df = st.data_editor(
    default_stations,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Station ID":   st.column_config.TextColumn("Station ID",   required=True),
        "Num Chargers": st.column_config.NumberColumn("Num Chargers", min_value=1, default=1),
        "Active":       st.column_config.CheckboxColumn("Active",    default=True),
    }
)

st.divider()

# ── SECTION 5: WEIGHTS ────────────────────────────────────────────────
st.subheader("5. Optimisation Weights")
col1, col2, col3 = st.columns(3)
with col1:
    w_individual = st.number_input("Individual Weight", value=1.0,
                                    min_value=0.0, step=0.5,
                                    help="Penalise individual bus wait time")
with col2:
    w_operator   = st.number_input("Operator Weight",   value=1.0,
                                    min_value=0.0, step=0.5,
                                    help="Penalise operator-level wait imbalance")
with col3:
    w_overall    = st.number_input("Overall Weight",    value=1.0,
                                    min_value=0.0, step=0.5,
                                    help="Penalise total network completion time")

st.divider()

# ── SECTION 6: BUS TABLE ─────────────────────────────────────────────
st.subheader("6. Bus Roster")
st.caption("Fill this in exactly like the tables in the assessment PDF. Add one row per bus.")

# Detect origin and destination from route
try:
    origin      = segments_df.iloc[0]["From"]
    destination = segments_df.iloc[-1]["To"]
    direction_options = [
        f"BK ({origin}→{destination})",
        f"KB ({destination}→{origin})"
    ]
except Exception:
    origin, destination = "Bengaluru", "Kochi"
    direction_options = ["BK (Bengaluru→Kochi)", "KB (Kochi→Bengaluru)"]

default_buses = pd.DataFrame([
    {"Bus ID": "bus-BK-01", "Operator": "kpn",      "Direction": direction_options[0], "Departure": "19:00", "Active": True},
    {"Bus ID": "bus-BK-02", "Operator": "freshbus",  "Direction": direction_options[0], "Departure": "19:15", "Active": True},
    {"Bus ID": "bus-BK-03", "Operator": "flixbus",   "Direction": direction_options[0], "Departure": "19:30", "Active": True},
    {"Bus ID": "bus-KB-01", "Operator": "freshbus",  "Direction": direction_options[1], "Departure": "19:00", "Active": True},
    {"Bus ID": "bus-KB-02", "Operator": "flixbus",   "Direction": direction_options[1], "Departure": "19:15", "Active": True},
])

buses_df = st.data_editor(
    default_buses,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Bus ID":    st.column_config.TextColumn("Bus ID",    required=True),
        "Operator":  st.column_config.TextColumn("Operator",  required=True,
                        help="kpn / freshbus / flixbus — or any new name"),
        "Direction": st.column_config.SelectboxColumn("Direction",
                        options=direction_options, required=True),
        "Departure": st.column_config.TextColumn("Departure",
                        help="Format: HH:MM e.g. 19:00", required=True),
        "Active":    st.column_config.CheckboxColumn("Active", default=True),
    }
)

st.divider()

# ── GENERATE JSON ─────────────────────────────────────────────────────
st.subheader("7. Generate JSON")

if st.button("⚡ Generate Scenario JSON", type="primary", use_container_width=True):

    errors = []

    # Validate segments
    if len(segments_df) == 0:
        errors.append("Route must have at least one segment.")

    # Validate stations
    if len(stations_df) == 0:
        errors.append("Must have at least one station.")

    # Validate buses
    active_buses = buses_df[buses_df["Active"] == True]
    if len(active_buses) == 0:
        errors.append("Must have at least one active bus.")

    # Validate departure times
    for _, row in buses_df.iterrows():
        dep = str(row["Departure"]).strip()
        parts = dep.split(":")
        if len(parts) != 2:
            errors.append(f"Bus {row['Bus ID']}: departure '{dep}' must be HH:MM format.")
        else:
            try:
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    errors.append(f"Bus {row['Bus ID']}: invalid time {dep}")
            except ValueError:
                errors.append(f"Bus {row['Bus ID']}: departure '{dep}' must be HH:MM format.")

    if errors:
        for e in errors:
            st.error(f"❌ {e}")
    else:
        # Build JSON structure
        segments_list = []
        for _, row in segments_df.iterrows():
            segments_list.append({
                "from": str(row["From"]).strip(),
                "to":   str(row["To"]).strip(),
                "distance_km": float(row["Distance (km)"])
            })

        stations_list = []
        for _, row in stations_df.iterrows():
            stations_list.append({
                "id":           str(row["Station ID"]).strip(),
                "num_chargers": int(row["Num Chargers"]),
                "active":       bool(row["Active"])
            })

        buses_list = []
        for _, row in buses_df.iterrows():
            # Extract direction code from display string e.g. "BK (Bengaluru→Kochi)" → "BK"
            dir_code = str(row["Direction"]).split("(")[0].strip()
            buses_list.append({
                "id":        str(row["Bus ID"]).strip(),
                "operator":  str(row["Operator"]).strip().lower(),
                "direction": dir_code,
                "departure": str(row["Departure"]).strip(),
                "active":    bool(row["Active"])
            })

        scenario = {
            "meta": {
                "scenario_id": scenario_id.strip(),
                "name":        scenario_name.strip(),
                "description": scenario_desc.strip()
            },
            "world": {
                "speed_kmph":       float(speed),
                "battery_range_km": float(bat_range),
                "charge_time_min":  float(charge_time)
            },
            "route": {
                "origin":      segments_list[0]["from"],
                "destination": segments_list[-1]["to"],
                "segments":    segments_list
            },
            "stations": stations_list,
            "weights": {
                "individual": float(w_individual),
                "operator":   float(w_operator),
                "overall":    float(w_overall)
            },
            "buses": buses_list
        }

        json_str = json.dumps(scenario, indent=2)

        st.success(f"✅ Scenario JSON generated — {len(buses_list)} buses, {len(stations_list)} stations")

        # Show JSON
        st.code(json_str, language="json")

        # Download button
        filename = f"{scenario_id.strip()}.json"
        st.download_button(
            label=f"⬇️ Download {filename}",
            data=json_str,
            file_name=filename,
            mime="application/json",
            use_container_width=True,
            type="primary"
        )

        st.info(
            f"**Next step:** Save this file as `scenarios/{filename}` "
            f"in your project folder. It will appear in the dropdown on the main app automatically."
        )

# ── TIPS ──────────────────────────────────────────────────────────────
with st.expander("💡 Tips for the Interview"):
    st.markdown("""
**When the interviewer gives you a new departure schedule:**
1. Keep this tool open in a second browser tab
2. Fill in the Bus Roster table row by row — takes 2-3 minutes
3. Click Generate → Download the JSON
4. Drop it into the `scenarios/` folder
5. Reload the main app — new scenario appears in dropdown immediately

**To add a new station:**
- Add a new row in the Route Segments table (split one segment into two)
- Add a new row in the Stations table with the new station ID
- JSON updates automatically

**To change a weight:**
- Just move the sliders in Section 5
- Regenerate JSON → replace the file

**To test a station going offline:**
- In the Stations table, uncheck Active for that station
- Regenerate JSON → scheduler automatically reroutes all buses

**To add a new operator:**
- Just type the new name in the Operator column
- No code change needed anywhere
""")
