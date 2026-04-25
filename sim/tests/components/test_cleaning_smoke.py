"""Cleaning interface power-law step — universal three-rule smoke."""

from __future__ import annotations

from copilot_sim.components import cleaning
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


def test_cleaning_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("cleaning")

    state = cleaning.initial_state()
    for _ in range(50):
        prev = state
        state = cleaning.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "cleaning")


def test_cleaning_replace_resets_metrics() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("cleaning")

    state = cleaning.initial_state()
    for _ in range(20):
        state = cleaning.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    fresh = cleaning.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["wiper_wear"] == 0.0
    assert fresh.metrics["cleaning_effectiveness"] == 1.0


def test_cleaning_fix_routes_to_replace() -> None:
    """Doc 09: cleaning has no partial FIX — wiper swap is the only repair."""
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("cleaning")

    state = cleaning.initial_state()
    for _ in range(20):
        state = cleaning.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    fixed = cleaning.reset(state, OperatorEventKind.FIX, payload={})
    assert fixed.metrics["wiper_wear"] == 0.0
