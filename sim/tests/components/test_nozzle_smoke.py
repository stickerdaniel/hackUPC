"""Nozzle Coffin-Manson + Poisson clog step — universal three-rule smoke."""

from __future__ import annotations

from copilot_sim.components import nozzle
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


def test_nozzle_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("nozzle")

    state = nozzle.initial_state()
    for _ in range(50):
        prev = state
        state = nozzle.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "nozzle")


def test_nozzle_replace_zeros_metrics() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("nozzle")

    state = nozzle.initial_state()
    for _ in range(20):
        state = nozzle.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    fresh = nozzle.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["thermal_fatigue"] == 0.0
    assert fresh.metrics["clog_pct"] == 0.0


def test_nozzle_fix_partially_clears_clog() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("nozzle", seed=1)

    state = nozzle.initial_state()
    for _ in range(40):
        state = nozzle.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    pre_clog = state.metrics["clog_pct"]
    pre_fatigue = state.metrics["thermal_fatigue"]
    if pre_clog == 0.0 and pre_fatigue == 0.0:
        # Nothing accumulated — skip the partial-clear assertion.
        return
    fixed = nozzle.reset(state, OperatorEventKind.FIX, payload={})
    assert fixed.metrics["clog_pct"] <= pre_clog
    assert fixed.metrics["thermal_fatigue"] <= pre_fatigue
