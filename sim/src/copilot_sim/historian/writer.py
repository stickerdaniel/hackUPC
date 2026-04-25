"""HistorianWriter — batched insert into the seven historian tables.

Buffers `executemany` arrays per table and flushes every `flush_every`
ticks (default 50, per the plan's 5-year-runtime budget). `close()`
flushes the tail and commits.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.events import OperatorEvent
from ..domain.state import ObservedPrinterState, PrinterState
from ..drivers_src.environment import Environment

_DRIVERS_SQL = """
INSERT OR REPLACE INTO drivers (
    run_id, tick, ts_iso, sim_time_s,
    temperature_stress, humidity_contamination, operational_load, maintenance_level,
    base_ambient_C, weekly_runtime_hours,
    print_outcome, coupling_factors_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_COMPONENT_STATE_SQL = """
INSERT OR REPLACE INTO component_state (
    run_id, tick, component_id, health_index, status, age_ticks
) VALUES (?, ?, ?, ?, ?, ?)
"""

_METRICS_SQL = """
INSERT OR REPLACE INTO metrics (
    run_id, tick, component_id, metric, value
) VALUES (?, ?, ?, ?, ?)
"""

_OBS_STATE_SQL = """
INSERT OR REPLACE INTO observed_component_state (
    run_id, tick, component_id, observed_health_index, observed_status, sensor_note
) VALUES (?, ?, ?, ?, ?, ?)
"""

_OBS_METRICS_SQL = """
INSERT OR REPLACE INTO observed_metrics (
    run_id, tick, component_id, metric, observed_value, sensor_health
) VALUES (?, ?, ?, ?, ?, ?)
"""

_EVENT_SQL = """
INSERT INTO events (run_id, tick, ts_iso, sim_time_s, kind, component_id, payload_json)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


class HistorianWriter:
    def __init__(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        flush_every: int = 50,
    ) -> None:
        self.conn = conn
        self.run_id = run_id
        self.flush_every = max(1, int(flush_every))
        self._driver_rows: list[tuple] = []
        self._component_state_rows: list[tuple] = []
        self._metric_rows: list[tuple] = []
        self._obs_state_rows: list[tuple] = []
        self._obs_metric_rows: list[tuple] = []
        self._event_rows: list[tuple] = []
        self._tick_buffer = 0

    # --- public API ------------------------------------------------------
    def write_run(
        self,
        scenario: str,
        profile: str,
        dt_seconds: int,
        seed: int,
        notes: str = "",
        horizon_ticks: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO runs (run_id, scenario, profile, dt_seconds, seed,
                started_at_iso, horizon_ticks, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                scenario,
                profile,
                int(dt_seconds),
                int(seed),
                datetime.now(UTC).isoformat(),
                horizon_ticks,
                notes,
            ),
        )
        self.conn.commit()

    def write_tick(
        self,
        true_state: PrinterState,
        observed: ObservedPrinterState,
        drivers: Drivers,
        env: Environment,
        coupling: CouplingContext,
        ts_iso: str,
    ) -> None:
        self._driver_rows.append(
            (
                self.run_id,
                true_state.tick,
                ts_iso,
                true_state.sim_time_s,
                drivers.temperature_stress,
                drivers.humidity_contamination,
                drivers.operational_load,
                drivers.maintenance_level,
                env.base_ambient_C,
                env.weekly_runtime_hours,
                true_state.print_outcome.value,
                json.dumps(dict(coupling.factors)),
            )
        )

        for cid, c in true_state.components.items():
            self._component_state_rows.append(
                (
                    self.run_id,
                    true_state.tick,
                    cid,
                    c.health_index,
                    c.status.value,
                    c.age_ticks,
                )
            )
            for metric, value in c.metrics.items():
                self._metric_rows.append((self.run_id, true_state.tick, cid, metric, float(value)))

        for cid, oc in observed.components.items():
            self._obs_state_rows.append(
                (
                    self.run_id,
                    true_state.tick,
                    cid,
                    oc.observed_health_index,
                    oc.observed_status.value if oc.observed_status is not None else None,
                    oc.sensor_note,
                )
            )
            for metric, value in oc.observed_metrics.items():
                sensor_health = oc.sensor_health.get(metric)
                self._obs_metric_rows.append(
                    (
                        self.run_id,
                        true_state.tick,
                        cid,
                        metric,
                        None if value is None else float(value),
                        None if sensor_health is None else float(sensor_health),
                    )
                )

        self._tick_buffer += 1
        if self._tick_buffer >= self.flush_every:
            self.flush()

    def write_event(self, event: OperatorEvent, ts_iso: str) -> None:
        self._event_rows.append(
            (
                self.run_id,
                event.tick,
                ts_iso,
                event.sim_time_s,
                event.kind.value,
                event.component_id,
                json.dumps(dict(event.payload)),
            )
        )

    def flush(self) -> None:
        cur = self.conn.cursor()
        if self._driver_rows:
            cur.executemany(_DRIVERS_SQL, self._driver_rows)
        if self._component_state_rows:
            cur.executemany(_COMPONENT_STATE_SQL, self._component_state_rows)
        if self._metric_rows:
            cur.executemany(_METRICS_SQL, self._metric_rows)
        if self._obs_state_rows:
            cur.executemany(_OBS_STATE_SQL, self._obs_state_rows)
        if self._obs_metric_rows:
            cur.executemany(_OBS_METRICS_SQL, self._obs_metric_rows)
        if self._event_rows:
            cur.executemany(_EVENT_SQL, self._event_rows)
        self.conn.commit()
        self._driver_rows.clear()
        self._component_state_rows.clear()
        self._metric_rows.clear()
        self._obs_state_rows.clear()
        self._obs_metric_rows.clear()
        self._event_rows.clear()
        self._tick_buffer = 0

    def close(self) -> None:
        self.flush()


def list_run_ids(conn: sqlite3.Connection) -> Iterable[str]:
    cur = conn.cursor()
    cur.execute("SELECT run_id FROM runs ORDER BY started_at_iso DESC")
    return [row[0] for row in cur.fetchall()]
