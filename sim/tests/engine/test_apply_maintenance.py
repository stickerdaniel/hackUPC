"""Engine.apply_maintenance — TROUBLESHOOT/FIX/REPLACE dispatch."""

from __future__ import annotations

from copilot_sim.domain.drivers import Drivers
from copilot_sim.domain.enums import OperatorEventKind
from copilot_sim.domain.events import MaintenanceAction
from copilot_sim.drivers_src.environment import Environment
from copilot_sim.engine.engine import Engine, initial_state


def _drivers() -> Drivers:
    return Drivers(
        temperature_stress=0.30,
        humidity_contamination=0.30,
        operational_load=0.50,
        maintenance_level=0.0,
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


def _age_blade(engine: Engine, ticks: int):
    state = initial_state()
    for _ in range(ticks):
        state, _, _ = engine.step(state, _drivers(), _env(), dt=1.0)
    return state


def test_troubleshoot_does_not_mutate_state() -> None:
    engine = Engine(scenario_seed=42)
    state = _age_blade(engine, 20)
    pre_blade = state.components["blade"]

    new_state, event = engine.apply_maintenance(
        state,
        MaintenanceAction(
            component_id="blade",
            kind=OperatorEventKind.TROUBLESHOOT,
            payload=MaintenanceAction.freeze_payload({}),
        ),
    )
    assert new_state.components["blade"] == pre_blade
    assert event.kind is OperatorEventKind.TROUBLESHOOT
    assert event.component_id == "blade"


def test_replace_blade_returns_fresh_metrics() -> None:
    engine = Engine(scenario_seed=42)
    state = _age_blade(engine, 20)
    assert state.components["blade"].metrics["wear_level"] > 0.0

    new_state, event = engine.apply_maintenance(
        state,
        MaintenanceAction(
            component_id="blade",
            kind=OperatorEventKind.REPLACE,
            payload=MaintenanceAction.freeze_payload({}),
        ),
    )
    assert new_state.components["blade"].metrics["wear_level"] == 0.0
    assert event.kind is OperatorEventKind.REPLACE


def test_fix_sensor_zeros_bias_keeps_noise() -> None:
    engine = Engine(scenario_seed=42)
    state = _age_blade(engine, 30)
    pre_noise = state.components["sensor"].metrics["noise_sigma"]

    new_state, _ = engine.apply_maintenance(
        state,
        MaintenanceAction(
            component_id="sensor",
            kind=OperatorEventKind.FIX,
            payload=MaintenanceAction.freeze_payload({}),
        ),
    )
    assert new_state.components["sensor"].metrics["bias_offset"] == 0.0
    assert new_state.components["sensor"].metrics["noise_sigma"] == pre_noise


def test_unknown_component_raises() -> None:
    engine = Engine(scenario_seed=42)
    state = initial_state()

    import pytest

    with pytest.raises(KeyError):
        engine.apply_maintenance(
            state,
            MaintenanceAction(
                component_id="not_a_component",
                kind=OperatorEventKind.FIX,
                payload=MaintenanceAction.freeze_payload({}),
            ),
        )
