"""`Engine.step` — the coupled discrete-time orchestrator.

Pure function of `(prev, drivers, env, dt)` plus the `scenario_seed` baked
in at construction. Every per-tick stochastic choice flows through
`derive_component_rng` so the result is bit-identical across processes
(`PYTHONHASHSEED` cannot perturb component iteration order). All six
component step functions read from the same immutable previous state +
the same `CouplingContext`, so reordering them cannot change the result.

`Engine.apply_maintenance` is intentionally NOT implemented in this
commit; it lands in A12 once the per-component reset rules are wired up.
"""

from __future__ import annotations

from ..components import registry
from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.enums import PrintOutcome
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
        observed = build_observed_state(next_state)
        return next_state, observed, coupling


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
