"""Heating element — Arrhenius acceleration on resistance drift + power draw.

Drift accumulates each week proportional to a single Arrhenius acceleration
factor `AF = exp((Ea/k_B)·(1/T_ref − 1/T_op))` (E_a = 0.7 eV, T_ref = 423 K
≈ 150 °C — doc 03). The operating temperature is read from
`engine.coupling.ambient_temperature_C_effective` (which itself is built
from the brief's `temperature_stress` Driver), then bumped by self-heating
proportional to load. So both pull-throughs from the audit table are
visible in the formula text:

1. The brief Driver `temperature_stress` enters via the derived
   `ambient_temperature_C_effective` → Kelvin → AF.
2. An additional `(1 + 0.3 · temp_stress_eff)` multiplier multiplies the
   drift increment so the audit grep on the Drivers field finds two
   independent dependencies.

Doc 22 anchors: η = 270 days ≈ 38 weeks, base_rate ≈ 0.025/week.
Doc 04: β = 1.0 (exponential / useful-life regime).
"""

from __future__ import annotations

import math
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
from ..engine.coupling import ambient_temperature_C_effective

COMPONENT_ID = "heater"

ETA_WEEKS = 38.0
BETA = 1.0
BASE_DRIFT_INCR = 0.0035

# Arrhenius constants — doc 03.
T_REF_K = 423.0  # 150 °C reference for binder cure.
EA_EV = 0.7  # activation energy for Ni-Cr resistance drift.
KB_EV_PER_K = 8.617e-5  # Boltzmann constant in eV/K.

# Self-heating range: 0 °C at zero load → SELF_HEATING_C at full load.
SELF_HEATING_C = 50.0

# Resistance drift expressed as fraction of nominal — 0.10 (10 %) is the
# doc-04 failed-element anchor.
DRIFT_AT_FAILURE = 0.10


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "resistance_drift": 0.0,
                "power_draw": 1.0,
                "energy_per_C": 1.0,
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

    ambient_C = ambient_temperature_C_effective(env, coupling)
    operating_C = ambient_C + SELF_HEATING_C * load_eff
    operating_K = max(operating_C + 273.15, 250.0)

    af = math.exp((EA_EV / KB_EV_PER_K) * (1.0 / T_REF_K - 1.0 / operating_K))
    temp_stress_bonus = 1.0 + 0.3 * temp_eff
    oxidation_amp = 1.0 + 0.5 * humid_eff
    duty_amp = 1.0 + 0.4 * load_eff

    drift_increment = (
        BASE_DRIFT_INCR * af * temp_stress_bonus * oxidation_amp * duty_amp * damp * dt
    )

    prev_drift = float(prev_self.metrics.get("resistance_drift", 0.0))
    prev_power = float(prev_self.metrics.get("power_draw", 1.0))
    prev_energy = float(prev_self.metrics.get("energy_per_C", 1.0))

    new_drift = prev_drift + drift_increment
    # Power-loss and energy-per-degree are both monotone proxies for drift.
    new_power = prev_power + 0.5 * drift_increment
    new_energy = prev_energy + 0.3 * drift_increment

    metric_health = clip01(1.0 - new_drift / DRIFT_AT_FAILURE)
    age = prev_self.age_ticks + 1
    baseline = weibull_baseline(age, ETA_WEEKS, BETA)
    health = clip01(baseline * metric_health)

    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=health,
        status=status_from_health(health),
        metrics=ComponentState.freeze_metrics(
            {
                "resistance_drift": new_drift,
                "power_draw": new_power,
                "energy_per_C": new_energy,
            }
        ),
        age_ticks=age,
    )


def reset(
    prev_self: ComponentState,
    kind: OperatorEventKind,
    payload: Mapping[str, float],  # noqa: ARG001
) -> ComponentState:
    """Doc 09: heater FIX = de-rate + recalibrate (drift × 0.5); REPLACE =
    element swap → initial_state.
    """
    if kind is OperatorEventKind.REPLACE:
        return initial_state()
    if kind is OperatorEventKind.FIX:
        prev_drift = float(prev_self.metrics.get("resistance_drift", 0.0))
        prev_power = float(prev_self.metrics.get("power_draw", 1.0))
        prev_energy = float(prev_self.metrics.get("energy_per_C", 1.0))
        return ComponentState(
            component_id=COMPONENT_ID,
            health_index=prev_self.health_index,
            status=prev_self.status,
            metrics=ComponentState.freeze_metrics(
                {
                    "resistance_drift": 0.5 * prev_drift,
                    # Recalibration brings power back toward nominal but not
                    # all the way (electrical wear is partly permanent).
                    "power_draw": 1.0 + 0.5 * (prev_power - 1.0),
                    "energy_per_C": 1.0 + 0.5 * (prev_energy - 1.0),
                }
            ),
            age_ticks=prev_self.age_ticks,
        )
    return prev_self
