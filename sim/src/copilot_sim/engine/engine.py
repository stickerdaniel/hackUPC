"""`Engine.step` + `Engine.apply_maintenance` — the coupled engine API.

`step` is a pure function of `(prev, drivers, env, dt)` plus the
`scenario_seed` baked in at construction. Every per-tick stochastic
choice flows through `derive_component_rng` so the result is bit-identical
across processes (`PYTHONHASHSEED` cannot perturb component iteration
order). All six component step functions read from the same immutable
previous state + the same `CouplingContext`, so reordering them cannot
change the result.

`apply_maintenance` is intentionally out-of-band — the simulation loop
calls it BETWEEN `step()` calls, never inside one (doc 20 §maintenance
ordering). It dispatches to the per-component reset rules in
`components/<x>.py` and produces an `OperatorEvent` row for the historian.
"""

from __future__ import annotations

from ..components import registry
from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.enums import OperatorEventKind, PrintOutcome
from ..domain.events import MaintenanceAction, OperatorEvent
from ..domain.state import ObservedPrinterState, PrinterState
from ..drivers_src.environment import Environment
from .aging import derive_component_rng
from .assembly import build_observed_state, derive_print_outcome
from .coupling import build_coupling_context


class Engine:
    def __init__(self, scenario_seed: int) -> None:
        self.scenario_seed = int(scenario_seed)

    def step(
        self,
        prev: PrinterState,
        drivers: Drivers,
        env: Environment,
        dt: float,
    ) -> tuple[PrinterState, ObservedPrinterState, CouplingContext]:
        coupling = build_coupling_context(prev, drivers, env, dt)

        next_components = {}
        next_tick = prev.tick + 1
        for component_id in registry.COMPONENT_IDS:
            spec = registry.REGISTRY[component_id]
            prev_self = prev.components[component_id]
            rng = derive_component_rng(self.scenario_seed, next_tick, component_id)
            next_components[component_id] = spec.step(prev_self, coupling, drivers, env, dt, rng)

        print_outcome = derive_print_outcome(next_components)
        next_state = PrinterState(
            tick=next_tick,
            sim_time_s=prev.sim_time_s + dt,
            components=PrinterState.freeze_components(next_components),
            print_outcome=print_outcome,
        )
        sensors_rng = derive_component_rng(self.scenario_seed, next_tick, "_sensors")
        observed = build_observed_state(next_state, sensors_rng)
        return next_state, observed, coupling

    def apply_maintenance(
        self,
        state: PrinterState,
        action: MaintenanceAction,
    ) -> tuple[PrinterState, OperatorEvent]:
        """Dispatch `action` to the targeted component's reset rule and
        assemble a new `PrinterState`. `TROUBLESHOOT` is a no-op on state —
        it only writes an event row (sets `last_inspected_tick` semantics
        on the loop side via the returned event).
        """
        if action.component_id not in state.components:
            raise KeyError(f"Unknown component_id in MaintenanceAction: {action.component_id!r}")

        new_components = dict(state.components)
        if action.kind is not OperatorEventKind.TROUBLESHOOT:
            spec = registry.REGISTRY[action.component_id]
            prev_component = state.components[action.component_id]
            new_components[action.component_id] = spec.reset(
                prev_component, action.kind, action.payload
            )

        # Print outcome may shift if the targeted component was the one
        # holding everything in QUALITY_DEGRADED / HALTED.
        print_outcome = derive_print_outcome(new_components)

        new_state = PrinterState(
            tick=state.tick,
            sim_time_s=state.sim_time_s,
            components=PrinterState.freeze_components(new_components),
            print_outcome=print_outcome,
        )
        event = OperatorEvent(
            tick=state.tick,
            sim_time_s=state.sim_time_s,
            kind=action.kind,
            component_id=action.component_id,
            payload=OperatorEvent.freeze_payload(dict(action.payload)),
        )
        return new_state, event


def initial_state() -> PrinterState:
    """Bootstrap: t=0 PrinterState built from the registry's initial states.

    Lives on the engine module instead of `simulation/bootstrap.py` because
    every test that exercises the engine wants this convenience without
    importing the simulation loop.
    """
    return PrinterState(
        tick=0,
        sim_time_s=0.0,
        components=PrinterState.freeze_components(registry.initial_components()),
        print_outcome=PrintOutcome.OK,
    )
