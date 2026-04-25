"""Smoke tests for the SQLite historian (schema + writer + reader)."""

from __future__ import annotations

from pathlib import Path

from copilot_sim.domain.drivers import Drivers
from copilot_sim.domain.enums import OperatorEventKind
from copilot_sim.domain.events import OperatorEvent
from copilot_sim.drivers_src.environment import Environment
from copilot_sim.engine.engine import Engine, initial_state
from copilot_sim.historian import reader
from copilot_sim.historian.connection import open_db
from copilot_sim.historian.run_id import mint_run_id
from copilot_sim.historian.writer import HistorianWriter


def _drivers() -> Drivers:
    return Drivers(
        temperature_stress=0.30,
        humidity_contamination=0.30,
        operational_load=0.50,
        maintenance_level=0.20,
    )


def _env() -> Environment:
    return Environment(
        base_ambient_C=22.0,
        amplitude_C=8.0,
        weekly_runtime_hours=60.0,
        vibration_level=0.10,
        cumulative_cleanings=0,
        hours_since_maintenance=0.0,
        start_stop_cycles=0,
    )


def test_historian_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "historian.sqlite"
    conn = open_db(db_path)
    run_id = mint_run_id("barcelona", "baseline", 42)
    writer = HistorianWriter(conn, run_id, flush_every=5)
    writer.write_run(
        scenario="barcelona", profile="baseline", dt_seconds=604800, seed=42, horizon_ticks=10
    )

    engine = Engine(scenario_seed=42)
    state = initial_state()
    drivers = _drivers()
    env = _env()
    for _ in range(10):
        state, observed, coupling = engine.step(state, drivers, env, dt=1.0)
        writer.write_tick(
            true_state=state,
            observed=observed,
            drivers=drivers,
            env=env,
            coupling=coupling,
            ts_iso="2026-04-25T10:00:00+00:00",
        )

    writer.write_event(
        OperatorEvent(
            tick=5,
            sim_time_s=5.0 * 604800,
            kind=OperatorEventKind.FIX,
            component_id="blade",
            payload=OperatorEvent.freeze_payload({"reason": "preventive"}),
        ),
        ts_iso="2026-04-25T11:00:00+00:00",
    )
    writer.close()

    run = reader.fetch_run(conn, run_id)
    assert run is not None
    assert run["scenario"] == "barcelona"

    finals = reader.fetch_final_component_states(conn, run_id)
    assert len(finals) == 6
    assert all(0.0 <= f["health_index"] <= 1.0 for f in finals)

    factors = reader.fetch_coupling_factors_at(conn, run_id, 5)
    assert "powder_spread_quality" in factors

    assert reader.fetch_event_count(conn, run_id) == 1

    conn.close()
