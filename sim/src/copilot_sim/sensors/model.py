"""SensorModel protocol — per-component contract for the §3.4 true→observed pass.

Every component in the registry has an associated `SensorModel` that knows
how to turn a true `ComponentState` into an `ObservedComponentState`
(potentially using context from the rest of the printer — e.g. the
heater's reading is mediated by the temperature sensor's drift, which is
the §3.4 sensor-fault-vs-component-fault story made concrete).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from ..domain.state import ComponentState, ObservedComponentState, PrinterState


class SensorModel(Protocol):
    """Contract every per-component sensor model implements."""

    def observe(
        self,
        true_self: ComponentState,
        system: PrinterState,
        rng: np.random.Generator,
    ) -> ObservedComponentState: ...
