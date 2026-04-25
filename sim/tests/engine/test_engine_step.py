"""End-to-end smoke for `Engine.step` — one tick, six components, observed shape."""

from __future__ import annotations

from copilot_sim.components.registry import COMPONENT_IDS
from copilot_sim.domain.drivers import Drivers
from copilot_sim.domain.enums import PrintOutcome
from copilot_sim.drivers_src.environment import Environment
from copilot_sim.engine.engine import Engine, initial_state


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


def test_engine_step_produces_six_components_and_observed_shape() -> None:
    engine = Engine(scenario_seed=42)
    prev = initial_state()
    new_state, observed, coupling = engine.step(prev, _drivers(), _env(), dt=1.0)

    assert new_state.tick == 1
    assert set(new_state.components.keys()) == set(COMPONENT_IDS)
    assert set(observed.components.keys()) == set(COMPONENT_IDS)
    assert new_state.print_outcome is PrintOutcome.OK

    # Coupling factors include the ten locked names.
    expected_factors = {
        "powder_spread_quality",
        "blade_loss_frac",
        "rail_alignment_error",
        "heater_drift_frac",
        "heater_thermal_stress_bonus",
        "sensor_bias_c",
        "sensor_noise_sigma_c",
        "control_temp_error_c",
        "cleaning_efficiency",
        "nozzle_clog_pct",
    }
    assert expected_factors.issubset(set(coupling.factors.keys()))


def test_engine_step_is_deterministic_for_same_seed() -> None:
    """Same scenario_seed + same inputs ⇒ byte-identical state."""
    a = Engine(scenario_seed=42)
    b = Engine(scenario_seed=42)
    prev = initial_state()
    a_next, _, _ = a.step(prev, _drivers(), _env(), dt=1.0)
    b_next, _, _ = b.step(prev, _drivers(), _env(), dt=1.0)
    for cid in COMPONENT_IDS:
        assert a_next.components[cid].metrics == b_next.components[cid].metrics
        assert a_next.components[cid].health_index == b_next.components[cid].health_index


def test_engine_advances_50_ticks_without_crash() -> None:
    engine = Engine(scenario_seed=7)
    state = initial_state()
    drivers = _drivers()
    env = _env()
    for _ in range(50):
        state, _, _ = engine.step(state, drivers, env, dt=1.0)
    assert state.tick == 50
