"""Sensor Arrhenius drift step — universal three-rule smoke."""

from __future__ import annotations

from copilot_sim.components import sensor
from copilot_sim.domain.enums import OperationalStatus, OperatorEventKind

from ._helpers import (
    assert_health_in_bounds,
    assert_metrics_in_expected_direction,
    assert_status_monotone_forward,
    make_rng,
    neutral_coupling,
    neutral_drivers,
    neutral_environment,
)


def test_sensor_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("sensor")

    state = sensor.initial_state()
    for _ in range(50):
        prev = state
        state = sensor.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "sensor")


def test_sensor_replace_zeros_bias_and_noise() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("sensor")

    state = sensor.initial_state()
    for _ in range(20):
        state = sensor.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    fresh = sensor.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["bias_offset"] == 0.0
    # Doc 09: REPLACE returns the initial noise floor.
    assert fresh.metrics["noise_sigma"] == sensor.initial_state().metrics["noise_sigma"]


def test_sensor_fix_zeros_bias_keeps_noise() -> None:
    """Doc 09: FIX = calibration (bias → 0) but connector oxidation
    persists, so noise is unchanged.
    """
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("sensor")

    state = sensor.initial_state()
    for _ in range(20):
        state = sensor.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    pre_noise = state.metrics["noise_sigma"]

    fixed = sensor.reset(state, OperatorEventKind.FIX, payload={})
    assert fixed.metrics["bias_offset"] == 0.0
    assert fixed.metrics["noise_sigma"] == pre_noise


def test_sensor_hard_failed_at_bias_5C() -> None:
    """Doc 04: |bias| > 5 °C is a hard FAILED gate regardless of HI."""
    from copilot_sim.drivers_src.environment import Environment

    drivers = neutral_drivers(temperature_stress=1.0)
    coupling = neutral_coupling(drivers)
    # Hot in-zone environment so the Arrhenius AF crosses 1; otherwise the
    # ambient is ~20 °C and bias drift is millikelvin-per-week.
    env = Environment(
        base_ambient_C=200.0,
        amplitude_C=0.0,
        weekly_runtime_hours=110.0,
        vibration_level=0.10,
        cumulative_cleanings=0,
        hours_since_maintenance=0.0,
        start_stop_cycles=0,
    )
    rng = make_rng("sensor")

    state = sensor.initial_state()
    for _ in range(400):
        state = sensor.step(state, coupling, drivers, env, dt=1.0, rng=rng)
        if state.status is OperationalStatus.FAILED:
            break
    assert state.status is OperationalStatus.FAILED
    assert abs(state.metrics["bias_offset"]) > 5.0
