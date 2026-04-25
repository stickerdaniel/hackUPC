"""Blade Archard step — universal three-rule smoke test.

Health stays in [0, 1], status only progresses forward, and the blade's
two damage metrics (wear_level, edge_roughness) only ever go up under
unmaintained operation.
"""

from __future__ import annotations

from copilot_sim.components import blade

from ._helpers import (
    assert_health_in_bounds,
    assert_metrics_in_expected_direction,
    assert_status_monotone_forward,
    make_rng,
    neutral_coupling,
    neutral_drivers,
    neutral_environment,
)


def test_blade_smoke_50_unmaintained_ticks() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("blade")

    state = blade.initial_state()
    assert state.health_index == 1.0

    for _ in range(50):
        prev = state
        state = blade.step(prev, coupling, drivers, env, dt=1.0, rng=rng)
        assert_health_in_bounds(state)
        assert_status_monotone_forward(prev, state)
        assert_metrics_in_expected_direction(prev, state, "blade")
        assert state.age_ticks == prev.age_ticks + 1


def test_blade_replace_zeros_wear() -> None:
    drivers = neutral_drivers()
    coupling = neutral_coupling(drivers)
    env = neutral_environment()
    rng = make_rng("blade")

    state = blade.initial_state()
    for _ in range(20):
        state = blade.step(state, coupling, drivers, env, dt=1.0, rng=rng)
    assert state.metrics["wear_level"] > 0.0

    from copilot_sim.domain.enums import OperatorEventKind

    fresh = blade.reset(state, OperatorEventKind.REPLACE, payload={})
    assert fresh.metrics["wear_level"] == 0.0
    assert fresh.health_index == 1.0
