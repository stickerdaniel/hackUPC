"""Cross-component coupling carried into every component's step.

Built once per tick by `engine.coupling.build_coupling_context` from the
immutable `t-1` `PrinterState` and the current raw `Drivers`. Components read
the *effective* drivers from this object instead of the raw `Drivers`, which
is how cascading failures (heater wear → thermal stress on nozzle, blade wear
→ contamination on nozzle) enter the engine without any component reading
another component's state directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CouplingContext:
    temperature_stress_effective: float
    humidity_contamination_effective: float
    operational_load_effective: float
    maintenance_level_effective: float
    # Named coupling terms (e.g. "heater_thermal_stress_bonus": 0.12).
    # Persisted as `coupling_factors_json` on the `ticks` table so the co-pilot
    # can attribute degradation to upstream components without re-running the engine.
    factors: Mapping[str, float]

    @staticmethod
    def freeze_factors(factors: Mapping[str, float]) -> Mapping[str, float]:
        """Wrap a mutable mapping so callers cannot mutate the frozen field."""
        return MappingProxyType(dict(factors))
