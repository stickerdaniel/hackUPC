"""Top-level simulation loop.

Per-tick flow (locked by doc 20 §What lives outside the engine):

1. Sample drivers + environment from `DriverProfile`.
2. `engine.step(prev, drivers, env, dt)` → new true + observed state +
   coupling.
3. Persist tick to historian.
4. Ask policy for `MaintenanceAction`s; for each, call
   `engine.apply_maintenance` between ticks (never inside step) and
   persist resulting `OperatorEvent` rows.
5. Loop until horizon_ticks reached.

Determinism: the engine and the driver profile each own their RNG;
nothing in the loop introduces non-determinism. Same seed + same
scenario YAML = byte-identical historian.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.events import OperatorEvent
from ..domain.state import ObservedPrinterState, PrinterState
from ..drivers_src.assembly import DriverProfile
from ..drivers_src.environment import Environment
from ..drivers_src.events import ScheduledEvent
from ..engine.engine import Engine
from ..historian.writer import HistorianWriter
from ..policy.heuristic import HeuristicPolicy


@dataclass(frozen=True, slots=True)
class TickPayload:
    """Snapshot mirroring exactly what the historian persisted for one tick.

    `components_*` reflect the *pre-maintenance* engine output (the values
    `HistorianWriter.write_tick` saved). Maintenance reset only takes effect on
    the next tick, identical to the historian's behaviour. The
    `operator_events` list captures any maintenance applied at the boundary
    between this tick and the next.
    """

    tick: int
    sim_time_s: float
    ts_iso: str
    drivers: Drivers
    env: Environment
    coupling: CouplingContext
    true_state: PrinterState
    observed: ObservedPrinterState
    env_events: tuple[ScheduledEvent, ...]
    operator_events: tuple[OperatorEvent, ...]


@dataclass(slots=True)
class SimulationLoop:
    engine: Engine
    profile: DriverProfile
    policy: HeuristicPolicy | None
    writer: HistorianWriter
    horizon_ticks: int
    dt_seconds: int = 604800
    start_time: datetime | None = None
    # Optional end-of-tick hook. Fires once per tick AFTER the maintenance
    # loop completes, so all events for the tick are collected. Component
    # snapshots in the payload are pre-maintenance — they mirror the rows
    # `write_tick` already persisted. CLI path leaves this None.
    on_tick_persisted: Callable[[TickPayload], None] | None = None

    def run(self, initial_state: PrinterState) -> PrinterState:
        state = initial_state
        start = self.start_time or datetime.now(UTC)
        human_maintenance_enabled = True
        for tick_index in range(self.horizon_ticks):
            step = self.profile.sample(tick_index)
            new_state, observed, coupling = self.engine.step(state, step.drivers, step.env, dt=1.0)

            ts = start + timedelta(seconds=self.dt_seconds * (tick_index + 1))
            ts_iso = ts.isoformat()
            self.writer.write_tick(
                true_state=new_state,
                observed=observed,
                drivers=step.drivers,
                env=step.env,
                coupling=coupling,
                ts_iso=ts_iso,
            )
            # Environmental events come from the world — recorded BEFORE
            # the operator reacts via the maintenance policy.
            for fired in step.fired_events:
                if fired.disable_human_maintenance:
                    human_maintenance_enabled = False
                self.writer.write_environmental_event(
                    name=fired.name,
                    tick=new_state.tick,
                    sim_time_s=new_state.sim_time_s,
                    payload={
                        "driver_overrides": dict(fired.driver_overrides),
                        "env_overrides": dict(fired.env_overrides),
                        "disable_human_maintenance": bool(fired.disable_human_maintenance),
                        "duration_remaining": (fired.output_tick + fired.duration - new_state.tick),
                    },
                    ts_iso=ts_iso,
                )

            state = new_state

            applied_events: list[OperatorEvent] = []
            if self.policy is not None and human_maintenance_enabled:
                actions = self.policy.decide(observed, tick=new_state.tick)
                for action in actions:
                    state, event = self.engine.apply_maintenance(state, action)
                    self.writer.write_event(event, ts_iso=ts_iso)
                    applied_events.append(event)

            if self.on_tick_persisted is not None:
                self.on_tick_persisted(
                    TickPayload(
                        tick=new_state.tick,
                        sim_time_s=new_state.sim_time_s,
                        ts_iso=ts_iso,
                        drivers=step.drivers,
                        env=step.env,
                        coupling=coupling,
                        true_state=new_state,
                        observed=observed,
                        env_events=tuple(step.fired_events),
                        operator_events=tuple(applied_events),
                    )
                )

        self.writer.close()
        return state
