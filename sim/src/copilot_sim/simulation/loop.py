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

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..domain.state import PrinterState
from ..drivers_src.assembly import DriverProfile
from ..engine.engine import Engine
from ..historian.writer import HistorianWriter
from ..policy.heuristic import HeuristicPolicy


@dataclass(slots=True)
class SimulationLoop:
    engine: Engine
    profile: DriverProfile
    policy: HeuristicPolicy | None
    writer: HistorianWriter
    horizon_ticks: int
    dt_seconds: int = 604800
    start_time: datetime | None = None

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

            if self.policy is not None and human_maintenance_enabled:
                actions = self.policy.decide(observed, tick=new_state.tick)
                for action in actions:
                    state, event = self.engine.apply_maintenance(state, action)
                    self.writer.write_event(event, ts_iso=ts_iso)

        self.writer.close()
        return state
