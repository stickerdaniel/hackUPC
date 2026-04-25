"""True and observed state objects emitted by the engine each tick.

Kept strictly separate per `TRACK-CONTEXT.md §3.4`: `PrinterState` is the
ground-truth view used internally; `ObservedPrinterState` is what sensors
actually report and is what the maintenance policy and co-pilot consume.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .enums import OperationalStatus, PrintOutcome


@dataclass(frozen=True, slots=True)
class ComponentState:
    component_id: str
    health_index: float  # 0.0 (dead) .. 1.0 (new)
    status: OperationalStatus
    metrics: Mapping[str, float]  # physical quantities, e.g. {"blade_thickness_mm": 0.42}
    age_ticks: int

    @staticmethod
    def freeze_metrics(metrics: Mapping[str, float]) -> Mapping[str, float]:
        return MappingProxyType(dict(metrics))


@dataclass(frozen=True, slots=True)
class PrinterState:
    tick: int
    sim_time_s: float
    components: Mapping[str, ComponentState]
    print_outcome: PrintOutcome

    @staticmethod
    def freeze_components(
        components: Mapping[str, ComponentState],
    ) -> Mapping[str, ComponentState]:
        return MappingProxyType(dict(components))


@dataclass(frozen=True, slots=True)
class ObservedComponentState:
    component_id: str
    # Per-metric observed values. None ⇒ sensor absent, dropped out, or stuck-at-None.
    observed_metrics: Mapping[str, float | None]
    # Per-metric sensor health (0..1). None ⇒ no sensor for that metric.
    sensor_health: Mapping[str, float | None]
    sensor_note: str  # "ok" | "noisy" | "drift" | "stuck" | "absent" | mixed-tag
    # Derived observed view. None when too many sensors are missing/failed to
    # produce a defensible estimate.
    observed_health_index: float | None
    observed_status: OperationalStatus | None  # may be UNKNOWN

    @staticmethod
    def freeze_metrics(
        observed_metrics: Mapping[str, float | None],
    ) -> Mapping[str, float | None]:
        return MappingProxyType(dict(observed_metrics))

    @staticmethod
    def freeze_sensor_health(
        sensor_health: Mapping[str, float | None],
    ) -> Mapping[str, float | None]:
        return MappingProxyType(dict(sensor_health))


@dataclass(frozen=True, slots=True)
class ObservedPrinterState:
    tick: int
    sim_time_s: float
    components: Mapping[str, ObservedComponentState]

    @staticmethod
    def freeze_components(
        components: Mapping[str, ObservedComponentState],
    ) -> Mapping[str, ObservedComponentState]:
        return MappingProxyType(dict(components))
