"""Cleaning interface (wiper + capping station) — power-law wear-per-cycle.

Per doc 18 the dominant decay is power-law in cumulative cleaning cycles,
not in time. We accumulate `wiper_wear` from the cleanings done THIS week
(Δn = `weekly_runtime_hours / 4`), amplified by the four drivers:

- `temperature_stress_eff` dries binder onto the wiper
  (`1 + 0.20 · temp_eff`) — the brief Driver enters the wiper-wear path.
- `humidity_contamination_eff` saturates the residue pad
  (`1 + 0.60 · humid_eff`).
- `operational_load_eff` adds throughput pressure
  (`1 + 0.40 · load_eff`).
- The shared `(1 - 0.8·M)` damper applies last.

`cleaning_effectiveness` is a derived metric: `1 - 0.7·wiper_wear -
0.3·residue_saturation`. Doc 04: β = 1.5 (light wear-out), η = 50 weeks
calendar shelf-life floor.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.enums import OperationalStatus, OperatorEventKind
from ..domain.state import ComponentState
from ..drivers_src.environment import Environment
from ..engine.aging import (
    clip01,
    maintenance_damper,
    status_from_health,
    weibull_baseline,
)

COMPONENT_ID = "cleaning"

ETA_WEEKS = 50.0
BETA = 1.5
WEAR_PER_CLEANING = 0.003
RESIDUE_BASE_INCR = 0.012


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "wiper_wear": 0.0,
                "residue_saturation": 0.0,
                "cleaning_effectiveness": 1.0,
            }
        ),
        age_ticks=0,
    )


def step(
    prev_self: ComponentState,
    coupling: CouplingContext,
    drivers: Drivers,  # noqa: ARG001
    env: Environment,
    dt: float,
    rng: np.random.Generator,  # noqa: ARG001
) -> ComponentState:
    temp_eff = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff = coupling.operational_load_effective
    damp = maintenance_damper(coupling.maintenance_level_effective)

    cleanings_this_week = max(env.weekly_runtime_hours / 4.0, 0.0)
    binder_drying = 1.0 + 0.20 * temp_eff
    residue_amp = 1.0 + 0.60 * humid_eff
    load_amp = 1.0 + 0.40 * load_eff

    wiper_increment = (
        WEAR_PER_CLEANING * cleanings_this_week * binder_drying * load_amp * residue_amp * damp * dt
    )
    residue_increment = RESIDUE_BASE_INCR * residue_amp * binder_drying * damp * dt

    prev_wear = float(prev_self.metrics.get("wiper_wear", 0.0))
    prev_residue = float(prev_self.metrics.get("residue_saturation", 0.0))

    new_wear = clip01(prev_wear + wiper_increment)
    new_residue = clip01(prev_residue + residue_increment)
    new_effectiveness = clip01(1.0 - 0.7 * new_wear - 0.3 * new_residue)

    age = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health = clip01(baseline * new_effectiveness)

    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=health,
        status=status_from_health(health),
        metrics=ComponentState.freeze_metrics(
            {
                "wiper_wear": new_wear,
                "residue_saturation": new_residue,
                "cleaning_effectiveness": new_effectiveness,
            }
        ),
        age_ticks=age,
    )


def reset(
    prev_self: ComponentState,
    kind: OperatorEventKind,
    payload: Mapping[str, float],  # noqa: ARG001
) -> ComponentState:
    """Doc 09: cleaning interface has no field-repairable FIX — wiper-blade
    swap = full reset of the wear path. Both FIX and REPLACE return
    initial_state.
    """
    if kind in (OperatorEventKind.FIX, OperatorEventKind.REPLACE):
        return initial_state()
    return prev_self
