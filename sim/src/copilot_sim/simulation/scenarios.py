"""Pydantic scenario config + YAML loader.

Schema mirrors `sim/scenarios/*.yaml`. Unknown `kind:` values fail-fast
at load time (pydantic discriminator). The loader returns a fully built
`(DriverProfile, Engine, ChaosOverlay, ...)` bundle ready to feed into
`SimulationLoop`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ..drivers_src.assembly import DriverProfile
from ..drivers_src.chaos import ChaosOverlay
from ..drivers_src.environment import Environment
from ..drivers_src.generators import (
    DriverGenerator,
    MonotonicDutyLoad,
    OUHumidity,
    SinusoidalSeasonalTemp,
    StepMaintenance,
)


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


class HumidCfg(_Strict):
    kind: str = Field(pattern=r"^ornstein_uhlenbeck$")
    mean: float
    theta: float
    sigma: float


class LoadCfg(_Strict):
    kind: str = Field(pattern=r"^monotonic_duty_cycle$")
    base: float
    monotonic_drift_per_year: float = 0.02
    duty_cycle_amplitude: float = 0.10


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


class ScenarioConfig(_Strict):
    run: RunCfg
    environment: EnvCfg
    drivers: DriversCfg
    chaos: ChaosCfg = Field(default_factory=ChaosCfg)
    policy: PolicyCfg = Field(default_factory=lambda: PolicyCfg(kind="heuristic"))
    historian: HistorianCfg = Field(default_factory=HistorianCfg)


def load_scenario(path: str | Path) -> ScenarioConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ScenarioConfig.model_validate(raw)


# --- generator builders ----------------------------------------------------
def build_temperature(cfg: TempCfg) -> DriverGenerator:
    return SinusoidalSeasonalTemp(
        base=cfg.base, amplitude=cfg.amplitude, period_weeks=cfg.period_weeks
    )


def build_humidity(cfg: HumidCfg) -> DriverGenerator:
    return OUHumidity(mean=cfg.mean, theta=cfg.theta, sigma=cfg.sigma)


def build_load(cfg: LoadCfg) -> DriverGenerator:
    return MonotonicDutyLoad(
        base=cfg.base,
        monotonic_drift_per_year=cfg.monotonic_drift_per_year,
        duty_cycle_amplitude=cfg.duty_cycle_amplitude,
    )


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


def build_driver_profile(config: ScenarioConfig) -> DriverProfile:
    return DriverProfile(
        temperature_gen=build_temperature(config.drivers.temperature_stress),
        humidity_gen=build_humidity(config.drivers.humidity_contamination),
        load_gen=build_load(config.drivers.operational_load),
        maintenance_gen=build_maintenance(config.drivers.maintenance_level),
        base_environment=build_environment(config.environment),
        chaos=build_chaos(config.chaos, config.run.horizon_ticks),
        seed=config.run.seed,
    )
