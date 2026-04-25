"""Linear guide / rail — Lundberg-Palmgren cubic load-life.

L10 ∝ (C/P)^3 (NSK / THK rolling-element bearings) means the rail's
fatigue life is a *cubic* function of equivalent dynamic load. We map this
into the monotone misalignment + friction_level damage metrics:

- `load_amplifier = 1 + 4 · operational_load_eff^3` keeps the cubic
  exponent visible in the formula text (the driver-coverage test asserts
  strict monotonicity in load).
- `temperature_stress_eff` thins the lubricant film
  (`1 + 0.10 · temp_eff`).
- `humidity_contamination_eff` corrodes the raceway
  (`1 + 0.40 · humid_eff`).
- `env.vibration_level` adds a constant per-scenario offset.
- The shared `(1 - 0.8·M)` damper applies last.

Doc 22 anchors: η = 540 days ≈ 77 weeks, base_rate ≈ 0.012/week.
Doc 04: β = 2.0 (rolling-contact pitting).
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

COMPONENT_ID = "rail"

ETA_WEEKS = 77.0
BETA = 2.0
BASE_DAMAGE_INCR = 0.012
ALIGNMENT_UM_AT_FAILURE = 50.0


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "misalignment": 0.0,
                "friction_level": 0.0,
                "alignment_error_um": 0.0,
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

    load_amplifier = 1.0 + 4.0 * (load_eff**3)
    visc_factor = 1.0 + 0.10 * temp_eff
    corrosion_factor = 1.0 + 0.40 * humid_eff
    vib_factor = 1.0 + 0.5 * env.vibration_level

    damage_increment = (
        BASE_DAMAGE_INCR * load_amplifier * visc_factor * corrosion_factor * vib_factor * damp * dt
    )

    prev_misalign = float(prev_self.metrics.get("misalignment", 0.0))
    prev_friction = float(prev_self.metrics.get("friction_level", 0.0))
    prev_alignment_um = float(prev_self.metrics.get("alignment_error_um", 0.0))

    new_misalign = clip01(prev_misalign + damage_increment)
    new_friction = clip01(prev_friction + 0.6 * damage_increment)
    new_alignment_um = prev_alignment_um + ALIGNMENT_UM_AT_FAILURE * damage_increment

    age = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health = clip01(baseline * (1.0 - new_misalign))

    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=health,
        status=status_from_health(health),
        metrics=ComponentState.freeze_metrics(
            {
                "misalignment": new_misalign,
                "friction_level": new_friction,
                "alignment_error_um": new_alignment_um,
            }
        ),
        age_ticks=age,
    )


def reset(
    prev_self: ComponentState,
    kind: OperatorEventKind,
    payload: Mapping[str, float],  # noqa: ARG001
) -> ComponentState:
    """Doc 09: rail FIX = re-grease + corrosion clean (zero misalignment delta,
    half the friction); REPLACE = full bearing swap (initial state).
    Subsurface pitting is permanent so FIX leaves alignment_error untouched.
    """
    if kind is OperatorEventKind.REPLACE:
        return initial_state()
    if kind is OperatorEventKind.FIX:
        return ComponentState(
            component_id=COMPONENT_ID,
            health_index=prev_self.health_index,
            status=prev_self.status,
            metrics=ComponentState.freeze_metrics(
                {
                    "misalignment": float(prev_self.metrics.get("misalignment", 0.0)),
                    "friction_level": 0.5 * float(prev_self.metrics.get("friction_level", 0.0)),
                    "alignment_error_um": float(prev_self.metrics.get("alignment_error_um", 0.0)),
                }
            ),
            age_ticks=prev_self.age_ticks,
        )
    return prev_self
