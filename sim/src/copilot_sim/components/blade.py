"""Recoater blade — Archard's wear law on the wear_level + edge_roughness pair.

`V = k · F · s / H`. We multiplicatively split the right-hand side across
the four brief drivers + Environment runtime hours:

- `H` (hardness) softens with `(1 + 0.10 · temp_stress_eff)` — hot beds make
  the blade lip easier to abrade.
- `k` (wear coefficient) amplifies with `(1 + 0.5 · humidity_contamination_eff)`
  — moisture-bound powder grits act as a more aggressive abrasive.
- `F` (load) amplifies with `(1 + 0.6 · operational_load_eff)` — heavier
  print queues push the recoater harder against the bed.
- `s` (sliding distance) scales with `weekly_runtime_hours / 60` — Barcelona
  baseline runs 60 h/week, Phoenix 110 h/week.
- The `(1 - 0.8 · M)` damper from `engine.aging.maintenance_damper` clamps
  the whole increment so good maintenance still slows wear.

Health is the multiplicative composition (doc 04) of the Weibull baseline
and the metric-derived health `(1 - wear_level)`.
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

COMPONENT_ID = "blade"

# Doc 22 anchors: η = 120 days ≈ 17 weeks, base_rate ≈ 0.04/week.
ETA_WEEKS = 17.0
BETA = 2.5
BASE_WEAR_INCR = 0.04
NOMINAL_RUNTIME_HOURS = 60.0


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "wear_level": 0.0,
                "edge_roughness": 0.0,
                "thickness_mm": 1.0,
            }
        ),
        age_ticks=0,
    )


def step(
    prev_self: ComponentState,
    coupling: CouplingContext,
    drivers: Drivers,  # noqa: ARG001 — components consume coupling.*_effective, not raw
    env: Environment,
    dt: float,
    rng: np.random.Generator,  # noqa: ARG001 — Archard is deterministic
) -> ComponentState:
    temp_eff = coupling.temperature_stress_effective
    humid_eff = coupling.humidity_contamination_effective
    load_eff = coupling.operational_load_effective
    damp = maintenance_damper(coupling.maintenance_level_effective)

    hardness_factor = 1.0 + 0.10 * temp_eff
    k_amplifier = 1.0 + 0.5 * humid_eff
    f_amplifier = 1.0 + 0.6 * load_eff
    s_scale = max(env.weekly_runtime_hours / NOMINAL_RUNTIME_HOURS, 0.0)

    wear_increment = (
        BASE_WEAR_INCR * hardness_factor * k_amplifier * f_amplifier * s_scale * damp * dt
    )

    prev_wear = float(prev_self.metrics.get("wear_level", 0.0))
    prev_rough = float(prev_self.metrics.get("edge_roughness", 0.0))

    new_wear = clip01(prev_wear + wear_increment)
    # Roughness lags wear at 0.7× — physically the leading edge dulls before
    # the bulk wears through.
    new_rough = clip01(prev_rough + 0.7 * wear_increment)
    new_thickness_mm = max(0.5, 1.0 - 0.5 * new_wear)

    age = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health = clip01(baseline * (1.0 - new_wear))

    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=health,
        status=status_from_health(health),
        metrics=ComponentState.freeze_metrics(
            {
                "wear_level": new_wear,
                "edge_roughness": new_rough,
                "thickness_mm": new_thickness_mm,
            }
        ),
        age_ticks=age,
    )


def reset(
    prev_self: ComponentState,
    kind: OperatorEventKind,
    payload: Mapping[str, float],  # noqa: ARG001 — payload not used in v1
) -> ComponentState:
    """Doc 09 §maintenance effect model: blade has no field-repairable FIX —
    `FIX` falls through to `REPLACE` (a fresh blade). `REPLACE` resets all
    wear metrics; `TROUBLESHOOT` is a no-op handled by the engine before
    this function is called.
    """
    if kind in (OperatorEventKind.FIX, OperatorEventKind.REPLACE):
        return initial_state()
    return prev_self
