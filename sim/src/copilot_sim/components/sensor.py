"""Temperature sensor — Arrhenius bias drift + sub-linear noise growth.

Doc 19: a PT100 RTD ages by accumulating a calibration offset (`bias_offset`,
in °C, sign convention +1 — the sensor reads consistently low) plus a
slowly growing noise floor (`noise_sigma`, in °C). The bias is the
"silent" failure mode that powers the §3.4 sensor-fault-vs-component-fault
story: a +°C bias propagates through `coupling.factors["sensor_bias_c"]`
into the heater controller, which then over-shoots and accelerates the
heater's own drift.

The temperature_stress Driver pull-through is identical to the heater's:

1. via `ambient_temperature_C_effective` → operating_K → Arrhenius AF.
2. via the `(1 + 0.3 · temp_eff)` multiplier on the drift increment.

`reading_accuracy = 0.7·(1 - |bias|/5) + 0.3·(1 - noise/0.5)` is the
non-increasing derived metric the smoke test pins down. There is no
Weibull baseline (doc 04) — drift dominates and there is a hard FAILED
gate at `|bias| > 5 °C` regardless of health composition.
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
)
from ..engine.coupling import ambient_temperature_C_effective

COMPONENT_ID = "sensor"

BASE_BIAS_INCR = 0.03  # °C/week base drift
BASE_NOISE_INCR = 0.003  # σ-°C/week base noise growth
T_REF_K = 423.0
EA_EV = 0.7
KB_EV_PER_K = 8.617e-5

BIAS_HARD_FAIL_C = 5.0
NOISE_AT_FAILURE = 0.5


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "bias_offset": 0.0,
                "noise_sigma": 0.05,
                "reading_accuracy": 1.0,
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
    operating_K = max(ambient_C + 273.15, 250.0)
    af = math.exp((EA_EV / KB_EV_PER_K) * (1.0 / T_REF_K - 1.0 / operating_K))

    temp_stress_bonus = 1.0 + 0.3 * temp_eff
    corrosion_amp = 1.0 + 0.5 * humid_eff

    bias_increment = BASE_BIAS_INCR * af * temp_stress_bonus * corrosion_amp * damp * dt
    noise_increment = BASE_NOISE_INCR * (1.0 + 0.4 * load_eff) * damp * dt

    prev_bias = float(prev_self.metrics.get("bias_offset", 0.0))
    prev_noise = float(prev_self.metrics.get("noise_sigma", 0.0))

    new_bias = prev_bias + bias_increment  # sign convention: monotone +1.
    new_noise = prev_noise + noise_increment

    accuracy_from_bias = clip01(1.0 - abs(new_bias) / BIAS_HARD_FAIL_C)
    accuracy_from_noise = clip01(1.0 - new_noise / NOISE_AT_FAILURE)
    reading_accuracy = clip01(0.7 * accuracy_from_bias + 0.3 * accuracy_from_noise)

    if abs(new_bias) > BIAS_HARD_FAIL_C:
        # Hard FAILED gate per doc 04 — no health composition saves us.
        health = 0.0
        status = OperationalStatus.FAILED
    else:
        health = clip01(reading_accuracy)
        status = status_from_health(health)

    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=health,
        status=status,
        metrics=ComponentState.freeze_metrics(
            {
                "bias_offset": new_bias,
                "noise_sigma": new_noise,
                "reading_accuracy": reading_accuracy,
            }
        ),
        age_ticks=prev_self.age_ticks + 1,
    )


def reset(
    prev_self: ComponentState,
    kind: OperatorEventKind,
    payload: Mapping[str, float],  # noqa: ARG001
) -> ComponentState:
    """Doc 09: sensor FIX = calibrate (bias → 0, noise unchanged because
    connector oxidation is irreversible without REPLACE); REPLACE → fresh.
    """
    if kind is OperatorEventKind.REPLACE:
        return initial_state()
    if kind is OperatorEventKind.FIX:
        prev_noise = float(prev_self.metrics.get("noise_sigma", 0.0))
        new_accuracy = clip01(0.7 * 1.0 + 0.3 * (1.0 - prev_noise / NOISE_AT_FAILURE))
        return ComponentState(
            component_id=COMPONENT_ID,
            health_index=new_accuracy,
            status=status_from_health(new_accuracy),
            metrics=ComponentState.freeze_metrics(
                {
                    "bias_offset": 0.0,
                    "noise_sigma": prev_noise,
                    "reading_accuracy": new_accuracy,
                }
            ),
            age_ticks=prev_self.age_ticks,
        )
    return prev_self
