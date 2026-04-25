"""Per-driver generators conforming to the `DriverGenerator` protocol.

All four generators are deterministic for a given `(rng, tick)` pair so
running the same scenario twice produces byte-identical driver streams.
Reads only from the seeded `rng` and the per-scenario static config; the
`Environment` is passed for symmetry but the v1 generators ignore it.

- `SinusoidalSeasonalTemp` — yearly cosine on `temperature_stress`. Base
  + amplitude knobs match the YAML schema.
- `OUHumidity` — Ornstein-Uhlenbeck integrator on `humidity_contamination`
  (mean-reverting around `mean` with stiffness `theta` and gaussian
  shocks `sigma`). Requires per-call state, kept on the generator.
- `MonotonicDutyLoad` — `operational_load` rises linearly with year-on-
  year drift, plus a weekly duty-cycle wobble for visual interest.
- `StepMaintenance` — `maintenance_level` follows a piecewise-constant
  schedule of `{tick: value}` pairs.

The protocol is `sample(tick, env, rng) -> float` so a chaos overlay can
post-process the value.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from .environment import Environment


class DriverGenerator(Protocol):
    def sample(self, tick: int, env: Environment, rng: np.random.Generator) -> float: ...


@dataclass(slots=True)
class SinusoidalSeasonalTemp:
    base: float
    amplitude: float
    period_weeks: float = 52.0

    def sample(
        self,
        tick: int,
        env: Environment,  # noqa: ARG002
        rng: np.random.Generator,  # noqa: ARG002
    ) -> float:
        phase = 2.0 * math.pi * tick / self.period_weeks
        return float(self.base + self.amplitude * math.cos(phase))


@dataclass(slots=True)
class OUHumidity:
    mean: float
    theta: float
    sigma: float
    _state: float | None = field(default=None, init=False)

    def sample(
        self,
        tick: int,  # noqa: ARG002 — OU is a stateful integrator, not tick-keyed
        env: Environment,  # noqa: ARG002
        rng: np.random.Generator,
    ) -> float:
        if self._state is None:
            self._state = self.mean
        # Discrete OU step: x_{t+1} = x_t + theta·(mu − x_t) + sigma·N(0,1)
        shock = float(rng.standard_normal())
        next_x = self._state + self.theta * (self.mean - self._state) + self.sigma * shock
        self._state = float(np.clip(next_x, 0.0, 1.0))
        return self._state


@dataclass(slots=True)
class MonotonicDutyLoad:
    base: float
    monotonic_drift_per_year: float = 0.02
    duty_cycle_amplitude: float = 0.10
    weeks_per_year: float = 52.0

    def sample(
        self,
        tick: int,
        env: Environment,  # noqa: ARG002
        rng: np.random.Generator,  # noqa: ARG002
    ) -> float:
        years = tick / self.weeks_per_year
        # Three-week duty wobble keeps the chart visually busy.
        wobble = self.duty_cycle_amplitude * math.sin(2.0 * math.pi * tick / 3.0)
        value = self.base + self.monotonic_drift_per_year * years + wobble
        return float(np.clip(value, 0.0, 1.0))


@dataclass(slots=True)
class StepMaintenance:
    """Piecewise-constant schedule. `schedule = [{tick: 0, value: 0.7}, ...]`.

    The most recent entry whose `tick` is `<=` the current tick wins.
    """

    schedule: Sequence[Mapping[str, float]]

    def sample(
        self,
        tick: int,
        env: Environment,  # noqa: ARG002
        rng: np.random.Generator,  # noqa: ARG002
    ) -> float:
        active = 0.0
        for entry in self.schedule:
            entry_tick = float(entry.get("tick", 0))
            if entry_tick <= tick:
                active = float(entry.get("value", 0.0))
        return float(np.clip(active, 0.0, 1.0))
