"""Component registry — single source of truth for the six modeled components.

The engine never imports per-component modules directly; it iterates this
registry. That decoupling means each component (`blade.py`, `rail.py`, …)
can land in its own commit and only needs to satisfy the
`ComponentStepFn` / `ComponentResetFn` / `ComponentInitFn` contracts to be
wired into `Engine.step`.

Component identifiers (`COMPONENT_IDS`) are also the canonical iteration
order for the engine and the historian.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.enums import OperatorEventKind
from ..domain.state import ComponentState
from ..drivers_src.environment import Environment
from . import blade, cleaning, heater, nozzle, rail, sensor

ComponentInitFn = Callable[[], ComponentState]
ComponentStepFn = Callable[
    [ComponentState, CouplingContext, Drivers, Environment, float, np.random.Generator],
    ComponentState,
]
ComponentResetFn = Callable[
    [ComponentState, OperatorEventKind, Mapping[str, float]], ComponentState
]


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    component_id: str
    initial_state: ComponentInitFn
    step: ComponentStepFn
    reset: ComponentResetFn


# Canonical iteration order. Engine, sensors and historian all walk this
# list. Order is deliberate: blade and rail (recoating) → nozzle and
# cleaning (printhead) → heater and sensor (thermal). Within a subsystem
# the "sensored" component is listed second so failure-analysis output is
# easier to read top-down.
COMPONENT_IDS: tuple[str, ...] = (
    "blade",
    "rail",
    "nozzle",
    "cleaning",
    "heater",
    "sensor",
)


REGISTRY: Mapping[str, ComponentSpec] = {
    "blade": ComponentSpec(
        component_id="blade",
        initial_state=blade.initial_state,
        step=blade.step,
        reset=blade.reset,
    ),
    "rail": ComponentSpec(
        component_id="rail",
        initial_state=rail.initial_state,
        step=rail.step,
        reset=rail.reset,
    ),
    "nozzle": ComponentSpec(
        component_id="nozzle",
        initial_state=nozzle.initial_state,
        step=nozzle.step,
        reset=nozzle.reset,
    ),
    "cleaning": ComponentSpec(
        component_id="cleaning",
        initial_state=cleaning.initial_state,
        step=cleaning.step,
        reset=cleaning.reset,
    ),
    "heater": ComponentSpec(
        component_id="heater",
        initial_state=heater.initial_state,
        step=heater.step,
        reset=heater.reset,
    ),
    "sensor": ComponentSpec(
        component_id="sensor",
        initial_state=sensor.initial_state,
        step=sensor.step,
        reset=sensor.reset,
    ),
}


def initial_components() -> dict[str, ComponentState]:
    """Fresh component state for every registered component."""
    return {cid: REGISTRY[cid].initial_state() for cid in COMPONENT_IDS}
