"""Heater Arrhenius step — universal three-rule smoke."""

from __future__ import annotations

from copilot_sim.components import heater
from copilot_sim.domain.enums import OperatorEventKind

from ._helpers import (
    assert_health_in_bounds,
    assert_metrics_in_expected_direction,
    assert_status_monotone_forward,
    make_rng,
    neutral_coupling,
    neutral_drivers,
    neutral_environment,
)


def test_heater_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("heater")

    state = heater.initial_state()
    for _ in range(50):
        prev = state
        state = heater.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "heater")


def test_heater_arrhenius_responds_to_temperature_stress() -> None:
    """Higher temperature_stress → larger drift increment per tick."""
    env = neutral_environment()
    rng = make_rng("heater")

    cool_drivers = neutral_drivers(temperature_stress=0.0)
    hot_drivers = neutral_drivers(temperature_stress=1.0)

    cool_coupling = neutral_coupling(cool_drivers)
    hot_coupling = neutral_coupling(hot_drivers)

    s = heater.initial_state()
    cool = heater.step(s, cool_coupling, cool_drivers, env, dt=1.0, rng=rng)
    hot = heater.step(s, hot_coupling, hot_drivers, env, dt=1.0, rng=rng)

    assert hot.metrics["resistance_drift"] > cool.metrics["resistance_drift"], (
        "Arrhenius pull-through is broken — temperature_stress should "
        "strictly accelerate drift via ambient_temperature_C_effective"
    )


def test_heater_replace_resets_drift() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("heater")

    state = heater.initial_state()
    for _ in range(20):
        state = heater.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    fresh = heater.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["resistance_drift"] == 0.0


def test_heater_fix_halves_drift() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("heater")

    state = heater.initial_state()
    for _ in range(20):
        state = heater.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    pre_drift = state.metrics["resistance_drift"]
    fixed = heater.reset(state, OperatorEventKind.FIX, payload={})
    assert fixed.metrics["resistance_drift"] == 0.5 * pre_drift
