"""Raw environmental and operational drivers fed into the engine each tick."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Drivers:
    """The four inputs Phase 1 must accept (TRACK-CONTEXT.md §3.1).

    These are the raw values from the environment / operator. Components
    consume the *effective* drivers carried on `CouplingContext`, which adds
    cross-component degradation effects to these raw values.
    """

    temperature_stress: float
    humidity_contamination: float
    operational_load: float
    maintenance_level: float
