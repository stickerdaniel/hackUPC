"""Streamlit dashboard for the digital twin demo.

Panels rendered for the selected run:

1. Component health over time (line chart with environmental-event rules).
2. Cascade attribution (top-3 coupling factors at each CRITICAL/FAILED tick).
3. Maintenance load by component (stacked bars by OperatorEventKind).
4. Driver streams (4 brief inputs as sparklines).
5. Status timeline (per-component Gantt of status periods).
6. Recommendation cards (Phase 3 heuristic preview).
7. Proactive alerts feed (Phase 3 autonomy preview).

Launch:
    cd sim
    uv run streamlit run src/copilot_sim/dashboard/streamlit_app.py

Reads the SQLite historian at `data/historian.sqlite` by default; override
in the sidebar.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from copilot_sim.cli import main as cli_main
from copilot_sim.components.registry import COMPONENT_IDS
from copilot_sim.historian import reader
from copilot_sim.historian.connection import open_db
from copilot_sim.historian.writer import list_run_ids

# ──────────────────────────────────────────────────────────────────────────
# Constants — kept in one place so panels stay consistent.
# ──────────────────────────────────────────────────────────────────────────

STATUS_COLOURS: dict[str, str] = {
    "FUNCTIONAL": "#E8E8E8",
    "DEGRADED": "#9E9E9E",
    "CRITICAL": "#5683FF",
    "FAILED": "#1846F5",
}
STATUS_ORDER: tuple[str, ...] = ("FUNCTIONAL", "DEGRADED", "CRITICAL", "FAILED")
# Severity rank for downsampled-bucket reduction (worst wins).
STATUS_SEVERITY: dict[str, int] = {s: i for i, s in enumerate(STATUS_ORDER)}

EVENT_SHAPES: dict[str, str] = {
    "FIX": "triangle-up",
    "REPLACE": "triangle-down",
    "TROUBLESHOOT": "diamond",
}
EVENT_COLOURS: dict[str, str] = {
    "FIX": "#111111",
    "REPLACE": "#1846F5",
    "TROUBLESHOOT": "#9E9E9E",
}

ACCENT_BLUE = "#1846F5"  # primary brand blue — REPLACE markers, recommendation pills.
RULE_GREY = "#5A5A5A"  # subtle dark grey for environmental-event rules.

# Chain text is rendered only when the queried top-3 contains the keys.
CASCADE_CHAINS: dict[str, tuple[set[str], str]] = {
    "heater": (
        {"sensor_bias_c", "control_temp_error_c", "heater_drift_frac"},
        "sensor_bias ↑ → control_temp_error ↑ → heater_drift ↑ → HEATER",
    ),
    "nozzle": (
        {"humidity_contamination_effective", "powder_spread_quality", "nozzle_clog_pct"},
        "humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE",
    ),
    "blade": (
        {"rail_alignment_error", "blade_loss_frac"},
        "rail_alignment ↑ → blade.k_eff ↑ → blade_loss ↑ → BLADE",
    ),
    "rail": (
        {"blade_loss_frac", "rail_alignment_error"},
        "vibration ↑ + blade_loss ↑ → rail_alignment ↑ → RAIL",
    ),
    "cleaning": (
        {"nozzle_clog_pct", "cleaning_efficiency"},
        "nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING",
    ),
    "sensor": (
        {"temperature_stress_effective", "heater_drift_frac", "sensor_bias_c"},
        "temperature_stress ↑ + heater_drift ↑ → sensor_bias ↑ → SENSOR",
    ),
}


# ──────────────────────────────────────────────────────────────────────────
# DB / loaders.
# ──────────────────────────────────────────────────────────────────────────


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
               maintenance_level
        FROM drivers WHERE run_id = ? ORDER BY tick
        """,
        conn,
        params=[run_id],
    )


def _load_component_state(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, component_id, health_index, status
        FROM component_state WHERE run_id = ? ORDER BY tick, component_id
        """,
        conn,
        params=[run_id],
    )


def _load_events(conn, run_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT tick, kind, component_id, payload_json
        FROM events WHERE run_id = ? ORDER BY tick
        """,
        conn,
        params=[run_id],
    )


def _load_environmental_events(conn, run_id: str) -> pd.DataFrame:
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
    return df.groupby("name", as_index=False).first()


# ──────────────────────────────────────────────────────────────────────────
# Helpers.
# ──────────────────────────────────────────────────────────────────────────


def _fmt_pct(x: float) -> str:
    return f"{round(100 * x):d}%"


def _outcome_kpis(conn, run_id: str) -> dict[str, int]:
    return reader.fetch_print_outcome_distribution(conn, run_id)


