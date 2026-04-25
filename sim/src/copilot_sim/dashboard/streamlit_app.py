"""Streamlit dashboard for the digital twin demo.

Six charts driven by the SQLite historian:

1. Per-component true health over time.
2. Driver streams (the four brief inputs) over time.
3. Print outcome ribbon — OK / QUALITY_DEGRADED / HALTED stacked
   counts per tick window.
4. Maintenance event timeline by component.
5. Coupling factor heatmap — how the ten named factors evolved.
6. True vs observed health for the heater (the §3.4 sensor-fault
   story made visible).

Launch:
    cd sim
    uv run streamlit run src/copilot_sim/dashboard/streamlit_app.py

If a `--db-path` query arg is set on the URL it is used; otherwise the
default is `data/historian.sqlite`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from ..historian.connection import open_db
from ..historian.writer import list_run_ids


def _default_db_path() -> Path:
    return Path("data/historian.sqlite")


@st.cache_resource
def _open(db_path: str):
    return open_db(db_path)


def _load_drivers(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, temperature_stress, humidity_contamination, operational_load,
               maintenance_level, print_outcome, coupling_factors_json
        FROM drivers WHERE run_id = ? ORDER BY tick
        """,
        conn,
        params=[run_id],
    )


def _load_component_health(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, component_id, health_index, status
        FROM component_state WHERE run_id = ? ORDER BY tick, component_id
        """,
        conn,
        params=[run_id],
    )


def _load_observed_health(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, component_id, observed_health_index, observed_status, sensor_note
        FROM observed_component_state WHERE run_id = ? ORDER BY tick, component_id
        """,
        conn,
        params=[run_id],
    )


def _load_events(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, kind, component_id FROM events WHERE run_id = ? ORDER BY tick
        """,
        conn,
        params=[run_id],
    )


def _factors_dataframe(drivers_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in drivers_df.iterrows():
        try:
            data = json.loads(row["coupling_factors_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        data["tick"] = int(row["tick"])
        rows.append(data)
    return pd.DataFrame(rows).set_index("tick") if rows else pd.DataFrame()


def main() -> None:
    st.set_page_config(page_title="Metal Jet Digital Twin", layout="wide")
    st.title("HP Metal Jet S100 — Digital Co-Pilot")
    st.caption(
        "Live telemetry from the coupled simulation engine — health, drivers, "
        "events, coupling and the §3.4 sensor-fault story."
    )

    db_input = st.sidebar.text_input("historian db path", str(_default_db_path()))
    if not Path(db_input).exists():
        st.warning(
            f"No historian DB at `{db_input}`. Run a scenario first:\n\n"
            "`uv run copilot-sim run barcelona-baseline.yaml`"
        )
        return

    conn = _open(db_input)
    run_ids = list(list_run_ids(conn))
    if not run_ids:
        st.warning("Historian is empty.")
        return
    run_id = st.sidebar.selectbox("run_id", run_ids, index=0)

    drivers_df = _load_drivers(conn, run_id)
    component_df = _load_component_health(conn, run_id)
    observed_df = _load_observed_health(conn, run_id)
    events_df = _load_events(conn, run_id)
    factors_df = _factors_dataframe(drivers_df)

    # Chart 1: per-component health
    st.subheader("1. Component health over time")
    if not component_df.empty:
        pivot = component_df.pivot(index="tick", columns="component_id", values="health_index")
        st.line_chart(pivot)

    # Chart 2: driver streams
    st.subheader("2. Driver streams")
    if not drivers_df.empty:
        st.line_chart(
            drivers_df.set_index("tick")[
                [
                    "temperature_stress",
                    "humidity_contamination",
                    "operational_load",
                    "maintenance_level",
                ]
            ]
        )

    # Chart 3: print outcome ribbon (counts per 10-tick bucket)
    st.subheader("3. Print outcome distribution")
    if not drivers_df.empty:
        outcome_counts = (
            drivers_df.assign(bucket=(drivers_df["tick"] // 10) * 10)
            .groupby(["bucket", "print_outcome"])
            .size()
            .unstack(fill_value=0)
        )
        st.bar_chart(outcome_counts)

    # Chart 4: maintenance events
    st.subheader("4. Maintenance events")
    if not events_df.empty:
        events_pivot = events_df.assign(count=1).pivot_table(
            index="tick", columns="kind", values="count", aggfunc="sum", fill_value=0
        )
        st.bar_chart(events_pivot)
        st.dataframe(events_df.tail(20))
    else:
        st.info("No maintenance events.")

    # Chart 5: coupling factors heatmap
    st.subheader("5. Coupling factors over time")
    if not factors_df.empty:
        st.line_chart(factors_df)
        st.caption(
            "powder_spread_quality / cleaning_efficiency are damage proxies that "
            "drop as upstream components age; nozzle_clog_pct rises with humidity."
        )

    # Chart 6: §3.4 sensor-fault story
    st.subheader("6. Sensor-fault vs component-fault — heater true vs observed")
    if not component_df.empty and not observed_df.empty:
        true_heater = component_df[component_df["component_id"] == "heater"][
            ["tick", "health_index"]
        ].rename(columns={"health_index": "true_health"})
        obs_heater = observed_df[observed_df["component_id"] == "heater"][
            ["tick", "observed_health_index", "sensor_note"]
        ].rename(columns={"observed_health_index": "observed_health"})
        merged = true_heater.merge(obs_heater, on="tick").set_index("tick")
        st.line_chart(merged[["true_health", "observed_health"]])
        notes = merged["sensor_note"].value_counts().to_dict()
        st.caption(
            "When sensor_note flips to 'drift' or 'stuck' the observed line "
            "diverges from the true line; that gap is the §3.4 story. "
            f"Note distribution: {notes}"
        )


if __name__ == "__main__":
    main()
