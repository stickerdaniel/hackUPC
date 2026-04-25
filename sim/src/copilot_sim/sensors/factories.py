"""Per-component sensor models.

Three flavours, all implementing the `SensorModel` protocol:

- `GaussianSensorModel` — direct readout of every true metric with a
  small additive gaussian noise. Used for blade, rail, nozzle, cleaning
  (load cell / encoder / optical drop detection / wiper-camera).
- `SensorMediatedHeaterModel` — heater readings flow through the
  temperature sensor: every metric picks up the sensor's `bias_offset`
  and the gaussian noise picks up the sensor's `noise_sigma`. When the
  sensor degrades the heater's *observed* picture diverges from its true
  state — that is the §3.4 sensor-fault-vs-component-fault story.
- `SelfSensorModel` — the sensor component sees itself directly (no meta-
  sensor on the sensor), per the plan's §sensor self-observation note.

`sensor_note` is set categorically from the underlying sensor's status —
"ok" / "noisy" / "drift" / "stuck" / "absent" — so the policy and the
co-pilot can decide how much to trust each row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ..domain.enums import OperationalStatus
from ..domain.state import ComponentState, ObservedComponentState, PrinterState
from .model import SensorModel


def _sensor_note_from_status(status: OperationalStatus) -> str:
    if status is OperationalStatus.FAILED:
        return "stuck"
    if status is OperationalStatus.CRITICAL:
        return "drift"
    if status is OperationalStatus.DEGRADED:
        return "noisy"
    return "ok"


def _build_observed(
    component_id: str,
    observed_metrics: Mapping[str, float | None],
    sensor_health_value: float,
    sensor_note: str,
    observed_health: float | None,
    observed_status: OperationalStatus | None,
) -> ObservedComponentState:
    sensor_health: dict[str, float | None] = {k: sensor_health_value for k in observed_metrics}
    return ObservedComponentState(
        component_id=component_id,
        observed_metrics=ObservedComponentState.freeze_metrics(dict(observed_metrics)),
        sensor_health=ObservedComponentState.freeze_sensor_health(sensor_health),
        sensor_note=sensor_note,
        observed_health_index=observed_health,
        observed_status=observed_status,
    )


@dataclass(frozen=True, slots=True)
class GaussianSensorModel:
    noise_sigma: float = 0.01

    def observe(
        self,
        true_self: ComponentState,
        system: PrinterState,  # noqa: ARG002 — not used by the simple direct readout
        rng: np.random.Generator,
    ) -> ObservedComponentState:
        observed_metrics: dict[str, float | None] = {
            k: float(v) + float(rng.normal(0.0, self.noise_sigma))
            for k, v in true_self.metrics.items()
        }
        return _build_observed(
            component_id=true_self.component_id,
            observed_metrics=observed_metrics,
            sensor_health_value=1.0,
            sensor_note="ok",
            observed_health=true_self.health_index,
            observed_status=true_self.status,
        )


@dataclass(frozen=True, slots=True)
class SensorMediatedHeaterModel:
    """Heater readings ride through the temperature sensor.

    `observed = true + sensor.bias_offset + N(0, sensor.noise_sigma)` per
    metric. As the sensor itself degrades, observed_status migrates toward
    UNKNOWN: when the sensor's status hits FAILED, every heater observed
    metric drops to `None` (the dropout case) and observed_status becomes
    UNKNOWN.
    """

    def observe(
        self,
        true_self: ComponentState,
        system: PrinterState,
        rng: np.random.Generator,
    ) -> ObservedComponentState:
        sensor_state = system.components.get("sensor")
        if sensor_state is None:
            return GaussianSensorModel().observe(true_self, system, rng)

        bias = float(sensor_state.metrics.get("bias_offset", 0.0))
        sigma = float(sensor_state.metrics.get("noise_sigma", 0.0))
        sensor_status = sensor_state.status
        note = _sensor_note_from_status(sensor_status)
        sensor_health_value = float(sensor_state.health_index)

        # Stuck-at-None when the sensor is FAILED: no observation recoverable.
        if sensor_status is OperationalStatus.FAILED:
            observed_metrics: dict[str, float | None] = {k: None for k in true_self.metrics}
            return _build_observed(
                component_id=true_self.component_id,
                observed_metrics=observed_metrics,
                sensor_health_value=sensor_health_value,
                sensor_note="stuck",
                observed_health=None,
                observed_status=OperationalStatus.UNKNOWN,
            )

        observed_metrics = {
            k: float(v) + bias + float(rng.normal(0.0, sigma)) for k, v in true_self.metrics.items()
        }
        # Observed health crudely tracks true health but is biased toward
        # the sensor's confidence — a noisy sensor still passes through but
        # we hold sensor_health_value low to flag the trust level.
        return _build_observed(
            component_id=true_self.component_id,
            observed_metrics=observed_metrics,
            sensor_health_value=sensor_health_value,
            sensor_note=note,
            observed_health=true_self.health_index,
            observed_status=true_self.status,
        )


@dataclass(frozen=True, slots=True)
class SelfSensorModel:
    """The sensor component reports its own true bias as observed."""

    def observe(
        self,
        true_self: ComponentState,
        system: PrinterState,  # noqa: ARG002
        rng: np.random.Generator,  # noqa: ARG002
    ) -> ObservedComponentState:
        observed_metrics: dict[str, float | None] = {
            k: float(v) for k, v in true_self.metrics.items()
        }
        return _build_observed(
            component_id=true_self.component_id,
            observed_metrics=observed_metrics,
            sensor_health_value=1.0,
            sensor_note="ok",
            observed_health=true_self.health_index,
            observed_status=true_self.status,
        )


_SENSOR_MODELS: dict[str, SensorModel] = {
    "blade": GaussianSensorModel(noise_sigma=0.005),
    "rail": GaussianSensorModel(noise_sigma=0.005),
    "nozzle": GaussianSensorModel(noise_sigma=0.01),
    "cleaning": GaussianSensorModel(noise_sigma=0.005),
    "heater": SensorMediatedHeaterModel(),
    "sensor": SelfSensorModel(),
}


def make_sensor_model(component_id: str) -> SensorModel:
    """Lookup factory the engine asks per component_id."""
    return _SENSOR_MODELS[component_id]
