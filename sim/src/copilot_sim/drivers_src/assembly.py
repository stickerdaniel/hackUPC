"""DriverProfile — assembles the four generators + chaos + event overlays
into a single `sample(tick_index)` that returns a `SampledStep`.

Layer order:
    generators (scalars) → chaos.apply(scalars) → clip drivers to [0, 1]
    → Drivers/Environment construction → events.apply(Drivers, Environment)
    → SampledStep

Chaos is the only stage that touches raw scalars (mirrors its existing
signature). Driver clipping happens BEFORE events; events operate on a
typed, in-bounds `Drivers` object. `Environment` passes through unclipped
because clipping `base_ambient_C=22` to `[0, 1]` would obliterate the
calibration. Per-key range checks for env overrides live in the YAML
loader (`EventCfg`), not here.

`sample` returns a `SampledStep` dataclass instead of a tuple so future
overlays can append fields without breaking tuple-unpacking call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..domain.drivers import Drivers
from .chaos import ChaosOverlay
from .environment import Environment
from .events import EventOverlay, ScheduledEvent
from .generators import DriverGenerator


@dataclass(frozen=True, slots=True)
class SampledStep:
    """One tick's worth of driver/env/events output."""

    drivers: Drivers
    env: Environment
    fired_events: tuple[ScheduledEvent, ...]


@dataclass(slots=True)
class DriverProfile:
    temperature_gen: DriverGenerator
    humidity_gen: DriverGenerator
    load_gen: DriverGenerator
    maintenance_gen: DriverGenerator
    base_environment: Environment
    chaos: ChaosOverlay
    seed: int = 0
    # Default factory keeps legacy constructors (test_drivers._profile,
    # build_driver_profile pre-event-overlay) compiling without changes —
    # the empty overlay is fully passthrough.
    events: EventOverlay = field(default_factory=EventOverlay)
    _rng: np.random.Generator | None = None

    def __post_init__(self) -> None:
        # Stateful generators (OU) need a single owned RNG; pre-roll chaos.
        self._rng = np.random.default_rng((int(self.seed), 0xD7_1A_E9))
        self.chaos.horizon_ticks = max(self.chaos.horizon_ticks, 0)
        self.chaos.roll(self.seed)
        self.events.roll(self.seed)  # no-op today; symmetry with chaos.

    def sample(self, tick_index: int) -> SampledStep:
        rng = self._rng
        assert rng is not None
        env = self.base_environment

        # Generators produce scalars …
        temp = self.temperature_gen.sample(tick_index, env, rng)
        humid = self.humidity_gen.sample(tick_index, env, rng)
        load = self.load_gen.sample(tick_index, env, rng)
        maint = self.maintenance_gen.sample(tick_index, env, rng)

        # … chaos modifies scalars …
        temp, humid, maint = self.chaos.apply(tick_index, temp, humid, maint)

        # … clip + construct Drivers (last point we ever hold raw scalars).
        drivers = Drivers(
            temperature_stress=float(np.clip(temp, 0.0, 1.0)),
            humidity_contamination=float(np.clip(humid, 0.0, 1.0)),
            operational_load=float(np.clip(load, 0.0, 1.0)),
            maintenance_level=float(np.clip(maint, 0.0, 1.0)),
        )

        # … events run on the typed surfaces. The output_tick maps to
        # Engine.step's `prev.tick + 1` because the loop always advances
        # the printer state after sampling.
        output_tick = tick_index + 1
        drivers, env, fired = self.events.apply(output_tick, drivers, env)

        return SampledStep(drivers=drivers, env=env, fired_events=tuple(fired))
