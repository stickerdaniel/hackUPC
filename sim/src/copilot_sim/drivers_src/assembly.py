"""DriverProfile — assembles the four generators + chaos overlay into a
single `sample(tick)` that returns `(Drivers, Environment)`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..domain.drivers import Drivers
from .chaos import ChaosOverlay
from .environment import Environment
from .generators import DriverGenerator


@dataclass(slots=True)
class DriverProfile:
    temperature_gen: DriverGenerator
    humidity_gen: DriverGenerator
    load_gen: DriverGenerator
    maintenance_gen: DriverGenerator
    base_environment: Environment
    chaos: ChaosOverlay
    seed: int = 0
    _rng: np.random.Generator | None = None

    def __post_init__(self) -> None:
        # Stateful generators (OU) need a single owned RNG; pre-roll chaos.
        self._rng = np.random.default_rng((int(self.seed), 0xD7_1A_E9))
        self.chaos.horizon_ticks = max(self.chaos.horizon_ticks, 0)
        self.chaos.roll(self.seed)

    def sample(self, tick: int) -> tuple[Drivers, Environment]:
        rng = self._rng
        assert rng is not None
        env = self.base_environment

        temp = self.temperature_gen.sample(tick, env, rng)
        humid = self.humidity_gen.sample(tick, env, rng)
        load = self.load_gen.sample(tick, env, rng)
        maint = self.maintenance_gen.sample(tick, env, rng)

        temp, humid, maint = self.chaos.apply(tick, temp, humid, maint)

        drivers = Drivers(
            temperature_stress=float(np.clip(temp, 0.0, 1.0)),
            humidity_contamination=float(np.clip(humid, 0.0, 1.0)),
            operational_load=float(np.clip(load, 0.0, 1.0)),
            maintenance_level=float(np.clip(maint, 0.0, 1.0)),
        )
        return drivers, env
