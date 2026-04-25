"""System-level assembly helpers used by `Engine.step`:

- `derive_print_outcome` maps component statuses + healths to the top-level
  `PrintOutcome` enum per the plan's locked thresholds.
- `build_observed_state` is the §3.4 true→observed pass. It walks the
  per-component `SensorModel` factories so the heater observation
  flows through the temperature sensor and the §3.4 sensor-fault story
  is mechanically wired.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ..domain.enums import OperationalStatus, PrintOutcome
from ..domain.state import (
    ComponentState,
    ObservedPrinterState,
    PrinterState,
)
from ..sensors.factories import make_sensor_model

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


def build_observed_state(state: PrinterState, rng: np.random.Generator) -> ObservedPrinterState:
    """§3.4 sensor-pass.

    Iterates the registry order via `state.components` and asks each
    component's `SensorModel` for an `ObservedComponentState`. The same
    `rng` is shared so the observation noise is deterministic w.r.t. the
    engine's seed/tick derivation.
    """
    observed = {}
    for cid, component in state.components.items():
        model = make_sensor_model(cid)
        observed[cid] = model.observe(component, state, rng)
    return ObservedPrinterState(
        tick=state.tick,
        sim_time_s=state.sim_time_s,
        components=ObservedPrinterState.freeze_components(observed),
    )
