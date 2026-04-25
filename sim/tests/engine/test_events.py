"""Tests for the event overlay — schema validation, apply behaviour,
boundary cases, and end-to-end persistence through the simulation loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from copilot_sim.cli import main
from copilot_sim.domain.drivers import Drivers
from copilot_sim.drivers_src.environment import Environment
from copilot_sim.drivers_src.events import EventOverlay, ScheduledEvent
from copilot_sim.simulation.scenarios import ScenarioConfig, load_scenario

# ---------------------------------------------------------------------------
# EventOverlay.apply behaviour
# ---------------------------------------------------------------------------


def _drivers() -> Drivers:
    return Drivers(
        temperature_stress=0.30,
        humidity_contamination=0.30,
        operational_load=0.50,
        maintenance_level=0.50,
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


def test_empty_overlay_passes_through() -> None:
    overlay = EventOverlay()
    drivers, env, fired = overlay.apply(5, _drivers(), _env())
    assert drivers == _drivers()
    assert env == _env()
    assert fired == []


def test_single_tick_event_fires_only_at_that_tick() -> None:
    overlay = EventOverlay(
        events=(
            ScheduledEvent(
                output_tick=5,
                name="earthquake",
                duration=1,
                driver_overrides={"maintenance_level": 0.0},
                env_overrides={"vibration_level": 0.85},
            ),
        )
    )
    # Before, after — no firing.
    for tick in (1, 4, 6, 7):
        drivers, env, fired = overlay.apply(tick, _drivers(), _env())
        assert drivers == _drivers()
        assert env == _env()
        assert fired == []
    # On the firing tick — both surfaces patched.
    drivers, env, fired = overlay.apply(5, _drivers(), _env())
    assert drivers.maintenance_level == 0.0
    assert env.vibration_level == 0.85
    assert len(fired) == 1 and fired[0].name == "earthquake"


def test_multi_tick_event_fires_across_full_window() -> None:
    overlay = EventOverlay(
        events=(
            ScheduledEvent(
                output_tick=10,
                name="hvac-failure",
                duration=3,
                driver_overrides={"temperature_stress": 0.95},
                env_overrides={},
            ),
        )
    )
    fired_at = {tick: overlay.fired_at(tick) for tick in (9, 10, 11, 12, 13)}
    assert [len(v) for v in fired_at.values()] == [0, 1, 1, 1, 0]
    # The override is applied for every active tick.
    for tick in (10, 11, 12):
        drivers, _, _ = overlay.apply(tick, _drivers(), _env())
        assert drivers.temperature_stress == 0.95


def test_multiple_events_compose_last_yaml_wins() -> None:
    overlay = EventOverlay(
        events=(
            ScheduledEvent(
                output_tick=5,
                name="first",
                duration=1,
                driver_overrides={"maintenance_level": 0.5},
                env_overrides={},
            ),
            ScheduledEvent(
                output_tick=5,
                name="second",
                duration=1,
                driver_overrides={"maintenance_level": 0.0},
                env_overrides={},
            ),
        )
    )
    drivers, _, fired = overlay.apply(5, _drivers(), _env())
    assert drivers.maintenance_level == 0.0
    assert [e.name for e in fired] == ["first", "second"]


# ---------------------------------------------------------------------------
# Pydantic validation — boundary cases the reviewer enumerated
# ---------------------------------------------------------------------------


def _scenario_with_event(**event_kwargs) -> dict:
    base = yaml.safe_load(
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("scenarios", "barcelona-baseline.yaml")
        .read_text()
    )
    base["events"] = [{"name": "test", **event_kwargs}]
    return base


def test_event_tick_boundaries() -> None:
    """tick=1 ok, tick=horizon ok, tick=horizon-1 duration=2 ok,
    tick=0 rejected, tick=horizon+1 rejected, tick=horizon duration=2 rejected.
    """
    horizon = 260

    # OK: tick = 1
    ScenarioConfig.model_validate(_scenario_with_event(tick=1, duration=1))
    # OK: tick = horizon, duration = 1 (last tick)
    ScenarioConfig.model_validate(_scenario_with_event(tick=horizon, duration=1))
    # OK: tick = horizon - 1, duration = 2 (spans last tick)
    ScenarioConfig.model_validate(_scenario_with_event(tick=horizon - 1, duration=2))

    # REJECT: tick = 0 (off-by-one trap)
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(_scenario_with_event(tick=0, duration=1))
    # REJECT: tick = horizon + 1 (past horizon)
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(_scenario_with_event(tick=horizon + 1, duration=1))
    # REJECT: tick = horizon, duration = 2 (extends past horizon)
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(_scenario_with_event(tick=horizon, duration=2))


def test_unknown_driver_override_key_rejected() -> None:
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(
            _scenario_with_event(tick=10, driver_overrides={"unknown_field": 0.5})
        )


def test_env_override_range_rejected() -> None:
    """Typo `vibration_level: 8.5` (vs `0.85`) is caught at YAML load."""
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(
            _scenario_with_event(tick=10, env_overrides={"vibration_level": 8.5})
        )


def test_driver_override_value_must_be_in_unit_interval() -> None:
    with pytest.raises(ValueError):
        ScenarioConfig.model_validate(
            _scenario_with_event(tick=10, driver_overrides={"temperature_stress": 1.5})
        )


# ---------------------------------------------------------------------------
# End-to-end through the simulation loop
# ---------------------------------------------------------------------------


def _scenario_root() -> Path:
    return Path(__file__).resolve().parents[2] / "scenarios"


def test_end_to_end_writes_environmental_event_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite"
    rc = main(
        [
            "run",
            str(_scenario_root() / "barcelona-with-events.yaml"),
            "--db-path",
            str(db_path),
            "--flush-every",
            "100",
        ]
    )
    assert rc == 0

    import sqlite3

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT tick, name FROM environmental_events ORDER BY tick").fetchall()
    conn.close()

    # earthquake @ 27, hvac-failure @ 89/90/91 (3 active ticks),
    # operator-holiday @ 145 = 5 rows total.
    by_name: dict[str, list[int]] = {}
    for tick, name in rows:
        by_name.setdefault(name, []).append(int(tick))
    assert by_name["earthquake"] == [27]
    assert by_name["hvac-failure"] == [89, 90, 91]
    assert by_name["operator-holiday"] == [145]


def test_environment_json_persists_per_tick_overrides(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite"
    rc = main(
        [
            "run",
            str(_scenario_root() / "barcelona-with-events.yaml"),
            "--db-path",
            str(db_path),
        ]
    )
    assert rc == 0

    from copilot_sim.historian import reader
    from copilot_sim.historian.connection import open_db

    conn = open_db(db_path)
    try:
        # tick 27 has the earthquake → vibration_level should be 0.85
        env_27 = reader.fetch_environment_at(conn, _latest_run_id(conn), 27)
        assert env_27["vibration_level"] == 0.85
        # tick 26 has the scenario default 0.10
        env_26 = reader.fetch_environment_at(conn, _latest_run_id(conn), 26)
        assert env_26["vibration_level"] == 0.10
        # tick 28 reverts back
        env_28 = reader.fetch_environment_at(conn, _latest_run_id(conn), 28)
        assert env_28["vibration_level"] == 0.10
    finally:
        conn.close()


def _latest_run_id(conn) -> str:
    return list(
        __import__("copilot_sim.historian.writer", fromlist=["list_run_ids"]).list_run_ids(conn)
    )[0]


def test_load_scenario_round_trip_with_events() -> None:
    cfg = load_scenario(_scenario_root() / "barcelona-with-events.yaml")
    names = [e.name for e in cfg.events]
    assert names == ["earthquake", "hvac-failure", "operator-holiday"]


def test_human_disruption_disables_policy_events_after_start(tmp_path: Path) -> None:
    db_path = tmp_path / "human-disruption.sqlite"
    rc = main(
        [
            "run",
            str(_scenario_root() / "barcelona-human-disruption-no-maintenance.yaml"),
            "--db-path",
            str(db_path),
        ]
    )
    assert rc == 0

    import sqlite3

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT tick FROM events ORDER BY tick").fetchall()
    conn.close()

    assert all(int(tick) < 140 for (tick,) in rows), (
        "No policy-driven human maintenance events should occur once "
        "human-disruption begins at tick 140"
    )
