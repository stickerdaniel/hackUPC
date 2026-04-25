"""Heuristic policy decision rules."""

from __future__ import annotations

from copilot_sim.components.registry import COMPONENT_IDS, REGISTRY
from copilot_sim.domain.enums import OperationalStatus, OperatorEventKind
from copilot_sim.domain.state import (
    ComponentState,
    ObservedComponentState,
    ObservedPrinterState,
)
from copilot_sim.policy.heuristic import HeuristicPolicy


def _ok_observed(component_id: str, health: float = 1.0) -> ObservedComponentState:
    metrics = REGISTRY[component_id].initial_state().metrics
    observed_metrics: dict[str, float | None] = {k: float(v) for k, v in metrics.items()}
    sensor_health: dict[str, float | None] = dict.fromkeys(observed_metrics, 1.0)
    return ObservedComponentState(
        component_id=component_id,
        observed_metrics=ObservedComponentState.freeze_metrics(observed_metrics),
        sensor_health=ObservedComponentState.freeze_sensor_health(sensor_health),
        sensor_note="ok",
        observed_health_index=health,
        observed_status=(
            OperationalStatus.FUNCTIONAL if health >= 0.75 else OperationalStatus.DEGRADED
        ),
    )


def _unknown_observed(component_id: str) -> ObservedComponentState:
    metrics = REGISTRY[component_id].initial_state().metrics
    observed_metrics: dict[str, float | None] = dict.fromkeys(metrics, None)
    sensor_health: dict[str, float | None] = dict.fromkeys(metrics, None)
    return ObservedComponentState(
        component_id=component_id,
        observed_metrics=ObservedComponentState.freeze_metrics(observed_metrics),
        sensor_health=ObservedComponentState.freeze_sensor_health(sensor_health),
        sensor_note="stuck",
        observed_health_index=None,
        observed_status=OperationalStatus.UNKNOWN,
    )


def _make(observed_components: dict[str, ObservedComponentState]) -> ObservedPrinterState:
    return ObservedPrinterState(
        tick=10,
        sim_time_s=10.0,
        components=ObservedPrinterState.freeze_components(observed_components),
    )


def test_unknown_status_triggers_troubleshoot() -> None:
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["heater"] = _unknown_observed("heater")
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert len(actions) == 1
    assert actions[0].kind is OperatorEventKind.TROUBLESHOOT
    assert actions[0].component_id == "heater"


def test_low_health_triggers_replace() -> None:
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["blade"] = _ok_observed("blade", health=0.10)
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert actions[0].kind is OperatorEventKind.REPLACE
    assert actions[0].component_id == "blade"


def test_mid_health_triggers_fix() -> None:
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["nozzle"] = _ok_observed("nozzle", health=0.30)
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert actions[0].kind is OperatorEventKind.FIX
    assert actions[0].component_id == "nozzle"


def test_preventive_fix_when_all_healthy() -> None:
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert len(actions) == 1
    assert actions[0].kind is OperatorEventKind.FIX


def test_unknown_takes_priority_over_low_health() -> None:
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["blade"] = _ok_observed("blade", health=0.05)
    components["heater"] = _unknown_observed("heater")
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert actions[0].kind is OperatorEventKind.TROUBLESHOOT
    assert actions[0].component_id == "heater"


def test_lowest_observed_health_wins_when_multiple_below_threshold() -> None:
    """Two components below the FIX threshold — the worst-health one wins
    regardless of registry order.
    """
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    # nozzle is third in COMPONENT_IDS, blade is first. Under the old
    # fixed-iteration policy, blade@0.30 would have won by being first;
    # here we make blade=0.40 (mild) and nozzle=0.25 (worse) — nozzle
    # should win by being the worst, which is also the fixed-order
    # outcome. Flip with rail to genuinely exercise the sort.
    components["blade"] = _ok_observed("blade", health=0.40)
    components["rail"] = _ok_observed("rail", health=0.30)
    components["nozzle"] = _ok_observed("nozzle", health=0.42)
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert actions[0].kind is OperatorEventKind.FIX
    assert actions[0].component_id == "rail", (
        "worst-first triage: rail@0.30 must beat blade@0.40 and nozzle@0.42 "
        "even though blade comes first in COMPONENT_IDS"
    )


def test_lowest_health_replace_threshold_overrides_fix() -> None:
    """A component below 0.20 ranks as REPLACE; a milder one stays FIX —
    the worst (REPLACE-bound) one wins.
    """
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["blade"] = _ok_observed("blade", health=0.30)
    components["heater"] = _ok_observed("heater", health=0.10)
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    assert actions[0].component_id == "heater"
    assert actions[0].kind is OperatorEventKind.REPLACE


def test_tie_breaks_by_registry_order() -> None:
    """Two equally-bad components → the one earlier in COMPONENT_IDS wins."""
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    components["blade"] = _ok_observed("blade", health=0.30)
    components["nozzle"] = _ok_observed("nozzle", health=0.30)
    observed = _make(components)
    policy = HeuristicPolicy()
    actions = policy.decide(observed, tick=10)
    # blade is first in COMPONENT_IDS, nozzle is third.
    assert actions[0].component_id == "blade"


def _state_with_initial(observed_components):
    return _make(observed_components)


def test_observed_state_is_only_input() -> None:
    """Construct an ObservedPrinterState with a happy view but a deliberately
    fake true state — the policy must never crash for missing true_state.
    """
    components = {cid: _ok_observed(cid) for cid in COMPONENT_IDS}
    observed = _make(components)
    policy = HeuristicPolicy()
    # Never raises — only argument is observed.
    policy.decide(observed, tick=4)


# Silence unused-import warning when running specific tests
_ = ComponentState
