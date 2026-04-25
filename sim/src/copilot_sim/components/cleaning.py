"""Cleaning interface (wiper + capping) — power-law wear in cumulative cleanings.

Stub in this commit; the power-law physics + smoke test land next.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ..domain.coupling import CouplingContext
from ..domain.drivers import Drivers
from ..domain.enums import OperationalStatus
from ..domain.state import ComponentState
from ..drivers_src.environment import Environment

COMPONENT_ID = "cleaning"


def initial_state() -> ComponentState:
    return ComponentState(
        component_id=COMPONENT_ID,
        health_index=1.0,
        status=OperationalStatus.FUNCTIONAL,
        metrics=ComponentState.freeze_metrics(
            {
                "wiper_wear": 0.0,
                "residue_saturation": 0.0,
                "cleaning_effectiveness": 1.0,
            }
        ),
        age_ticks=0,
    )


def step(
    prev_self: ComponentState,
    coupling: CouplingContext,  # noqa: ARG001
    drivers: Drivers,  # noqa: ARG001
    env: Environment,  # noqa: ARG001
    dt: float,  # noqa: ARG001
    rng: np.random.Generator,  # noqa: ARG001
) -> ComponentState:
    return prev_self


def reset(
    prev_self: ComponentState,
    kind,  # noqa: ANN001, ARG001
    payload: Mapping[str, float],  # noqa: ARG001
) -> ComponentState:
    return prev_self
