"""§3.4 observed-state pass — sensor-mediated heater readings."""

from __future__ import annotations

import numpy as np

from copilot_sim.components.registry import COMPONENT_IDS, REGISTRY
from copilot_sim.domain.enums import OperationalStatus
from copilot_sim.domain.state import ComponentState, PrinterState
from copilot_sim.engine.assembly import build_observed_state
from copilot_sim.engine.engine import initial_state


def _state_with_sensor(sensor_state: ComponentState) -> PrinterState:
    components = {cid: REGISTRY[cid].initial_state() for cid in COMPONENT_IDS}
    components["sensor"] = sensor_state
    return PrinterState(
        tick=0,
        sim_time_s=0.0,
        components=PrinterState.freeze_components(components),
        print_outcome=initial_state().print_outcome,
    )


def test_observed_shape_matches_true_keys() -> None:
    state = initial_state()
    rng = np.random.default_rng(0)
    observed = build_observed_state(state, rng)
    assert set(observed.components.keys()) == set(state.components.keys())
    for cid in state.components:
        assert observed.components[cid].observed_status is not None


def test_failed_sensor_produces_unknown_observed_heater() -> None:
    """When the temperature sensor is FAILED the heater observation drops
    to None / UNKNOWN — the policy should pick this up and TROUBLESHOOT.
    """
    failed_sensor = ComponentState(
        component_id="sensor",
        health_index=0.0,
        status=OperationalStatus.FAILED,
        metrics=ComponentState.freeze_metrics(
            {"bias_offset": 12.0, "noise_sigma": 1.0, "reading_accuracy": 0.0}
        ),
        age_ticks=200,
    )
    state = _state_with_sensor(failed_sensor)
    rng = np.random.default_rng(0)
    observed = build_observed_state(state, rng)

    heater_observed = observed.components["heater"]
    assert heater_observed.observed_status is OperationalStatus.UNKNOWN
    assert heater_observed.sensor_note == "stuck"
    for value in heater_observed.observed_metrics.values():
        assert value is None


def test_sensor_self_observation_is_passthrough() -> None:
    """The sensor reports its own true bias as observed — no meta-sensor."""
    state = initial_state()
    rng = np.random.default_rng(0)
    observed = build_observed_state(state, rng)
    sensor_obs = observed.components["sensor"]
    sensor_true = state.components["sensor"]
    for k, v in sensor_true.metrics.items():
        assert sensor_obs.observed_metrics[k] == v
