"""Rail Lundberg-Palmgren step — universal three-rule smoke test."""

from __future__ import annotations

from copilot_sim.components import rail
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


def test_rail_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("rail")

    state = rail.initial_state()
    for _ in range(50):
        prev = state
        state = rail.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "rail")


def test_rail_replace_zeros_misalignment() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("rail")

    state = rail.initial_state()
    for _ in range(20):
        state = rail.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    assert state.metrics["misalignment"] > 0.0

    fresh = rail.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["misalignment"] == 0.0
    assert fresh.metrics["alignment_error_um"] == 0.0


def test_rail_fix_keeps_pitting_halves_friction() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("rail")

    state = rail.initial_state()
    for _ in range(20):
        state = rail.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    pre_friction = state.metrics["friction_level"]
    pre_alignment = state.metrics["alignment_error_um"]

    fixed = rail.reset(state, OperatorEventKind.FIX, payload={})
    # Pitting is permanent — alignment_error_um must not change.
    assert fixed.metrics["alignment_error_um"] == pre_alignment
    # Friction halved.
    assert fixed.metrics["friction_level"] == 0.5 * pre_friction
