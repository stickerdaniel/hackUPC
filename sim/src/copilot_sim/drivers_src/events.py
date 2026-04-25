"""Named-event overlay — a sibling of `ChaosOverlay` for narrative one-off
events (earthquake, HVAC failure, operator holiday, ...).

Distinct from chaos in three ways:

1. **Named** — every event carries a `name` that lands on the historian's
   `environmental_events` table, so a Phase 3 chatbot can answer "what
   happened in week 27?" with a real attribution.
2. **Scheduled** — events fire on a deterministic `output_tick` taken
   straight from the YAML, no RNG. Same scenario file → same firings.
3. **Both surfaces** — events can patch either `Drivers` (e.g. zero
   `maintenance_level`) or `Environment` (e.g. spike `vibration_level`).
   Chaos can only touch the three drivers it knows about.

Layer ordering at sample time (locked in the plan):
    generators → chaos.apply(scalars) → clip drivers to [0, 1]
    → Drivers/Environment construction → events.apply(Drivers, Environment)
The driver clip happens BEFORE events; `EventCfg.driver_overrides` values
are validated to `[0, 1]` at YAML-load, so no post-event clip is needed.

Override semantics: SET, not max. `vibration_level: 0.85` sets the env
field to 0.85 for the affected ticks. If multiple active events touch
the same field, the LAST one in the YAML wins (stable, predictable).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from ..domain.drivers import Drivers
from .environment import Environment


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    """One row from the YAML `events:` list, expanded to a tick range.

    `output_tick` is the historian-facing tick (operator-facing surface);
    the event is *active* on output ticks
    `[output_tick, output_tick + duration - 1]` inclusive.
    """

    output_tick: int
    name: str
    duration: int
    driver_overrides: Mapping[str, float]
    env_overrides: Mapping[str, float]
    disable_human_maintenance: bool = False

    def is_active_at(self, output_tick: int) -> bool:
        return self.output_tick <= output_tick < self.output_tick + self.duration


@dataclass(slots=True)
class EventOverlay:
    """Mirrors `ChaosOverlay`'s shape so `DriverProfile` can treat both
    overlays uniformly. Empty default → fully passthrough; `EventOverlay()`
    is what every existing constructor falls back to via the
    `field(default_factory=EventOverlay)` field on `DriverProfile`.
    """

    events: tuple[ScheduledEvent, ...] = field(default_factory=tuple)

    def roll(self, seed: int) -> None:  # noqa: ARG002 — symmetry with ChaosOverlay
        """No-op. Events are deterministic; the method exists only so
        `DriverProfile.__post_init__` can call it without branching.
        """

    def fired_at(self, output_tick: int) -> list[ScheduledEvent]:
        return [e for e in self.events if e.is_active_at(output_tick)]

    def apply(
        self,
        output_tick: int,
        drivers: Drivers,
        env: Environment,
    ) -> tuple[Drivers, Environment, list[ScheduledEvent]]:
        """Patch `drivers` and `env` according to every event active at
        `output_tick`. Returns the (possibly-unchanged) pair plus the list
        of fired events (empty when nothing fires — typical case)."""
        active = self.fired_at(output_tick)
        if not active:
            return drivers, env, active

        driver_patch: dict[str, float] = {}
        env_patch: dict[str, float] = {}
        for event in active:
            # Last-event-wins composition: later events overwrite earlier
            # entries in the patch dicts.
            driver_patch.update({k: float(v) for k, v in event.driver_overrides.items()})
            env_patch.update({k: float(v) for k, v in event.env_overrides.items()})

        new_drivers = replace(drivers, **driver_patch) if driver_patch else drivers
        new_env = replace(env, **env_patch) if env_patch else env
        return new_drivers, new_env, active