def _failure_cards(
    conn,
    run_id: str,
    component_df: pd.DataFrame,
    max_cards: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build cascade-attribution cards.

    Returns (visible_cards, overflow_cards). Each card has:
      - component, transitions (dict status -> tick),
      - worst_tick, worst_status, worst_health,
      - factors (list of (name, value) sorted by |value| desc, top 3),
      - chain_text (str | None — only when factors match the template keys).
    """
    transitions = reader.fetch_status_transitions(conn, run_id)
    by_comp: dict[str, dict[str, int]] = {}
    for row in transitions:
        cid = row["component_id"]
        by_comp.setdefault(cid, {}).setdefault(row["status"], int(row["first_tick"]))

    cards: list[dict[str, Any]] = []
    for cid, t_map in by_comp.items():
        worst_status = None
        for status in ("FAILED", "CRITICAL"):
            if status in t_map:
                worst_status = status
                break
        if worst_status is None:
            continue
        worst_tick = int(t_map[worst_status])
        sub = component_df[
            (component_df["component_id"] == cid) & (component_df["tick"] == worst_tick)
        ]
        worst_health = float(sub["health_index"].iloc[0]) if not sub.empty else None

        factors_dict = reader.fetch_coupling_factors_at(conn, run_id, worst_tick)
        sorted_factors = sorted(factors_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
        factor_keys = {name for name, _ in sorted_factors}
        chain = None
        if cid in CASCADE_CHAINS:
            required, template = CASCADE_CHAINS[cid]
            if required & factor_keys:  # at least one template key landed in top-3
                chain = f"{template} {worst_status}"

        cards.append(
            {
                "component": cid,
                "transitions": t_map,
                "worst_tick": worst_tick,
                "worst_status": worst_status,
                "worst_health": worst_health,
                "factors": sorted_factors,
                "chain": chain,
            }
        )

    cards.sort(
        key=lambda c: (
            0 if c["worst_status"] == "FAILED" else 1,
            c["worst_health"] if c["worst_health"] is not None else 1.0,
        )
    )
    return cards[:max_cards], cards[max_cards:]


def _status_segments(component_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-tick status rows into (start_tick, end_tick, status) segments
    per component — one row per contiguous run of the same status.
    """
    rows: list[dict[str, Any]] = []
    if component_df.empty:
        return pd.DataFrame(rows)
    for cid, sub in component_df.sort_values("tick").groupby("component_id"):
        sub = sub.reset_index(drop=True)
        cur_status = str(sub["status"].iloc[0])
        seg_start = int(sub["tick"].iloc[0])
        last_tick = int(sub["tick"].iloc[-1])
        for i in range(1, len(sub)):
            s = str(sub["status"].iloc[i])
            t = int(sub["tick"].iloc[i])
            if s != cur_status:
                rows.append(
                    {
                        "component_id": cid,
                        "status": cur_status,
                        "tick_start": seg_start,
                        "tick_end": t,
                    }
                )
                cur_status = s
                seg_start = t
        rows.append(
            {
                "component_id": cid,
                "status": cur_status,
                "tick_start": seg_start,
                "tick_end": last_tick + 1,
            }
        )
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────
# Render — metadata strip.
# ──────────────────────────────────────────────────────────────────────────


def _render_metadata_strip(run: dict[str, Any], outcomes: dict[str, int]) -> None:
    total = sum(outcomes.values()) or 1
    ok = outcomes.get("OK", 0)
    deg = outcomes.get("QUALITY_DEGRADED", 0)
    halt = outcomes.get("HALTED", 0)

    pill_base = (
        "display:inline-flex;align-items:center;gap:6px;"
        "padding:4px 10px;background:#F4F6FF;border:1px solid #E0E6FF;"
        "border-radius:999px;font-size:11px;line-height:1;"
        "margin-right:6px;margin-bottom:6px;"
    )
    label_style = (
        f"color:{ACCENT_BLUE};font-weight:700;letter-spacing:0.5px;text-transform:uppercase"
    )
    value_style = "color:#111;font-variant-numeric:tabular-nums"

    def pill(label: str, value: str, dot: str | None = None) -> str:
        dot_html = (
            f"<span style='display:inline-block;width:6px;height:6px;border-radius:999px;"
            f"background:{dot}'></span>"
            if dot
            else ""
        )
        return (
            f"<span style='{pill_base}'>"
            f"<span style='{label_style}'>{label}</span>"
            f"{dot_html}"
            f"<span style='{value_style}'>{value}</span>"
            f"</span>"
        )

    pills = [
        pill("Run", f"<code style='font-size:11px;color:#111'>{run['run_id']}</code>"),
        pill("Scenario", run["scenario"]),
        pill("Profile", run.get("profile") or "—"),
        pill("Seed", str(run["seed"])),
        pill("Horizon", str(run.get("horizon_ticks") or "—")),
        pill("dt", f"{run['dt_seconds']}s"),
        pill("OK", _fmt_pct(ok / total), dot="#3FB37F"),
        pill("Degraded", _fmt_pct(deg / total), dot="#E8B341"),
        pill("Halted", _fmt_pct(halt / total), dot="#D45757"),
    ]
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;align-items:center;'>{''.join(pills)}</div>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 1: Component health over time (line chart with env-event rules).
# ──────────────────────────────────────────────────────────────────────────


def _render_panel1(
    component_df: pd.DataFrame,
    env_events_df: pd.DataFrame,
) -> None:
    if component_df.empty:
        st.info("No component-state data for this run.")
        return

    max_tick = int(component_df["tick"].max())
    total_ticks = max_tick + 1

    # Window options in weekly ticks (dt = 1 week, so 1 year = 52 ticks).
    # "all" sizes the window to cover the full run regardless of length.
    window_options: list[tuple[str, int]] = [
        ("6mo", 26),
        ("1y", 52),
        ("3y", 156),
        ("all", total_ticks),
    ]
    label_to_size = dict(window_options)

    # One-time session-state init. Default to 1y if the run is long enough,
    # otherwise step down through 6mo before showing everything.
    if "panel1_window_label" not in st.session_state:
        if max_tick >= 52:
            default_label = "1y"
        elif max_tick >= 26:
            default_label = "6mo"
        else:
            default_label = "all"
        st.session_state["panel1_window_label"] = default_label
    if "panel1_start_tick" not in st.session_state:
        st.session_state["panel1_start_tick"] = 0

    # Controls row above the chart, right-aligned. Spacer column on the
    # left pushes the controls toward the chart's right edge. Inside the
    # control column, arrows flank the segmented control so the panning
    # controls bracket the range buttons (← [6mo|1y|3y|all] →).
    _, ctrl_col = st.columns([5, 4])
    with ctrl_col:
        prev_col, range_col, next_col = st.columns(
            [1, 5, 1], vertical_alignment="bottom"
        )
        # Compute disabled state from the CURRENT (pre-click) session state
        # so the button visuals are right after the previous interaction.
        cur_start = int(st.session_state["panel1_start_tick"])
        cur_window = label_to_size.get(
            st.session_state.get("panel1_window_label", "1y"), 52
        )
        at_left = cur_start <= 0
        at_right = (cur_start + cur_window) >= total_ticks
        with prev_col:
            prev_clicked = st.button(
                "←", key="panel1_prev", disabled=at_left, help="Pan earlier"
            )
        with range_col:
            window_label = st.segmented_control(
                "range",
                options=[opt[0] for opt in window_options],
                key="panel1_window_label",
                label_visibility="collapsed",
            )
        with next_col:
            next_clicked = st.button(
                "→", key="panel1_next", disabled=at_right, help="Pan later"
            )

    # Resolve window size and pan step. `window_label` is None on first render
    # if the user has just deselected the segmented control; fall back to the
    # session-state default.
    if window_label is None:
        window_label = st.session_state.get("panel1_window_label", "1y")
    window_size = label_to_size[window_label]
    pan_step = max(1, window_size // 2)

    start_tick = int(st.session_state["panel1_start_tick"])
    if prev_clicked:
        start_tick -= pan_step
    if next_clicked:
        start_tick += pan_step
    # Clamp to valid range — also handles run changes (different total_ticks)
    # and window-size changes (e.g. zooming out from 1y to 5y).
    upper_start = max(0, total_ticks - window_size)
    start_tick = max(0, min(start_tick, upper_start))
    st.session_state["panel1_start_tick"] = start_tick
    end_tick = start_tick + window_size  # exclusive

    # Filter component_df + env_events_df to the visible window.
    visible_df = component_df[
        (component_df["tick"] >= start_tick) & (component_df["tick"] < end_tick)
    ].copy()
    visible_df["component_id"] = pd.Categorical(
        visible_df["component_id"], categories=list(COMPONENT_IDS)
    )
    visible_env = (
        env_events_df[
            (env_events_df["tick"] >= start_tick) & (env_events_df["tick"] < end_tick)
        ]
        if not env_events_df.empty
        else env_events_df
    )

    # Lock the x-axis domain to the chosen window so panning feels stable
    # (the chart doesn't auto-rescale when only one component has data in
    # the window after filtering).
    x_domain = [start_tick, min(end_tick, total_ticks) - 1]

    health_chart = (
        alt.Chart(visible_df)
        .mark_line(strokeWidth=1.6)
        .encode(
            x=alt.X(
                "tick:Q",
                title="tick",
                scale=alt.Scale(domain=x_domain),
                axis=alt.Axis(labelFontSize=10, titleFontSize=10),
            ),
            y=alt.Y(
                "health_index:Q",
                title="health index",
                scale=alt.Scale(domain=[0.0, 1.0]),
                axis=alt.Axis(labelFontSize=10, titleFontSize=10),
            ),
            color=alt.Color(
                "component_id:N",
                sort=list(COMPONENT_IDS),
                legend=alt.Legend(
                    orient="top",
                    title=None,
                    labelFontSize=11,
                    symbolType="circle",
                    columns=6,
                ),
            ),
            tooltip=[
                "component_id",
                alt.Tooltip("tick:Q", title="tick"),
                alt.Tooltip("health_index:Q", title="health", format=".3f"),
                "status",
            ],
        )
        .properties(height=320)
    )

    layers: list[alt.Chart] = [health_chart]

    if not visible_env.empty:
        env_rule = (
            alt.Chart(visible_env)
            .mark_rule(color=RULE_GREY, strokeDash=[3, 3], strokeWidth=1, opacity=0.85)
            .encode(x="tick:Q", tooltip=["name", "tick"])
        )
        env_label = (
            alt.Chart(visible_env)
            .mark_text(
                align="left",
                baseline="top",
                dx=4,
                dy=2,
                color=RULE_GREY,
                fontSize=10,
                fontWeight=600,
            )
            .encode(x="tick:Q", y=alt.value(0), text="name:N")
        )
        layers.extend([env_rule, env_label])

    composed = (
        alt.layer(*layers)
        .configure_view(stroke=None)
        .configure_axis(grid=True, gridColor="#EFEFEF", domainColor="#111111", tickColor="#111111")
    )
    st.altair_chart(composed, width="stretch")

    # Caption — current window + env-event legend if any are visible.
    visible_last = min(end_tick - 1, max_tick)
    range_caption = (
        f"showing ticks {start_tick}–{visible_last} of {total_ticks} total"
    )
    if not visible_env.empty:
        st.caption(
            f"{range_caption} · grey dashed rules mark environmental events "
            f"from the scenario (chaos overlays — earthquake, HVAC failure, "
            f"holiday, ...)."
        )
    else:
        st.caption(range_caption)


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 2: Cascade attribution.
# ──────────────────────────────────────────────────────────────────────────


def _status_stepper_html(transitions: dict[str, int]) -> str:
    """Visual stepper: coloured status pills connected by arrows, each with its tick."""
    steps_present = [s for s in STATUS_ORDER if s in transitions]
    nodes: list[str] = []
    for s in steps_present:
        dot = STATUS_COLOURS[s]
        text_color = "#FFF" if s in {"CRITICAL", "FAILED"} else "#111"
        nodes.append(
            f"<span style='display:inline-flex;align-items:center;gap:5px;"
            f"padding:3px 9px;background:{dot};color:{text_color};"
            f"border:1px solid #DDD;border-radius:999px;"
            f"font-size:10px;font-weight:700;letter-spacing:0.5px'>"
            f"{s}"
            f"<span style='opacity:0.85;font-weight:600;font-variant-numeric:tabular-nums'>"
            f"t={transitions[s]}</span></span>"
        )
    arrow = "<span style='color:#BBB;font-size:13px;margin:0 4px'>→</span>"
    return f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:2px'>{arrow.join(nodes)}</div>"


def _render_cascade_card(card: dict[str, Any]) -> None:
    cid = card["component"].upper()
    transitions = card["transitions"]
    st.markdown(
        f"<div style='font-weight:700;font-size:13px;color:#111;"
        f"letter-spacing:0.4px;margin-bottom:6px'>{cid}</div>"
        f"{_status_stepper_html(transitions)}",
        unsafe_allow_html=True,
    )

    if not card["factors"]:
        st.caption("Coupling factors not available at this tick.")
        return

    bars_df = pd.DataFrame([{"factor": name, "value": value} for name, value in card["factors"]])
    bars_df["abs_value"] = bars_df["value"].abs()
    bar_chart = (
        alt.Chart(bars_df)
        .mark_bar(color=ACCENT_BLUE, height=14)
        .encode(
            x=alt.X(
                "abs_value:Q",
                title=None,
                axis=alt.Axis(labelFontSize=9, tickCount=4),
            ),
            y=alt.Y("factor:N", sort="-x", title=None, axis=alt.Axis(labelFontSize=10)),
            tooltip=[
                alt.Tooltip("factor:N"),
                alt.Tooltip("value:Q", format=".3f"),
            ],
        )
        .properties(height=80)
    )
    text = (
        alt.Chart(bars_df)
        .mark_text(align="left", dx=4, color="#111111", fontSize=10)
        .encode(
            x="abs_value:Q",
            y=alt.Y("factor:N", sort="-x"),
            text=alt.Text("value:Q", format=".3f"),
        )
    )
    st.altair_chart((bar_chart + text).configure_view(stroke=None), width="stretch")
    if card["chain"]:
        st.caption(card["chain"])


def _render_panel2(cards: list[dict[str, Any]], overflow: list[dict[str, Any]]) -> None:
    if not cards and not overflow:
        st.info("No CRITICAL/FAILED transitions in this run.")
        return
    for card in cards:
        _render_cascade_card(card)
        st.markdown("")
    if overflow:
        with st.expander(f"Other transitions ({len(overflow)})"):
            for card in overflow:
                _render_cascade_card(card)
                st.markdown("")


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 4: Maintenance load by component (stacked bars).
# ──────────────────────────────────────────────────────────────────────────


def _render_panel4(events_df: pd.DataFrame) -> None:
    if events_df.empty:
        st.info("No maintenance events in this run.")
        return

    counts = events_df["kind"].value_counts().to_dict()
    fix = counts.get("FIX", 0)
    rep = counts.get("REPLACE", 0)
    tro = counts.get("TROUBLESHOOT", 0)
    total = len(events_df)
    st.markdown(
        f"<div style='font-size:11px;font-weight:600;color:#111;letter-spacing:0.4px;margin-bottom:6px'>"
        f"FIX {fix}  ·  REPLACE {rep}  ·  TROUBLESHOOT {tro}  ·  TOTAL {total}</div>",
        unsafe_allow_html=True,
    )

    ev = events_df.copy()
    ev = ev[ev["component_id"].isin(COMPONENT_IDS)]
    if ev.empty:
        st.info("Events recorded but none tied to a tracked component.")
        return

    counts_by = ev.groupby(["component_id", "kind"], observed=True).size().reset_index(name="count")
    counts_by["component_id"] = pd.Categorical(
        counts_by["component_id"], categories=list(COMPONENT_IDS)
    )
    counts_by["kind"] = pd.Categorical(counts_by["kind"], categories=list(EVENT_COLOURS.keys()))

    bars = (
        alt.Chart(counts_by)
        .mark_bar(height=22)
        .encode(
            y=alt.Y(
                "component_id:N",
                sort=list(COMPONENT_IDS),
                title=None,
                axis=alt.Axis(labelFontSize=11, labelFontWeight=600, ticks=False),
            ),
            x=alt.X(
                "count:Q",
                stack="zero",
                title="event count",
                axis=alt.Axis(labelFontSize=10, titleFontSize=10),
            ),
            color=alt.Color(
                "kind:N",
                scale=alt.Scale(
                    domain=list(EVENT_COLOURS.keys()),
                    range=list(EVENT_COLOURS.values()),
                ),
                legend=alt.Legend(
                    orient="top",
                    title=None,
                    labelFontSize=11,
                    symbolType="square",
                ),
            ),
            tooltip=["component_id", "kind", "count"],
        )
        .properties(height=max(180, 36 * len(COMPONENT_IDS)))
    )

    totals = counts_by.groupby("component_id", observed=True)["count"].sum().reset_index()
    total_labels = (
        alt.Chart(totals)
        .mark_text(align="left", dx=4, color="#111", fontSize=11, fontWeight=600)
        .encode(
            y=alt.Y("component_id:N", sort=list(COMPONENT_IDS)),
            x="count:Q",
            text=alt.Text("count:Q", format="d"),
        )
    )

    st.altair_chart(
        (bars + total_labels)
        .configure_view(stroke=None)
        .configure_axis(grid=True, gridColor="#EFEFEF", domainColor="#111111"),
        width="stretch",
    )

    with st.expander(f"Event log (last 50 of {total})", expanded=False):
        st.dataframe(events_df.sort_values("tick", ascending=False).head(50))


# ──────────────────────────────────────────────────────────────────────────
# Main.
# ──────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 5: Driver streams (4 brief inputs).
# ──────────────────────────────────────────────────────────────────────────


def _driver_sparkline(df: pd.DataFrame, field: str, label: str, value_fmt: str) -> alt.Chart:
    if df.empty:
        return alt.Chart(pd.DataFrame({"tick": [0], field: [0.0]})).mark_point()
    latest = float(df[field].iloc[-1])
    last_tick = int(df["tick"].iloc[-1])
    line = (
        alt.Chart(df)
        .mark_line(color="#111", strokeWidth=1.4)
        .encode(
            x=alt.X("tick:Q", axis=None),
            y=alt.Y(f"{field}:Q", axis=None, scale=alt.Scale(zero=False, nice=False)),
            tooltip=[
                alt.Tooltip("tick:Q", title="tick"),
                alt.Tooltip(f"{field}:Q", title=field, format=".3f"),
            ],
        )
        .properties(
            height=46,
            title=alt.TitleParams(
                label.upper(),
                fontSize=10,
                fontWeight=700,
                color="#111",
                anchor="start",
                offset=2,
            ),
        )
    )
    label_chart = (
        alt.Chart(pd.DataFrame({"tick": [last_tick], "v": [latest]}))
        .mark_text(
            align="right",
            baseline="middle",
            dx=-2,
            color=ACCENT_BLUE,
            fontSize=12,
            fontWeight=700,
        )
        .encode(x="tick:Q", y=alt.value(28), text=alt.Text("v:Q", format=value_fmt))
    )
    return line + label_chart


def _render_panel5(drivers_df: pd.DataFrame) -> None:
    if drivers_df.empty:
        st.info("No driver data for this run.")
        return
    sparks = alt.vconcat(
        _driver_sparkline(drivers_df, "temperature_stress", "Temperature stress", ".0%"),
        _driver_sparkline(drivers_df, "humidity_contamination", "Humidity contamination", ".0%"),
        _driver_sparkline(drivers_df, "operational_load", "Operational load", ".0%"),
        _driver_sparkline(drivers_df, "maintenance_level", "Maintenance level", ".0%"),
        spacing=10,
    )
    composed = (
        sparks.configure_view(stroke=None)
        .configure_axis(grid=False, domainColor="#DDD")
        .configure_concat(spacing=10)
    )
    st.altair_chart(composed, width="stretch")
    st.caption(
        "Four engine inputs every tick. Right-edge value is the latest reading; "
        "all four are wired into the coupled engine on every step."
    )


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 6: Status timeline (per-component Gantt of status periods).
# ──────────────────────────────────────────────────────────────────────────


def _render_panel6(component_df: pd.DataFrame) -> None:
    if component_df.empty:
        st.info("No component-state data for this run.")
        return
    segs = _status_segments(component_df)
    if segs.empty:
        st.info("No status segments to display.")
        return
    segs = segs.assign(
        component_id=pd.Categorical(segs["component_id"], categories=list(COMPONENT_IDS)),
        status=pd.Categorical(segs["status"], categories=list(STATUS_ORDER)),
    )

    bars = (
        alt.Chart(segs)
        .mark_bar(height=20, stroke="#FFF", strokeWidth=1)
        .encode(
            x=alt.X(
                "tick_start:Q",
                title="tick",
                axis=alt.Axis(labelFontSize=10, titleFontSize=10),
            ),
            x2="tick_end:Q",
            y=alt.Y(
                "component_id:N",
                sort=list(COMPONENT_IDS),
                title=None,
                axis=alt.Axis(labelFontSize=11, labelFontWeight=600, ticks=False),
            ),
            color=alt.Color(
                "status:N",
                scale=alt.Scale(
                    domain=list(STATUS_ORDER),
                    range=[STATUS_COLOURS[s] for s in STATUS_ORDER],
                ),
                legend=alt.Legend(
                    orient="top",
                    title=None,
                    labelFontSize=11,
                    symbolType="square",
                ),
            ),
            tooltip=[
                "component_id",
                "status",
                alt.Tooltip("tick_start:Q", title="from"),
                alt.Tooltip("tick_end:Q", title="to"),
            ],
        )
        .properties(height=max(180, 32 * len(COMPONENT_IDS)))
    )
    st.altair_chart(
        bars.configure_view(stroke=None).configure_axis(
            grid=True, gridColor="#EFEFEF", domainColor="#111111"
        ),
        width="stretch",
    )
    st.caption(
        "Same data as the line chart above, painted as continuous status periods. "
        "Look for the moment each row turns blue — that's a CRITICAL crossing."
    )


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 7: Co-Pilot recommendations (Phase 3 / Intelligence preview).
# ──────────────────────────────────────────────────────────────────────────

# (status, severity_dot, recommendation verb, action_label)
_PHASE3_RULES: dict[str, tuple[str, str, str]] = {
    "DEGRADED": ("#E8B341", "Watch closely", "WATCH"),
    "CRITICAL": ("#5683FF", "Schedule a FIX in the next maintenance window", "SCHEDULE FIX"),
    "FAILED": ("#1846F5", "Replace immediately — print outcomes are degrading", "REPLACE NOW"),
}


def _render_panel7(
    conn,
    run_id: str,
    component_df: pd.DataFrame,
) -> None:
    cards, overflow = _failure_cards(conn, run_id, component_df, max_cards=6)
    all_cards = cards + overflow
    if not all_cards:
        st.info("No CRITICAL/FAILED components to recommend on.")
        return

    for card in all_cards:
        cid = card["component"].upper()
        status = card["worst_status"]
        dot, recommendation, action = _PHASE3_RULES.get(status, ("#9E9E9E", "Monitor", "MONITOR"))
        health = card["worst_health"]
        health_str = f"{health:.2f}" if health is not None else "—"
        top_factor = (
            f"{card['factors'][0][0]} = {card['factors'][0][1]:.3f}"
            if card["factors"]
            else "factors not recorded at this tick"
        )

        st.markdown(
            f"<div style='border:1px solid #E8E8E8;border-radius:8px;padding:10px 12px;"
            f"margin-bottom:8px;background:#FFF'>"
            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px'>"
            f"<span style='display:inline-block;width:8px;height:8px;border-radius:999px;"
            f"background:{dot}'></span>"
            f"<span style='font-weight:700;font-size:13px;color:#111;letter-spacing:0.3px'>"
            f"{cid}</span>"
            f"<span style='font-size:10px;color:#888;letter-spacing:0.4px;text-transform:uppercase'>"
            f"@ t={card['worst_tick']}  ·  health {health_str}  ·  status {status}</span>"
            f"</div>"
            f"<div style='color:#444;font-size:12px;margin-bottom:6px;line-height:1.5'>"
            f"<b>Why:</b> top driver was <code style='color:#111;background:#F4F6FF;"
            f"padding:1px 5px;border-radius:3px;font-size:11px'>{top_factor}</code>. "
            f"{card['chain'] or 'Cascade chain not recoverable from the recorded factors.'}</div>"
            f"<div style='display:flex;align-items:center;gap:8px;flex-wrap:wrap'>"
            f"<span style='font-size:10px;color:#666;letter-spacing:0.4px;text-transform:uppercase'>"
            f"Suggested next step</span>"
            f"<span style='display:inline-flex;align-items:center;gap:5px;"
            f"padding:2px 9px;background:#FFF;color:{ACCENT_BLUE};"
            f"border:1px solid {ACCENT_BLUE};border-radius:4px;"
            f"font-size:11px;font-weight:700;letter-spacing:0.5px'>"
            f"<span style='display:inline-block;width:5px;height:5px;border-radius:999px;"
            f"background:{ACCENT_BLUE}'></span>{action}</span>"
            f"<span style='color:#444;font-size:12px'>· {recommendation}</span>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ──────────────────────────────────────────────────────────────────────────
# Render — Panel 8: Proactive alerts feed (Phase 3 / Autonomy preview).
# ──────────────────────────────────────────────────────────────────────────

_ALERT_GLYPH: dict[str, str] = {
    "FUNCTIONAL": "○",
    "DEGRADED": "◐",
    "CRITICAL": "◑",
    "FAILED": "●",
}
_ALERT_DOT: dict[str, str] = {
    "FUNCTIONAL": "#9E9E9E",
    "DEGRADED": "#E8B341",
    "CRITICAL": "#5683FF",
    "FAILED": "#1846F5",
}


def _render_panel8(conn, run_id: str) -> None:
    transitions = reader.fetch_status_transitions(conn, run_id)
    # Drop FUNCTIONAL "transitions" (every component starts there) — alerts only fire on degradation.
    transitions = [t for t in transitions if t["status"] != "FUNCTIONAL"]
    transitions.sort(key=lambda r: (int(r["first_tick"]), r["component_id"]))

    if not transitions:
        st.info("No status transitions raised during this run.")
        return

    rows_html = []
    for t in transitions:
        cid = t["component_id"]
        status = t["status"]
        tick = int(t["first_tick"])
        glyph = _ALERT_GLYPH.get(status, "•")
        dot = _ALERT_DOT.get(status, "#9E9E9E")
        factors = reader.fetch_coupling_factors_at(conn, run_id, tick)
        top = ""
        if factors:
            top_name, top_value = max(factors.items(), key=lambda kv: abs(kv[1]))
            top = (
                f"<span style='color:#666'>· top driver </span>"
                f"<code style='color:#111;background:#F4F6FF;padding:1px 5px;border-radius:3px;"
                f"font-size:11px'>{top_name} = {top_value:.3f}</code>"
            )
        rows_html.append(
            f"<div style='display:flex;align-items:center;gap:10px;padding:7px 10px;"
            f"border-bottom:1px solid #F2F2F2'>"
            f"<span style='color:{dot};font-size:14px;width:14px;text-align:center'>{glyph}</span>"
            f"<span style='font-size:10px;color:#888;letter-spacing:0.4px;width:62px'>"
            f"TICK {tick}</span>"
            f"<span style='font-weight:700;font-size:12px;color:#111;letter-spacing:0.3px'>"
            f"{cid.upper()}</span>"
            f"<span style='font-size:10px;color:#888;letter-spacing:0.4px'>→</span>"
            f"<span style='font-size:11px;font-weight:700;color:{dot};letter-spacing:0.4px'>"
            f"{status}</span>"
            f"{top}"
            f"</div>"
        )

    st.markdown(
        f"<div style='border:1px solid #E8E8E8;border-radius:8px;background:#FFF;"
        f"max-height:360px;overflow-y:auto'>{''.join(rows_html)}</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"{len(transitions)} alerts. Each row is what the proactive agent would have raised "
        "the moment a component crossed a status threshold."
    )


def _section_header(eyebrow: str, title: str) -> None:
    st.markdown(
        f"<div style='font-size:11px;font-weight:600;color:{ACCENT_BLUE};"
        f"letter-spacing:0.6px;text-transform:uppercase;margin-top:18px'>{eyebrow}</div>"
        f"<div style='font-size:20px;font-weight:700;color:#111;letter-spacing:-0.2px;"
        f"margin-top:2px;margin-bottom:8px'>{title}</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="HP CoPilot Twin — hpct.work", layout="wide")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;"
        f"font-size:11px;letter-spacing:0.6px;text-transform:uppercase;'>"
        f"<span style='color:{ACCENT_BLUE};font-weight:700'>hpct.work</span>"
        f"<span style='color:#BBB'>·</span>"
        f"<span style='color:#666;font-weight:600'>HP Metal Jet S100 digital twin</span>"
        f"</div>"
        f"<div style='display:flex;align-items:baseline;gap:12px;margin-top:4px;margin-bottom:6px;'>"
        f"<h1 style='margin:0;font-weight:700;color:#111;letter-spacing:-0.6px;font-size:36px;'>"
        f"HP <span style='color:{ACCENT_BLUE}'>Co</span>Pilot "
        f"<span style='font-weight:500;color:#444'>Twin</span></h1>"
        f"<span style='display:inline-flex;align-items:center;gap:6px;"
        f"padding:3px 10px;background:#111;color:#FFF;border-radius:999px;"
        f"font-size:10px;font-weight:700;letter-spacing:0.6px;text-transform:uppercase;'>"
        f"<span style='display:inline-block;width:6px;height:6px;border-radius:999px;"
        f"background:#3FB37F'></span>Operator</span>"
        f"</div>"
        f"<div style='color:#666;font-size:12px;margin-bottom:14px;max-width:760px;line-height:1.5'>"
        f"Operator dashboard for the coupled simulation engine — drivers, status decay, "
        f"cascade attribution, sensor trust, and operator response, sourced from the "
        f"SQLite historian for the selected run.</div>",
        unsafe_allow_html=True,
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
    run_ids = list(list_run_ids(conn))
    if not run_ids:
        st.warning("Historian is empty.")
        return
    run_id = st.sidebar.selectbox("run_id", run_ids, index=0)

    run_meta = reader.fetch_run(conn, run_id)
    if run_meta is None:
        st.error(f"run_id not found: {run_id}")
        return
    outcomes = _outcome_kpis(conn, run_id)
    drivers_df = _load_drivers(conn, run_id)
    component_df = _load_component_state(conn, run_id)
    events_df = _load_events(conn, run_id)
    env_events_df = _load_environmental_events(conn, run_id)

    _render_metadata_strip(run_meta, outcomes)
    st.markdown("---")

    # Panel 1 — Component health over time.
    _section_header("Phase 1 / coupled engine", "Component health over time")
    _render_panel1(component_df, env_events_df)
    st.markdown("---")

    # Panel 2 — Cascade attribution (full width now that panel 3 is gone).
    _section_header("Phase 1 / failure explanation", "Cascade attribution")
    cards, overflow = _failure_cards(conn, run_id, component_df)
    _render_panel2(cards, overflow)
    st.markdown("---")

    # Panel 4 — Maintenance load by component.
    _section_header("Phase 2 / operator response", "Maintenance load by component")
    _render_panel4(events_df)
    st.markdown("---")

    # Bonus row — extra options the team can pick from when finalising the demo.
    st.markdown(
        f"<div style='font-size:11px;font-weight:700;color:{ACCENT_BLUE};"
        f"letter-spacing:0.6px;text-transform:uppercase;margin-top:6px;margin-bottom:6px'>"
        f"Also available · pick four for the demo</div>",
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns(2, gap="large")
    with col_a:
        _section_header("Phase 2 / brief inputs", "Driver streams")
        _render_panel5(drivers_df)
    with col_b:
        _section_header("Phase 1 / status decay", "Status timeline")
        _render_panel6(component_df)
    st.markdown("---")

    # Phase 3 preview row — AI co-pilot framing built on real historian data.
    st.markdown(
        f"<div style='font-size:11px;font-weight:700;color:{ACCENT_BLUE};"
        f"letter-spacing:0.6px;text-transform:uppercase;margin-top:6px;margin-bottom:6px'>"
        f"Phase 3 preview · Reliability · Intelligence · Autonomy</div>",
        unsafe_allow_html=True,
    )
    col_c, col_d = st.columns(2, gap="large")
    with col_c:
        _section_header("Phase 3 / heuristic preview", "Recommendation cards")
        st.caption(
            "Read-only insight cards — rule-based today (status → suggested action lookup); "
            "the LLM agent in Phase 3 will replace the rule with a generated rationale."
        )
        _render_panel7(conn, run_id, component_df)
    with col_d:
        _section_header("Phase 3 / autonomy preview", "Proactive alerts feed")
        st.caption(
            "Notification-style log of every status crossing the engine produced — "
            "what the autonomous agent would have raised in real time."
        )
        _render_panel8(conn, run_id)


if __name__ == "__main__":
    main()
