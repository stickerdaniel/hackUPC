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

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from copilot_sim.cli import main as cli_main
from copilot_sim.historian.connection import open_db
from copilot_sim.historian.writer import list_run_ids


def _default_db_path() -> Path:
    return Path("data/historian.sqlite")


def _scenarios_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "scenarios"


def _available_scenarios() -> list[Path]:
    return sorted(_scenarios_dir().glob("*.yaml"))


def _run_scenario(scenario_path: Path, db_path: Path) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        rc = cli_main(["run", str(scenario_path), "--db-path", str(db_path)])
    return rc, buffer.getvalue()


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


def _load_environmental_events(conn, run_id: str) -> pd.DataFrame:
    """Distinct from operator events — narrative one-offs from the YAML.

    Multi-tick events have one row per active tick; we deduplicate by
    name for display so an "earthquake duration: 3" shows up as one
    rule, not three.
    """
    df = pd.read_sql_query(
        """
        SELECT tick, name, payload_json FROM environmental_events
        WHERE run_id = ? ORDER BY tick
        """,
        conn,
        params=[run_id],
    )
    if df.empty:
        return df
    # Show one mark per (name, first-tick) — the start of each event window.
    return df.groupby("name", as_index=False).first()


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
    scenarios = _available_scenarios()
    if scenarios:
        selected_scenario = st.sidebar.selectbox(
            "scenario to run",
            scenarios,
            format_func=lambda path: path.name,
            index=0,
        )
        if st.sidebar.button("Run selected scenario", width="stretch"):
            db_path = Path(db_input)
            with st.spinner(f"Running {selected_scenario.name}..."):
                rc, output = _run_scenario(selected_scenario, db_path)
            st.session_state["last_run_output"] = output
            if rc == 0:
                st.session_state["last_run_scenario"] = selected_scenario.name
                st.rerun()
            st.error(f"Scenario run failed with exit code {rc}.")
            if output:
                st.code(output)
    else:
        st.sidebar.info("No scenarios found in sim/scenarios.")

    if st.session_state.get("last_run_output"):
        with st.expander("Last scenario run output", expanded=False):
            st.code(st.session_state["last_run_output"])

    if not Path(db_input).exists():
        st.warning(
            f"No historian DB at `{db_input}` yet. Choose a scenario on the left and run it."
        )
        return

    conn = open_db(db_input)
    try:
        run_ids = list(list_run_ids(conn))
        if not run_ids:
            st.warning("Historian is empty.")
            return
        run_id = st.sidebar.selectbox("run_id", run_ids, index=0)

        drivers_df = _load_drivers(conn, run_id)
        component_df = _load_component_health(conn, run_id)
        observed_df = _load_observed_health(conn, run_id)
        events_df = _load_events(conn, run_id)
        env_events_df = _load_environmental_events(conn, run_id)
        factors_df = _factors_dataframe(drivers_df)
    finally:
        conn.close()

    # Chart 1: per-component health (Altair so we can overlay event rules)
    st.subheader("1. Component health over time")
    if not component_df.empty:
        health_chart = (
            alt.Chart(component_df)
            .mark_line()
            .encode(
                x=alt.X("tick:Q", title="tick"),
                y=alt.Y("health_index:Q", scale=alt.Scale(domain=[0.0, 1.0])),
                color=alt.Color("component_id:N", legend=alt.Legend(title="component")),
                tooltip=["component_id", "tick", "health_index", "status"],
            )
        )
        if not env_events_df.empty:
            rule = (
                alt.Chart(env_events_df)
                .mark_rule(color="firebrick", strokeDash=[4, 4])
                .encode(x="tick:Q", tooltip=["name", "tick"])
            )
            label = (
                alt.Chart(env_events_df)
                .mark_text(align="left", baseline="top", dx=4, dy=2, color="firebrick", fontSize=11)
                .encode(x="tick:Q", y=alt.value(0), text="name:N")
            )
            health_chart = health_chart + rule + label
        st.altair_chart(health_chart.properties(height=320), use_container_width=True)
        if not env_events_df.empty:
            st.caption("Red dashed lines mark environmental events.")
            st.dataframe(
                env_events_df[["tick", "name", "payload_json"]].rename(
                    columns={"payload_json": "payload"}
                )
            )

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
