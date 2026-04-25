"""System-level assembly helpers used by `Engine.step`:

- `derive_print_outcome` maps component statuses + healths to the top-level
  `PrintOutcome` enum per the plan's locked thresholds.
- `build_observed_state` is the §3.4 true→observed pass. In this commit it
  is a passthrough (every observed view equals the true view); A13 replaces
  the body with per-component sensor models without changing the
  signature.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..domain.enums import OperationalStatus, PrintOutcome
from ..domain.state import (
    ComponentState,
    ObservedComponentState,
    ObservedPrinterState,
    PrinterState,
)

_QUALITY_DEGRADED_HEALTH = 0.40


def derive_print_outcome(components: Mapping[str, ComponentState]) -> PrintOutcome:
    """`HALTED` if any component status is FAILED; `QUALITY_DEGRADED` if any
    CRITICAL or `min(health) < 0.40`; else `OK`. Strict-`<` everywhere.
    """
    if any(c.status is OperationalStatus.FAILED for c in components.values()):
        return PrintOutcome.HALTED

    any_critical = any(c.status is OperationalStatus.CRITICAL for c in components.values())
    min_health = min((c.health_index for c in components.values()), default=1.0)
    if any_critical or min_health < _QUALITY_DEGRADED_HEALTH:
        return PrintOutcome.QUALITY_DEGRADED

    return PrintOutcome.OK


def _passthrough_observed(component: ComponentState) -> ObservedComponentState:
    observed_metrics: dict[str, float | None] = {k: float(v) for k, v in component.metrics.items()}
    sensor_health: dict[str, float | None] = {k: 1.0 for k in component.metrics}
    return ObservedComponentState(
        component_id=component.component_id,
        observed_metrics=ObservedComponentState.freeze_metrics(observed_metrics),
        sensor_health=ObservedComponentState.freeze_sensor_health(sensor_health),
        sensor_note="ok",
        observed_health_index=component.health_index,
        observed_status=component.status,
    )


def build_observed_state(state: PrinterState) -> ObservedPrinterState:
    """§3.4 sensor-pass. v1 is a passthrough; A13 replaces the body with the
    per-component sensor models without changing the signature.
    """
    observed = {cid: _passthrough_observed(c) for cid, c in state.components.items()}
    return ObservedPrinterState(
        tick=state.tick,
        sim_time_s=state.sim_time_s,
        components=ObservedPrinterState.freeze_components(observed),
    )
