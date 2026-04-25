"""Historian read helpers used by the CLI inspect command and the dashboard.

Read-only queries on the seven tables. Each function returns plain Python
data structures — list of dicts or pandas-friendly tuples — so callers
can decide whether to render them as a CLI table, a Streamlit chart,
or a JSON dump.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any


def fetch_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT run_id, scenario, profile, dt_seconds, seed, started_at_iso,
               horizon_ticks, notes
        FROM runs WHERE run_id = ?
        """,
        (run_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = (
        "run_id",
        "scenario",
        "profile",
        "dt_seconds",
        "seed",
        "started_at_iso",
        "horizon_ticks",
        "notes",
    )
    return dict(zip(keys, row, strict=True))


def fetch_final_component_states(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cs.component_id, cs.tick, cs.health_index, cs.status, cs.age_ticks
        FROM component_state cs
        WHERE cs.run_id = ?
          AND cs.tick = (SELECT MAX(tick) FROM component_state WHERE run_id = ?)
        ORDER BY cs.component_id
        """,
        (run_id, run_id),
    )
    keys = ("component_id", "tick", "health_index", "status", "age_ticks")
    return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def fetch_status_transitions(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """First tick each (component_id, status) appears, in tick order.

    Used by `inspect --failure-analysis` to answer "when did each
    component first hit DEGRADED / CRITICAL / FAILED?".
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT component_id, status, MIN(tick) AS first_tick
        FROM component_state
        WHERE run_id = ?
        GROUP BY component_id, status
        ORDER BY component_id, first_tick
        """,
        (run_id,),
    )
    keys = ("component_id", "status", "first_tick")
    return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def fetch_coupling_factors_at(conn: sqlite3.Connection, run_id: str, tick: int) -> dict[str, float]:
    cur = conn.cursor()
    cur.execute(
        "SELECT coupling_factors_json FROM drivers WHERE run_id = ? AND tick = ?",
        (run_id, tick),
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        return {}
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return {}
    return {k: float(v) for k, v in data.items()}


def fetch_print_outcome_distribution(conn: sqlite3.Connection, run_id: str) -> dict[str, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT print_outcome, COUNT(*) FROM drivers
        WHERE run_id = ? GROUP BY print_outcome
        """,
        (run_id,),
    )
    return {row[0]: int(row[1]) for row in cur.fetchall()}


def fetch_event_count(conn: sqlite3.Connection, run_id: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,))
    return int(cur.fetchone()[0])


def fetch_health_timeseries(
    conn: sqlite3.Connection, run_id: str, component_id: str
) -> Iterable[tuple[int, float]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tick, health_index FROM component_state
        WHERE run_id = ? AND component_id = ? ORDER BY tick
        """,
        (run_id, component_id),
    )
    return [(int(t), float(h)) for t, h in cur.fetchall()]


def fetch_environmental_events(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    """All `environmental_events` rows for the run, in tick order."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tick, ts_iso, sim_time_s, name, payload_json
        FROM environmental_events WHERE run_id = ? ORDER BY tick, event_seq
        """,
        (run_id,),
    )
    keys = ("tick", "ts_iso", "sim_time_s", "name", "payload_json")
    rows = [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]
    for row in rows:
        try:
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            row["payload"] = {}
    return rows


def fetch_environmental_event_count(conn: sqlite3.Connection, run_id: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM environmental_events WHERE run_id = ?", (run_id,))
    return int(cur.fetchone()[0])


def fetch_environment_at(conn: sqlite3.Connection, run_id: str, tick: int) -> dict[str, Any]:
    """Per-tick Environment snapshot from the `environment_json` column.

    Returns an empty dict when the row is missing or the JSON is bad.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT environment_json FROM drivers WHERE run_id = ? AND tick = ?",
        (run_id, tick),
    )
    row = cur.fetchone()
    if row is None or row[0] is None:
        return {}
    try:
        return dict(json.loads(row[0]))
    except json.JSONDecodeError:
        return {}
