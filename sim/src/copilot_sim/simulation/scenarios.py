"""Pydantic scenario config + YAML loader.

Schema mirrors `sim/scenarios/*.yaml`. Unknown `kind:` values fail-fast
at load time (pydantic discriminator). The loader returns a fully built
`(DriverProfile, Engine, ChaosOverlay, ...)` bundle ready to feed into
`SimulationLoop`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..drivers_src.assembly import DriverProfile
from ..drivers_src.chaos import ChaosOverlay
from ..drivers_src.environment import Environment
from ..drivers_src.events import EventOverlay, ScheduledEvent
from ..drivers_src.generators import (
    DriverGenerator,
    MonotonicDutyLoad,
    OUHumidity,
    SinusoidalSeasonalTemp,
    SmoothSyntheticOperationalLoad,
    StepMaintenance,
)

# Allowed override keys + per-key range constraints. Keys outside these
# sets fail validation; values outside the ranges fail validation. Catch
# typos like `vibration_level: 8.5` (vs the intended 0.85) at YAML load
# instead of via mysterious 5× rail wear at runtime.
_DRIVER_KEYS: frozenset[str] = frozenset(
    {"temperature_stress", "humidity_contamination", "operational_load", "maintenance_level"}
)
_ENV_KEY_RANGES: dict[str, tuple[float | None, float | None]] = {
    # vibration_level enters rail.py as `1 + 0.5 * env.vibration_level`;
    # values > 1 explode the wear rate.
    "vibration_level": (0.0, 1.0),
    # one week = 168 hours.
    "weekly_runtime_hours": (0.0, 168.0),
    # symmetric ± swing on the seasonal envelope.
    "amplitude_C": (0.0, 50.0),
    # nominal ambient — winter facilities can run sub-zero, leave unbounded.
    "base_ambient_C": (None, None),
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunCfg(_Strict):
    scenario: str
    profile: str
    seed: int
    horizon_ticks: int
    dt_seconds: int = 604800


class EnvCfg(_Strict):
    base_ambient_C: float
    amplitude_C: float
    weekly_runtime_hours: float
    vibration_level: float = 0.10


class TempCfg(_Strict):
    kind: str = Field(pattern=r"^sinusoidal_seasonal$")
    base: float
    amplitude: float
    period_weeks: float = 52.0
    weekly_wobble_amplitude: float = 0.02
    noise_sigma: float = 0.01
    noise_theta: float = 0.35


class HumidCfg(_Strict):
    kind: str = Field(pattern=r"^ornstein_uhlenbeck$")
    mean: float
    theta: float
    sigma: float


class LoadCfg(_Strict):
    kind: str = Field(pattern=r"^(monotonic_duty_cycle|smooth_synthetic)$")

    # shared
    weeks_per_year: float = 52.0

    # monotonic_duty_cycle
    base: float = 0.45
    monotonic_drift_per_year: float = 0.02
    duty_cycle_amplitude: float = 0.10

    # smooth_synthetic
    mean: float = 0.55
    theta: float = 0.25
    sigma: float = 0.12
    annual_amplitude: float = 0.15
    idle_probability: float = 0.05
    overload_probability: float = 0.04


class StepEntry(_Strict):
    tick: int
    value: float


class MaintCfg(_Strict):
    kind: str = Field(pattern=r"^step$")
    schedule: Sequence[StepEntry]


class DriversCfg(_Strict):
    temperature_stress: TempCfg
    humidity_contamination: HumidCfg
    operational_load: LoadCfg
    maintenance_level: MaintCfg


class ChaosCfg(_Strict):
    enabled: bool = False
    temp_spike_lambda_per_year: float = 4.0
    contamination_burst_lambda_per_year: float = 6.0
    skipped_maintenance_p: float = 0.10


class PolicyCfg(_Strict):
    kind: str = Field(pattern=r"^(heuristic|none)$")


class HistorianCfg(_Strict):
    path: str = "data/historian.sqlite"


class EventCfg(_Strict):
    """One named environmental event from the YAML `events:` list.

    `tick` is the **historian-facing output tick** (1..horizon_ticks
    inclusive), not the loop's internal tick_index. The cross-field
    horizon check lives on `ScenarioConfig.model_validator` because
    `EventCfg` cannot see `run.horizon_ticks`.
    """

    tick: int = Field(ge=1)
    name: str
    duration: int = Field(default=1, ge=1)
    driver_overrides: dict[str, float] = Field(default_factory=dict)
    env_overrides: dict[str, float] = Field(default_factory=dict)
    disable_human_maintenance: bool = False

    @field_validator("driver_overrides")
    @classmethod
    def _validate_driver_overrides(cls, v: dict[str, float]) -> dict[str, float]:
        bad_keys = set(v.keys()) - _DRIVER_KEYS
        if bad_keys:
            raise ValueError(
                f"unknown driver_overrides keys {sorted(bad_keys)}; allowed: {sorted(_DRIVER_KEYS)}"
            )
        for key, value in v.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(
                    f"driver_overrides[{key}] = {value} outside [0, 1]; "
                    "Drivers fields are bounded by the brief contract"
                )
        return {k: float(val) for k, val in v.items()}

    @field_validator("env_overrides")
    @classmethod
    def _validate_env_overrides(cls, v: dict[str, float]) -> dict[str, float]:
        bad_keys = set(v.keys()) - set(_ENV_KEY_RANGES.keys())
        if bad_keys:
            raise ValueError(
                f"unknown env_overrides keys {sorted(bad_keys)}; "
                f"allowed: {sorted(_ENV_KEY_RANGES.keys())}"
            )
        for key, value in v.items():
            lo, hi = _ENV_KEY_RANGES[key]
            value_f = float(value)
            if lo is not None and value_f < lo:
                raise ValueError(f"env_overrides[{key}] = {value} below minimum {lo}")
            if hi is not None and value_f > hi:
                raise ValueError(f"env_overrides[{key}] = {value} above maximum {hi}")
        return {k: float(val) for k, val in v.items()}


class ScenarioConfig(_Strict):
    run: RunCfg
    environment: EnvCfg
    drivers: DriversCfg
    chaos: ChaosCfg = Field(default_factory=ChaosCfg)
    events: list[EventCfg] = Field(default_factory=list)
    policy: PolicyCfg = Field(default_factory=lambda: PolicyCfg(kind="heuristic"))
    historian: HistorianCfg = Field(default_factory=HistorianCfg)

    @model_validator(mode="after")
    def _validate_event_horizon(self) -> Self:
        """Cross-model: every event must fall inside `[1, horizon_ticks]`."""
        horizon = self.run.horizon_ticks
        for event in self.events:
            last_active = event.tick + event.duration - 1
            if last_active > horizon:
                raise ValueError(
                    f"event {event.name!r} tick={event.tick} duration={event.duration} "
                    f"extends to tick {last_active} > horizon_ticks {horizon}"
                )
        return self


def load_scenario(path: str | Path) -> ScenarioConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ScenarioConfig.model_validate(raw)


# --- generator builders ----------------------------------------------------
def build_temperature(cfg: TempCfg) -> DriverGenerator:
    return SinusoidalSeasonalTemp(
        base=cfg.base,
        amplitude=cfg.amplitude,
        period_weeks=cfg.period_weeks,
        weekly_wobble_amplitude=cfg.weekly_wobble_amplitude,
        noise_sigma=cfg.noise_sigma,
        noise_theta=cfg.noise_theta,
    )


def build_humidity(cfg: HumidCfg) -> DriverGenerator:
    return OUHumidity(mean=cfg.mean, theta=cfg.theta, sigma=cfg.sigma)


def build_load(cfg: LoadCfg) -> DriverGenerator:
    if cfg.kind == "monotonic_duty_cycle":
        return MonotonicDutyLoad(
            base=cfg.base,
            monotonic_drift_per_year=cfg.monotonic_drift_per_year,
            duty_cycle_amplitude=cfg.duty_cycle_amplitude,
            weeks_per_year=cfg.weeks_per_year,
        )

    if cfg.kind == "smooth_synthetic":
        return SmoothSyntheticOperationalLoad(
            mean=cfg.mean,
            theta=cfg.theta,
            sigma=cfg.sigma,
            annual_amplitude=cfg.annual_amplitude,
            idle_probability=cfg.idle_probability,
            overload_probability=cfg.overload_probability,
            weeks_per_year=cfg.weeks_per_year,
        )

    raise ValueError(f"Unknown load generator kind: {cfg.kind!r}")


def build_maintenance(cfg: MaintCfg) -> DriverGenerator:
    schedule = [{"tick": float(e.tick), "value": float(e.value)} for e in cfg.schedule]
    return StepMaintenance(schedule=schedule)


def build_environment(cfg: EnvCfg) -> Environment:
    return Environment(
        base_ambient_C=cfg.base_ambient_C,
        amplitude_C=cfg.amplitude_C,
        weekly_runtime_hours=cfg.weekly_runtime_hours,
        vibration_level=cfg.vibration_level,
        cumulative_cleanings=0,
        hours_since_maintenance=0.0,
        start_stop_cycles=0,
    )


def build_chaos(cfg: ChaosCfg, horizon_ticks: int) -> ChaosOverlay:
    return ChaosOverlay(
        enabled=cfg.enabled,
        horizon_ticks=horizon_ticks,
        temp_spike_lambda_per_year=cfg.temp_spike_lambda_per_year,
        contamination_burst_lambda_per_year=cfg.contamination_burst_lambda_per_year,
        skipped_maintenance_p=cfg.skipped_maintenance_p,
    )


def build_event_overlay(cfg_events: list[EventCfg], horizon_ticks: int) -> EventOverlay:  # noqa: ARG001
    """Materialise the YAML event list into an EventOverlay.

    `horizon_ticks` is accepted for symmetry with `build_chaos` and to
    leave room for any future validation that needs both, but the
    cross-field horizon check already happened on the pydantic model.
    """
    scheduled = tuple(
        ScheduledEvent(
            output_tick=cfg.tick,
            name=cfg.name,
            duration=cfg.duration,
            driver_overrides=dict(cfg.driver_overrides),
            env_overrides=dict(cfg.env_overrides),
            disable_human_maintenance=bool(cfg.disable_human_maintenance),
        )
        for cfg in cfg_events
    )
    return EventOverlay(events=scheduled)


def build_driver_profile(config: ScenarioConfig) -> DriverProfile:
    return DriverProfile(
        temperature_gen=build_temperature(config.drivers.temperature_stress),
        humidity_gen=build_humidity(config.drivers.humidity_contamination),
        load_gen=build_load(config.drivers.operational_load),
        maintenance_gen=build_maintenance(config.drivers.maintenance_level),
        base_environment=build_environment(config.environment),
        chaos=build_chaos(config.chaos, config.run.horizon_ticks),
        events=build_event_overlay(config.events, config.run.horizon_ticks),
        seed=config.run.seed,
    )
